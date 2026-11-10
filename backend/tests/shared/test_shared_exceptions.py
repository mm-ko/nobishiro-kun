import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.shared.exceptions import AppError, register_exception_handlers

app = FastAPI()
register_exception_handlers(app)


class ScoreRequest(BaseModel):
    score: int
    student_answer: str


@app.get("/app-error")
def raise_app_error() -> None:
    raise AppError(
        404,
        "ANALYSIS_NOT_FOUND",
        "分析が見つかりません。",
        headers={"Retry-After": "3"},
    )


@app.post("/validated")
def validated(request: ScoreRequest) -> ScoreRequest:
    return request


@app.get("/unexpected")
def raise_unexpected_error() -> None:
    raise RuntimeError("secret-internal-detail")


class CommonErrorFormatTests(unittest.TestCase):
    def setUp(self):
        # 予期しないエラーも、テストの中で例外にせず500の応答として受け取る。
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_app_error_is_returned_in_common_format(self):
        response = self.client.get("/app-error")

        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertEqual(
            body["error"],
            {
                "code": "ANALYSIS_NOT_FOUND",
                "message": "分析が見つかりません。",
                "details": [],
            },
        )
        self.assertTrue(body["request_id"].startswith("req-"))
        self.assertEqual(response.headers["Retry-After"], "3")

    def test_request_id_differs_for_each_request(self):
        first = self.client.get("/app-error").json()["request_id"]
        second = self.client.get("/app-error").json()["request_id"]

        self.assertNotEqual(first, second)

    def test_validation_error_lists_fields_without_input_values(self):
        response = self.client.post(
            "/validated", json={"score": "eighty", "student_answer": None}
        )

        self.assertEqual(response.status_code, 422)
        error = response.json()["error"]
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertEqual(
            sorted(detail["field"] for detail in error["details"]),
            ["score", "student_answer"],
        )
        self.assertNotIn("eighty", response.text)

    def test_missing_field_is_reported_as_required(self):
        response = self.client.post("/validated", json={"score": 80})

        details = response.json()["error"]["details"]
        self.assertEqual(
            details, [{"field": "student_answer", "reason": "必須の項目です。"}]
        )

    def test_unexpected_error_hides_internal_details(self):
        response = self.client.get("/unexpected")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("secret-internal-detail", response.text)


class ErrorLogTests(unittest.TestCase):
    LOGGER_NAME = "app.shared.exceptions"

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_log_has_same_request_id_as_response(self):
        with self.assertLogs(self.LOGGER_NAME, level="WARNING") as logs:
            response = self.client.get("/app-error")

        self.assertEqual(len(logs.records), 1)
        self.assertEqual(logs.records[0].levelname, "WARNING")
        message = logs.records[0].getMessage()
        self.assertIn(f"request_id={response.json()['request_id']}", message)
        self.assertIn("method=GET", message)
        self.assertIn("path=/app-error", message)
        self.assertIn("status=404", message)
        self.assertIn("code=ANALYSIS_NOT_FOUND", message)

    def test_log_has_no_input_values_or_query(self):
        with self.assertLogs(self.LOGGER_NAME, level="WARNING") as logs:
            self.client.post(
                "/validated?token=secret-query",
                json={"score": "eighty", "student_answer": "secret-answer"},
                headers={"Authorization": "Bearer secret-token"},
            )

        message = logs.records[0].getMessage()
        self.assertIn("path=/validated ", message)
        self.assertIn("code=VALIDATION_ERROR", message)
        for secret in ("eighty", "secret-answer", "secret-query", "secret-token"):
            self.assertNotIn(secret, message)

    def test_unexpected_error_is_logged_as_error_with_type_only(self):
        with self.assertLogs(self.LOGGER_NAME, level="WARNING") as logs:
            response = self.client.get("/unexpected")

        self.assertEqual(logs.records[0].levelname, "ERROR")
        message = logs.records[0].getMessage()
        self.assertIn(f"request_id={response.json()['request_id']}", message)
        self.assertIn("status=500", message)
        self.assertIn("error_type=RuntimeError", message)
        self.assertNotIn("secret-internal-detail", message)


if __name__ == "__main__":
    unittest.main()
