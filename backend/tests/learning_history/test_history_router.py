import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import get_session
from app.features.auth import repository as auth_repository
from app.features.auth import service as auth_service
from app.features.auth.dependencies import get_firebase_user
from app.features.auth.schemas import AuthenticatedUser, CurrentUser
from app.features.learning_history import repository as history_repository
from app.features.learning_history.router import router
from app.shared.exceptions import register_exception_handlers

RECORDED_AT = datetime(2026, 10, 20, 12, tzinfo=timezone(timedelta(hours=9)))


class HistoryRouterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        self.session = MagicMock()
        app.dependency_overrides[get_session] = lambda: self.session
        app.dependency_overrides[get_firebase_user] = lambda: AuthenticatedUser(
            firebase_uid="history-test-user"
        )
        self.app = app
        self.client = TestClient(app)
        self.user = CurrentUser(
            id=7, firebase_uid="history-test-user", created_at=RECORDED_AT
        )
        self.mock_user = self.enterContext(
            patch.object(auth_repository, "get_user_by_firebase_uid")
        )
        self.mock_user.return_value = self.user
        self.mock_list = self.enterContext(
            patch.object(history_repository, "list_analysis_records", return_value=[])
        )
        self.enterContext(patch.object(settings, "dev_fixed_user_enabled", False))

    def test_returns_only_list_fields_with_string_id_and_utc_date(self):
        self.mock_list.return_value = [
            (9007199254740993, RECORDED_AT, "division", "わり算", 80, 100)
        ]

        response = self.client.get("/v1/analysis-records")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {
                        "id": "9007199254740993",
                        "recorded_at": "2026-10-20T03:00:00Z",
                        "unit": {"code": "division", "name": "わり算"},
                        "score": 80,
                        "max_score": 100,
                    }
                ],
                "limit": 20,
                "offset": 0,
                "has_more": False,
            },
        )
        self.mock_list.assert_called_once_with(self.session, 7, 21, 0)
        self.session.commit.assert_not_called()

    def test_empty_history(self):
        body = self.client.get("/v1/analysis-records").json()
        self.assertEqual(
            body, {"items": [], "limit": 20, "offset": 0, "has_more": False}
        )

    def test_pagination_trims_extra_item_and_uses_authenticated_user(self):
        self.mock_list.return_value = [
            (2, RECORDED_AT, "division", "わり算", 80, 100),
            (1, RECORDED_AT, "division", "わり算", 0, 100),
        ]

        body = self.client.get(
            "/v1/analysis-records?limit=1&offset=3&user_id=999"
        ).json()

        self.assertEqual([item["id"] for item in body["items"]], ["2"])
        self.assertTrue(body["has_more"])
        self.assertEqual((body["limit"], body["offset"]), (1, 3))
        self.mock_list.assert_called_once_with(self.session, 7, 2, 3)

    def test_limit_upper_boundary_is_accepted(self):
        response = self.client.get("/v1/analysis-records?limit=100&offset=0")
        self.assertEqual(response.status_code, 200)
        self.mock_list.assert_called_once_with(self.session, 7, 101, 0)

    def test_invalid_pagination_returns_common_validation_error(self):
        for query in ("limit=0", "limit=101", "limit=abc", "offset=-1", "offset=1.5"):
            with self.subTest(query=query):
                response = self.client.get(f"/v1/analysis-records?{query}")
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.mock_list.assert_not_called()

    def test_missing_or_invalid_token_cannot_read_history(self):
        del self.app.dependency_overrides[get_firebase_user]
        with patch.object(
            auth_service, "verify_id_token", side_effect=auth_service.InvalidTokenError
        ):
            for headers in ({}, {"Authorization": "Bearer invalid-test-token"}):
                with self.subTest(headers=headers):
                    response = self.client.get("/v1/analysis-records", headers=headers)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(
                        response.json()["error"]["code"], "UNAUTHENTICATED"
                    )
        self.mock_list.assert_not_called()

    def test_unregistered_user_cannot_read_history(self):
        self.mock_user.return_value = None
        response = self.client.get("/v1/analysis-records")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "USER_NOT_INITIALIZED")
        self.mock_list.assert_not_called()


if __name__ == "__main__":
    unittest.main()
