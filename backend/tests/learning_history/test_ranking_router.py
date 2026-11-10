import unittest
from datetime import UTC, datetime
from decimal import Decimal
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


class UnitRankingRouterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        self.session = MagicMock()
        app.dependency_overrides[get_session] = lambda: self.session
        app.dependency_overrides[get_firebase_user] = lambda: AuthenticatedUser(
            firebase_uid="ranking-test-user"
        )
        self.app = app
        self.client = TestClient(app)
        self.mock_user = self.enterContext(
            patch.object(auth_repository, "get_user_by_firebase_uid")
        )
        self.mock_user.return_value = CurrentUser(
            id=7, firebase_uid="ranking-test-user", created_at=datetime.now(UTC)
        )
        self.mock_rankings = self.enterContext(
            patch.object(history_repository, "list_unit_rankings", return_value=[])
        )
        self.enterContext(patch.object(settings, "dev_fixed_user_enabled", False))

    def test_returns_rankings_in_api_design_shape_for_authenticated_user(self):
        self.mock_rankings.return_value = [
            (1, "division", "わり算", Decimal("70.0"), 2),
            (1, "fractions", "分数", Decimal("70.0"), 1),
            (3, "addition_subtraction_written", "筆算", Decimal("85.0"), 1),
        ]

        response = self.client.get("/v1/rankings/units?user_id=999")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["items"][0],
            {
                "rank": 1,
                "unit": {"code": "division", "name": "わり算"},
                "average_score_rate": 70.0,
                "record_count": 2,
            },
        )
        self.assertEqual([item["rank"] for item in response.json()["items"]], [1, 1, 3])
        # クエリの user_id は使わず、認証したユーザーで集計する。
        self.mock_rankings.assert_called_once_with(self.session, 7)

    def test_empty_rankings(self):
        response = self.client.get("/v1/rankings/units")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"items": []})

    def test_missing_or_invalid_token_cannot_read_rankings(self):
        del self.app.dependency_overrides[get_firebase_user]
        with patch.object(
            auth_service, "verify_id_token", side_effect=auth_service.InvalidTokenError
        ):
            for headers in ({}, {"Authorization": "Bearer invalid-test-token"}):
                with self.subTest(headers=headers):
                    response = self.client.get("/v1/rankings/units", headers=headers)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(
                        response.json()["error"]["code"], "UNAUTHENTICATED"
                    )
        self.mock_rankings.assert_not_called()

    def test_unregistered_user_cannot_read_rankings(self):
        self.mock_user.return_value = None
        response = self.client.get("/v1/rankings/units")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "USER_NOT_INITIALIZED")
        self.mock_rankings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
