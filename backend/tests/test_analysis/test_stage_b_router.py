import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db.session import get_session
from app.features.ai_analysis import service as ai_service
from app.features.ai_analysis.clients.openrouter import (
    OpenRouterError,
    OpenRouterTimeoutError,
)
from app.features.ai_analysis.schemas import AnalysisComment, StageBResult, StageBUnit
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.test_analysis import service
from app.features.test_analysis.router import router
from app.shared.exceptions import AppError, register_exception_handlers


class StageBRouterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=7, firebase_uid="test-user", created_at=datetime.now(UTC)
        )
        # 本物のDBには接続しない。
        self.session = MagicMock()
        app.dependency_overrides[get_session] = lambda: self.session
        self.client = TestClient(app)
        self.analysis_request_id = uuid4()
        self.url = f"/v1/analyses/{self.analysis_request_id}/result"
        self.headers = {"Idempotency-Key": str(uuid4())}
        self.body = dict(
            score=0,
            max_score=100,
            read_unit_name=None,
            confirmed_questions=[
                dict(
                    question_id="q1",
                    image_index=2,
                    question_number=None,
                    problem_text="17÷5",
                    student_answer="",
                    calculation_process=None,
                    grading="incorrect",
                )
            ],
        )
        for target, name in [
            (service, "OpenRouterClient"),
            (ai_service, "run_stage_b"),
            (ai_service, "generate_comment"),
            (service.history_service, "save_analysis"),
            (service.usage_service, "is_analysis_counted"),
            (service.usage_service, "record_usage"),
            (service.usage_service, "check_rate_limit"),
            (service.usage_service, "check_remaining_usage"),
            (service.usage_service, "lock_usage"),
            (service.test_analysis_repository, "list_units"),
        ]:
            patcher = patch.object(target, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.is_analysis_counted.return_value = False
        self.record_usage.return_value = 11
        self.list_units.return_value = [
            SimpleNamespace(id=1, code="division", name="わり算"),
            SimpleNamespace(
                id=2, code="addition_subtraction_written", name="たし算とひき算の筆算"
            ),
        ]
        self.run_stage_b.return_value = StageBResult(
            unit_status="supported",
            unit=StageBUnit(id=1, code="division", name="わり算"),
            unit_is_estimated=True,
            patterns=[],
        )
        self.generate_comment.return_value = AnalysisComment(
            comment_title="一緒に問題を振り返ってみましょう",
            comment_body="テストの確認、お疲れさまです。" * 12,
        )

    def post(self):
        return self.client.post(self.url, json=self.body, headers=self.headers)

    def test_supported_flow_and_confirmed_text_only(self):
        for score, expected_title in (
            (0, self.generate_comment.return_value.comment_title),
            (100, self.generate_comment.return_value.comment_title),
        ):
            self.body["score"] = score
            response = self.post()
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["score_rate"], score)
            self.assertEqual(result["unit"]["id"], "1")
            self.assertEqual(result["incorrect_question_numbers"], ["2:番号不明-q1"])
            self.assertEqual(
                set(self.run_stage_b.call_args.args[0].model_dump()),
                {"read_unit_name", "confirmed_questions"},
            )
            self.assertEqual(
                result["comment_title"],
                expected_title,
            )
            self.assertEqual(
                result["comment_body"], self.generate_comment.return_value.comment_body
            )
            self.generate_comment.assert_called_with(
                self.run_stage_b.call_args.args[0],
                self.run_stage_b.return_value,
                self.OpenRouterClient.return_value,
            )
            self.record_usage.assert_called_with(
                self.session, 7, self.analysis_request_id, ANY
            )
            saved_at = self.record_usage.call_args.args[3]
            self.save_analysis.assert_called_with(
                self.session,
                user_id=7,
                unit_id=1,
                analysis_usage_id=11,
                score=score,
                max_score=100,
                score_rate=Decimal(score).quantize(Decimal("0.01")),
                incorrect_question_numbers=["2:番号不明-q1"],
                analysis_result={"patterns": []},
                comment_title=expected_title,
                comment_body=self.generate_comment.return_value.comment_body,
                recorded_at=saved_at,
            )
        self.OpenRouterClient.return_value.close.assert_called()
        self.assertEqual(self.session.commit.call_count, 2)

    def test_full_score_with_incorrect_question_keeps_generated_title(self):
        self.body["score"] = self.body["max_score"]
        response = self.post()
        self.assertEqual(response.status_code, 200)
        expected_title = self.generate_comment.return_value.comment_title
        self.assertEqual(response.json()["comment_title"], expected_title)
        self.assertEqual(
            self.save_analysis.call_args.kwargs["comment_title"], expected_title
        )

    def test_full_score_title_uses_entered_score_and_max_score(self):
        self.body["confirmed_questions"][0]["grading"] = "correct"
        for score, max_score, expected_title in (
            (1, 1, "今回のテストは満点でした"),
            (50, 50, "今回のテストは満点でした"),
            (200, 200, "今回のテストは満点でした"),
            (99, 100, self.generate_comment.return_value.comment_title),
            (100, 200, self.generate_comment.return_value.comment_title),
        ):
            with self.subTest(score=score, max_score=max_score):
                self.body.update(score=score, max_score=max_score)
                response = self.post()
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result["comment_title"], expected_title)
                self.assertEqual(
                    result["comment_body"],
                    self.generate_comment.return_value.comment_body,
                )
                # 満点の差し替えも含めて、画面に返すタイトルと同じものを保存する。
                saved = self.save_analysis.call_args.kwargs
                self.assertEqual(saved["comment_title"], expected_title)
                self.assertEqual(
                    saved["comment_body"],
                    self.generate_comment.return_value.comment_body,
                )

    def test_score_rate_uses_two_decimal_places_and_all_correct_has_no_errors(self):
        self.body.update(score=1, max_score=32)
        self.body["confirmed_questions"][0]["grading"] = "correct"
        result = self.post().json()
        self.assertEqual(result["score_rate"], 3.13)
        self.assertEqual(result["incorrect_question_numbers"], [])
        self.assertEqual(result["analysis_result"]["patterns"], [])
        self.generate_comment.assert_called_once()

    def test_non_hundred_point_scores_are_returned_and_saved_consistently(self):
        for score, max_score, expected_rate in (
            (90, 150, "60.00"),
            (100, 150, "66.67"),
            (1, 32, "3.13"),
            (0, 150, "0.00"),
        ):
            with self.subTest(score=score, max_score=max_score):
                self.body.update(score=score, max_score=max_score)
                self.save_analysis.reset_mock()
                self.record_usage.reset_mock()
                self.session.reset_mock()

                response = self.post()

                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result["status"], "completed")
                self.assertEqual(
                    (result["score"], result["max_score"]), (score, max_score)
                )
                self.assertEqual(result["score_rate"], float(expected_rate))
                self.save_analysis.assert_called_once()
                saved = self.save_analysis.call_args.kwargs
                self.assertEqual(
                    (saved["score"], saved["max_score"]), (score, max_score)
                )
                self.assertEqual(saved["score_rate"], Decimal(expected_rate))
                self.record_usage.assert_called_once_with(
                    self.session, 7, self.analysis_request_id, saved["recorded_at"]
                )
                self.session.commit.assert_called_once_with()
                self.session.rollback.assert_not_called()

    def test_two_images_keep_only_incorrect_question_numbers_in_input_order(self):
        question = self.body["confirmed_questions"][0]
        self.body["confirmed_questions"] = [
            question
            | dict(
                question_id=question_id,
                image_index=image_index,
                question_number=number,
                grading=grading,
            )
            for question_id, image_index, number, grading in (
                ("q1", 1, "1", "correct"),
                ("q2", 1, "2", "incorrect"),
                ("q3", 2, "1", "incorrect"),
                ("q4", 2, None, "incorrect"),
                ("q5", 2, "3", "correct"),
            )
        ]

        response = self.post()

        self.assertEqual(response.status_code, 200)
        expected_numbers = ["1:2", "2:1", "2:番号不明-q4"]
        self.assertEqual(
            response.json()["incorrect_question_numbers"], expected_numbers
        )
        self.save_analysis.assert_called_once()
        self.assertEqual(
            self.save_analysis.call_args.kwargs["incorrect_question_numbers"],
            expected_numbers,
        )
        self.session.commit.assert_called_once_with()

    def test_non_supported_results_skip_saving_and_comments(self):
        for unit_status, expected, message in [
            (
                "unsupported",
                "unsupported",
                "このテストの単元は分析対象外のため、分析を終了します。"
                "利用回数は消費されません。",
            ),
            (
                "undetermined",
                "unit_undetermined",
                "このテストの単元を特定できなかったため、分析を終了します。"
                "利用回数は消費されません。",
            ),
        ]:
            self.run_stage_b.return_value = StageBResult(
                unit_status=unit_status,
                unit=None,
                unit_is_estimated=False,
                patterns=None,
            )
            response = self.post()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], expected)
            self.assertEqual(response.json()["message"], message)
            for key in (
                "unit",
                "analysis_result",
                "comment_title",
                "comment_body",
                "incorrect_question_numbers",
            ):
                self.assertIsNone(response.json()[key])
        self.save_analysis.assert_not_called()
        self.record_usage.assert_not_called()
        self.session.commit.assert_not_called()
        self.generate_comment.assert_not_called()

    def test_rate_limit_is_checked_for_stage_b_before_ai(self):
        self.post()

        self.check_rate_limit.assert_called_once_with(
            7, service.usage_service.RateLimitTarget.STAGE_B
        )

    def test_rate_limited_request_never_calls_ai(self):
        self.check_rate_limit.side_effect = AppError(
            429, "RATE_LIMIT_EXCEEDED", "制限", headers={"Retry-After": "30"}
        )

        response = self.post()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "RATE_LIMIT_EXCEEDED")
        self.assertEqual(response.headers["Retry-After"], "30")
        self.run_stage_b.assert_not_called()
        self.save_analysis.assert_not_called()

    def test_invalid_input_never_calls_ai(self):
        self.body["score"] = -1
        response = self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.run_stage_b.assert_not_called()

    def test_uuid_headers_and_authentication_are_required(self):
        self.headers = {}
        self.assertEqual(self.post().status_code, 422)
        self.headers = {"Idempotency-Key": "invalid"}
        self.assertEqual(self.post().status_code, 422)
        self.client.app.dependency_overrides.clear()
        self.assertEqual(self.post().status_code, 401)

    def test_ai_errors_close_client_and_skip_saving(self):
        for error, status, code in [
            (ai_service.StageBInvalidResponseError, 502, "AI_RESPONSE_INVALID"),
            (OpenRouterTimeoutError, 504, "ANALYSIS_TIMEOUT"),
            (OpenRouterError, 503, "AI_SERVICE_UNAVAILABLE"),
        ]:
            self.run_stage_b.side_effect = error("private model output")
            response = self.post()
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.json()["error"]["code"], code)
            self.assertNotIn("private model output", response.text)
            self.OpenRouterClient.return_value.close.assert_called()
        self.save_analysis.assert_not_called()
        self.record_usage.assert_not_called()

    def test_comment_errors_close_client_and_skip_saving(self):
        for error, status, code in [
            (ai_service.StageBInvalidResponseError, 502, "AI_RESPONSE_INVALID"),
            (OpenRouterTimeoutError, 504, "ANALYSIS_TIMEOUT"),
            (OpenRouterError, 503, "AI_SERVICE_UNAVAILABLE"),
        ]:
            with self.subTest(error=error):
                self.generate_comment.side_effect = error("private model output")
                response = self.post()
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["error"]["code"], code)
                self.assertNotIn("private model output", response.text)
                self.OpenRouterClient.return_value.close.assert_called()
        self.assertEqual(self.run_stage_b.call_count, 3)
        self.save_analysis.assert_not_called()
        self.record_usage.assert_not_called()
        self.session.commit.assert_not_called()

    def test_usage_and_record_share_the_save_time_in_utc(self):
        # DBのnow()（トランザクション開始の時刻）ではなく、保存する時点の時刻を使う。
        before = datetime.now(UTC)
        self.post()
        after = datetime.now(UTC)

        counted_at = self.record_usage.call_args.args[3]
        self.assertEqual(counted_at.utcoffset(), timedelta(0))
        self.assertTrue(before <= counted_at <= after)
        self.assertEqual(self.save_analysis.call_args.kwargs["recorded_at"], counted_at)

    def test_units_are_read_from_the_database(self):
        self.post()

        units = self.run_stage_b.call_args.args[1]
        self.assertEqual(
            [(unit.id, unit.code) for unit in units],
            [(1, "division"), (2, "addition_subtraction_written")],
        )

    def test_usage_is_checked_after_saved_check_and_before_rate_limit(self):
        calls = []
        self.is_analysis_counted.side_effect = lambda *args: calls.append("saved")
        self.check_remaining_usage.side_effect = lambda session, user_id, *rest: (
            calls.append(("remaining", user_id))
        )
        self.check_rate_limit.side_effect = lambda *args: calls.append("rate_limit")
        self.run_stage_b.side_effect = lambda *args: (
            calls.append("stage_b") or self.run_stage_b.return_value
        )

        self.post()

        self.assertEqual(
            calls[:4], ["saved", ("remaining", 7), "rate_limit", "stage_b"]
        )

    def test_usage_limit_stops_stage_b_before_calling_ai(self):
        # Stage Aを通らずに直接呼ばれても、上限に達していればAIを呼ばない。
        for code in ("PLAN_REQUIRED", "MONTHLY_LIMIT_REACHED"):
            with self.subTest(code=code):
                self.check_remaining_usage.side_effect = AppError(403, code, "上限")

                response = self.post()

                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"]["code"], code)
                self.run_stage_b.assert_not_called()

    def test_saved_analysis_resent_after_reaching_limit_is_still_409(self):
        self.is_analysis_counted.return_value = True
        self.check_remaining_usage.side_effect = AppError(
            403, "MONTHLY_LIMIT_REACHED", "上限"
        )

        response = self.post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "ANALYSIS_STATE_CONFLICT")

    def test_usage_is_checked_again_under_lock_before_saving(self):
        calls = []
        self.lock_usage.side_effect = lambda session, user_id: calls.append(
            ("lock", user_id)
        )
        self.is_analysis_counted.side_effect = lambda *args: calls.append("saved")
        self.check_remaining_usage.side_effect = lambda *args: calls.append("remaining")
        self.record_usage.side_effect = lambda *args: calls.append("record") or 11

        self.post()

        # 送信前のチェックのあと、ロック → 保存済みか → 上限 → 保存の順。
        self.assertEqual(calls[-4:], [("lock", 7), "saved", "remaining", "record"])
        saved_at = self.check_remaining_usage.call_args.args[2]
        self.assertEqual(saved_at, self.record_usage.call_args.args[3])

    def test_same_analysis_sent_twice_at_the_last_use_returns_409(self):
        # 残り1回で同じ分析IDを2回同時に送り、両方が送信前のチェックを通った。
        # 後の送信は、ロックの中で先の保存を見つけ、上限の403より先に409にする。
        for code in ("PLAN_REQUIRED", "MONTHLY_LIMIT_REACHED"):
            with self.subTest(code=code):
                self.session.reset_mock()
                self.record_usage.reset_mock()
                self.save_analysis.reset_mock()
                self.is_analysis_counted.side_effect = [False, True]
                self.check_remaining_usage.side_effect = [
                    None,
                    AppError(403, code, "上限"),
                ]

                response = self.post()

                self.assertEqual(response.status_code, 409)
                self.assertEqual(
                    response.json()["error"]["code"], "ANALYSIS_STATE_CONFLICT"
                )
                self.record_usage.assert_not_called()
                self.save_analysis.assert_not_called()
                self.session.rollback.assert_called_once_with()
                self.session.commit.assert_not_called()

    def test_limit_reached_while_analyzing_saves_nothing(self):
        # 残り1回で2つ同時に分析し、先にもう一方が保存された場合。
        for code in ("PLAN_REQUIRED", "MONTHLY_LIMIT_REACHED"):
            with self.subTest(code=code):
                self.session.reset_mock()
                self.record_usage.reset_mock()
                self.save_analysis.reset_mock()
                self.check_remaining_usage.side_effect = [
                    None,
                    AppError(403, code, "上限"),
                ]

                response = self.post()

                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"]["code"], code)
                self.record_usage.assert_not_called()
                self.save_analysis.assert_not_called()
                self.session.rollback.assert_called_once_with()
                self.session.commit.assert_not_called()

    def test_saved_analysis_is_rejected_before_calling_ai(self):
        self.is_analysis_counted.return_value = True

        response = self.post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "ANALYSIS_STATE_CONFLICT")

        # AI を呼んでいない（費用をかけていない）こと
        self.run_stage_b.assert_not_called()

    def test_concurrent_save_returns_409_and_keeps_nothing(self):
        # 同じ分析処理IDが、先に別の送信で保存された場合。
        # 送信前・ロックの中では未保存で、保存の途中で先を越された場合。
        self.is_analysis_counted.side_effect = [False, False, True]
        self.save_analysis.side_effect = IntegrityError("insert", {}, Exception())

        response = self.post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "ANALYSIS_STATE_CONFLICT")
        self.session.rollback.assert_called_once()
        self.session.commit.assert_not_called()

    def test_other_save_errors_are_not_reported_as_conflict(self):
        self.save_analysis.side_effect = IntegrityError("insert", {}, Exception())
        # 想定外のエラーも、共通形式の500として返ることを確かめる。
        client = TestClient(self.client.app, raise_server_exceptions=False)

        response = client.post(self.url, json=self.body, headers=self.headers)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "INTERNAL_ERROR")
        self.session.rollback.assert_called_once()
        self.session.commit.assert_not_called()

    def test_usage_save_constraint_errors_rollback_before_saving_record(self):
        client = TestClient(self.client.app, raise_server_exceptions=False)
        for already_saved, expected_status, expected_code in (
            (True, 409, "ANALYSIS_STATE_CONFLICT"),
            (False, 500, "INTERNAL_ERROR"),
        ):
            with self.subTest(already_saved=already_saved):
                self.session.reset_mock()
                self.record_usage.reset_mock()
                self.save_analysis.reset_mock()
                self.is_analysis_counted.side_effect = [False, False, already_saved]
                self.record_usage.side_effect = IntegrityError(
                    "insert", {}, Exception("dummy database detail")
                )

                response = client.post(self.url, json=self.body, headers=self.headers)

                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.json()["error"]["code"], expected_code)
                self.assertNotIn("dummy database detail", response.text)
                self.record_usage.assert_called_once()
                self.save_analysis.assert_not_called()
                self.session.rollback.assert_called_once_with()
                self.session.commit.assert_not_called()

    def test_commit_constraint_errors_rollback_instead_of_returning_completed(self):
        client = TestClient(self.client.app, raise_server_exceptions=False)
        for already_saved, expected_status, expected_code in (
            (True, 409, "ANALYSIS_STATE_CONFLICT"),
            (False, 500, "INTERNAL_ERROR"),
        ):
            with self.subTest(already_saved=already_saved):
                self.session.reset_mock()
                self.record_usage.reset_mock()
                self.save_analysis.reset_mock()
                self.is_analysis_counted.side_effect = [False, False, already_saved]
                self.session.commit.side_effect = IntegrityError(
                    "commit", {}, Exception("dummy database detail")
                )

                response = client.post(self.url, json=self.body, headers=self.headers)

                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.json()["error"]["code"], expected_code)
                self.assertNotIn("dummy database detail", response.text)
                self.record_usage.assert_called_once()
                self.save_analysis.assert_called_once()
                self.session.commit.assert_called_once_with()
                self.session.rollback.assert_called_once_with()
