import tempfile
import unittest
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.db.session import get_session
from app.features.ai_analysis import service as ai_analysis_service
from app.features.ai_analysis.clients.openrouter import (
    OpenRouterRateLimitError,
    OpenRouterTimeoutError,
)
from app.features.ai_analysis.schemas import StageAExtraction, StageAQuestion
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.test_analysis import service as test_analysis_service
from app.features.test_analysis import upload
from app.features.test_analysis.router import router
from app.features.usage import service as usage_service
from app.shared.exceptions import AppError, register_exception_handlers

USER_ID = 1
IDEMPOTENCY_KEY = "0b8f5f0e-3c1d-4c58-9a51-3f1f3d0a7a11"


def make_image(image_format):
    # 本物の答案は使わず、その場で作った単色の小さな画像を使う。
    buffer = BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 40)).save(buffer, image_format)
    return buffer.getvalue()


JPEG = make_image("JPEG")
PNG = make_image("PNG")


def make_extraction():
    return StageAExtraction(
        read_score=80,
        read_unit_name="あまりのあるわり算",
        questions=[
            StageAQuestion(
                question_id="q1",
                image_index=1,
                question_number="1(1)",
                problem_text="17÷5",
                student_answer="3あまり3",
                calculation_process=None,
                grading="incorrect",
            )
        ],
    )


class CreateAnalysisRouterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)

        # 本物のDB・Firebase・OpenRouterには接続しない。
        self.session = MagicMock()
        app.dependency_overrides[get_session] = lambda: self.session
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=USER_ID,
            firebase_uid="firebase-uid-1",
            created_at=datetime(2026, 9, 26, 3, 0, tzinfo=UTC),
        )
        self.app = app
        self.client = TestClient(app)

        client_patcher = patch.object(test_analysis_service, "OpenRouterClient")
        self.mock_openrouter_client = client_patcher.start().return_value
        self.addCleanup(client_patcher.stop)

        stage_a_patcher = patch.object(
            ai_analysis_service, "run_stage_a", return_value=make_extraction()
        )
        self.mock_run_stage_a = stage_a_patcher.start()
        self.addCleanup(stage_a_patcher.stop)

        self.mock_check_remaining_usage = self.enterContext(
            patch.object(usage_service, "check_remaining_usage")
        )

    def post(self, images, headers=None):
        if headers is None:
            headers = {"Idempotency-Key": IDEMPOTENCY_KEY}
        return self.client.post(
            "/v1/analyses",
            files=[
                ("images", (f"test{position}.jpg", content, "image/jpeg"))
                for position, content in enumerate(images, start=1)
            ],
            headers=headers,
        )

    def assert_error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code)
        self.assertEqual(response.json()["error"]["code"], code)

    def test_one_image_returns_201_with_extracted_facts(self):
        started_at = datetime.now(UTC)

        response = self.post([JPEG])

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(
            list(body),
            [
                "analysis_request_id",
                "status",
                "read_score",
                "read_unit_name",
                "questions",
                "expires_at",
            ],
        )
        UUID(body["analysis_request_id"])
        self.assertEqual(body["status"], "awaiting_confirmation")
        self.assertEqual(body["read_score"], 80)
        self.assertEqual(body["read_unit_name"], "あまりのあるわり算")
        self.assertEqual(
            body["questions"],
            [
                {
                    "question_id": "q1",
                    "image_index": 1,
                    "question_number": "1(1)",
                    "problem_text": "17÷5",
                    "student_answer": "3あまり3",
                    "calculation_process": None,
                    "grading": "incorrect",
                }
            ],
        )
        self.assertTrue(body["expires_at"].endswith("Z"))
        self.assertGreater(datetime.fromisoformat(body["expires_at"]), started_at)

    def test_each_request_gets_a_new_analysis_request_id(self):
        first = self.post([JPEG]).json()["analysis_request_id"]
        second = self.post([JPEG]).json()["analysis_request_id"]

        self.assertNotEqual(first, second)

    def test_two_images_are_passed_to_stage_a_in_order_with_detected_types(self):
        # 2枚目は、ファイル名とContent-TypeがJPEGでも、中身からPNGと判定する。
        response = self.post([JPEG, PNG])

        self.assertEqual(response.status_code, 201)
        input_images, client = self.mock_run_stage_a.call_args.args
        self.assertEqual(
            [(image.content, image.media_type) for image in input_images],
            [(JPEG, "image/jpeg"), (PNG, "image/png")],
        )
        self.assertIs(client, self.mock_openrouter_client)
        self.mock_openrouter_client.close.assert_called_once()

    def test_usage_checks_run_before_stage_a(self):
        calls = []
        self.mock_run_stage_a.side_effect = lambda *args: (
            calls.append("stage_a") or make_extraction()
        )
        with (
            patch.object(
                usage_service,
                "check_remaining_usage",
                side_effect=lambda session, user_id: calls.append(
                    ("remaining", user_id)
                ),
            ),
            patch.object(
                usage_service,
                "check_rate_limit",
                side_effect=lambda user_id, target: calls.append(
                    ("rate_limit", user_id, target)
                ),
            ),
        ):
            self.session.rollback.side_effect = lambda: calls.append("end_db_read")
            response = self.post([JPEG])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            calls,
            [
                ("remaining", USER_ID),
                # AIの読み取りの間、DBの接続を持ち続けない。
                "end_db_read",
                ("rate_limit", USER_ID, usage_service.RateLimitTarget.STAGE_A),
                "stage_a",
            ],
        )

    def test_usage_limit_stops_stage_a_before_calling_ai(self):
        for code in ("PLAN_REQUIRED", "MONTHLY_LIMIT_REACHED"):
            with self.subTest(code=code):
                self.mock_run_stage_a.reset_mock()
                self.mock_check_remaining_usage.side_effect = AppError(
                    403, code, "上限"
                )

                response = self.post([JPEG])

                self.assert_error(response, 403, code)
                self.mock_run_stage_a.assert_not_called()

    def test_three_images_are_rejected_without_calling_ai(self):
        response = self.post([JPEG, JPEG, JPEG])

        self.assert_error(response, 422, "VALIDATION_ERROR")
        self.assertEqual(response.json()["error"]["details"][0]["field"], "images")
        self.mock_run_stage_a.assert_not_called()

    def test_request_without_images_is_rejected(self):
        response = self.post([])

        self.assert_error(response, 422, "VALIDATION_ERROR")
        self.mock_run_stage_a.assert_not_called()

    def test_file_that_is_not_jpeg_or_png_is_rejected(self):
        # 拡張子とContent-Typeは画像でも、中身が画像でなければ受け付けない。
        for content in (b"%PDF-1.7 not an image", make_image("GIF"), b""):
            with self.subTest(content=content[:8]):
                response = self.post([JPEG, content])

                self.assert_error(response, 415, "UNSUPPORTED_IMAGE_TYPE")
        self.mock_run_stage_a.assert_not_called()

    def test_broken_image_is_rejected_without_calling_ai(self):
        # 先頭はJPEG・PNGでも、画像として読み取れないデータはAIへ送らない。
        broken_images = {
            "jpeg signature only": JPEG[:3],
            "jpeg cut in the middle": JPEG[: len(JPEG) // 2],
            "png signature only": PNG[:8],
            "png cut in the middle": PNG[: len(PNG) // 2],
        }
        for name, content in broken_images.items():
            with self.subTest(name=name):
                response = self.post([JPEG, content])

                self.assert_error(response, 422, "IMAGE_UNREADABLE")
        self.mock_run_stage_a.assert_not_called()

    def test_image_over_the_limit_per_image_is_rejected(self):
        with patch.object(settings, "image_max_bytes", len(JPEG) - 1):
            response = self.post([JPEG])

        self.assert_error(response, 413, "IMAGE_TOO_LARGE")
        self.mock_run_stage_a.assert_not_called()

    def test_images_over_the_total_limit_are_rejected(self):
        with patch.object(settings, "image_total_max_bytes", len(JPEG) + len(PNG) - 1):
            response = self.post([JPEG, PNG])

        self.assert_error(response, 413, "IMAGE_TOO_LARGE")
        self.mock_run_stage_a.assert_not_called()

    def test_images_at_the_limits_are_accepted(self):
        with (
            patch.object(settings, "image_max_bytes", max(len(JPEG), len(PNG))),
            patch.object(settings, "image_total_max_bytes", len(JPEG) + len(PNG)),
        ):
            response = self.post([JPEG, PNG])

        self.assertEqual(response.status_code, 201)

    def test_idempotency_key_is_required_and_must_be_uuid(self):
        for headers in ({}, {"Idempotency-Key": "not-a-uuid"}):
            with self.subTest(headers=headers):
                response = self.post([JPEG], headers=headers)

                self.assert_error(response, 422, "VALIDATION_ERROR")
        self.mock_run_stage_a.assert_not_called()

    def test_ai_failures_are_returned_in_the_common_error_format(self):
        cases = [
            (ai_analysis_service.StageAImageUnreadableError(), 422, "IMAGE_UNREADABLE"),
            (
                ai_analysis_service.StageAInvalidResponseError(),
                502,
                "AI_RESPONSE_INVALID",
            ),
            (OpenRouterTimeoutError(), 504, "ANALYSIS_TIMEOUT"),
            (OpenRouterRateLimitError(), 503, "AI_SERVICE_UNAVAILABLE"),
        ]
        for error, status_code, code in cases:
            with self.subTest(code=code):
                self.mock_openrouter_client.reset_mock()
                self.mock_run_stage_a.side_effect = error

                response = self.post([JPEG])

                self.assert_error(response, status_code, code)
                # 失敗しても、接続は閉じる。
                self.mock_openrouter_client.close.assert_called_once()

    def test_request_without_login_is_rejected(self):
        del self.app.dependency_overrides[get_current_user]

        response = self.post([JPEG])

        self.assert_error(response, 401, "UNAUTHENTICATED")
        self.mock_run_stage_a.assert_not_called()

    def test_upload_over_the_receiving_limit_is_rejected_by_its_declared_size(self):
        # Content-Lengthが上限を超えていれば、中身を受け取る前に断る。
        with (
            patch.object(settings, "image_total_max_bytes", 1000),
            patch.object(upload, "MULTIPART_OVERHEAD_BYTES", 500),
            patch.object(upload._LimitedUploadRequest, "stream") as mock_stream,
        ):
            response = self.post([JPEG + bytes(2000)])

        self.assert_error(response, 413, "IMAGE_TOO_LARGE")
        mock_stream.assert_not_called()
        self.mock_run_stage_a.assert_not_called()

    def test_upload_without_declared_size_stops_at_the_receiving_limit(self):
        # Content-Lengthのない送信でも、上限を超えた時点で受け取るのをやめる。
        boundary = "test-boundary"
        body = (
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="images"; filename="a.jpg"\r\n'
                "Content-Type: image/jpeg\r\n\r\n"
            ).encode()
            + JPEG
            + bytes(2000)
            + f"\r\n--{boundary}--\r\n".encode()
        )

        def chunks():
            for start in range(0, len(body), 256):
                yield body[start : start + 256]

        with (
            patch.object(settings, "image_total_max_bytes", 1000),
            patch.object(upload, "MULTIPART_OVERHEAD_BYTES", 500),
        ):
            response = self.client.post(
                "/v1/analyses",
                content=chunks(),
                headers={
                    "Idempotency-Key": IDEMPOTENCY_KEY,
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
            )

        self.assertNotIn("content-length", response.request.headers)
        self.assert_error(response, 413, "IMAGE_TOO_LARGE")
        self.mock_run_stage_a.assert_not_called()

    def test_received_uploads_are_never_written_to_a_temporary_file(self):
        # 受け取る量の上限まで、Starletteが一時ファイルへ書き出さないこと。
        self.assertGreater(
            upload.MultiPartParser.spool_max_size,
            settings.image_total_max_bytes + upload.MULTIPART_OVERHEAD_BYTES,
        )
        with patch.object(tempfile.SpooledTemporaryFile, "rollover") as mock_rollover:
            for images in ([JPEG, PNG], [JPEG, PNG, JPEG]):
                self.post(images)

        mock_rollover.assert_not_called()
