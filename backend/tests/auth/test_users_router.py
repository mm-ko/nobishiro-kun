import unittest
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.features.auth import repository as auth_repository
from app.features.auth.dependencies import get_firebase_user
from app.features.auth.router import router
from app.features.auth.schemas import AuthenticatedUser
from app.shared.exceptions import register_exception_handlers

FIREBASE_UID = "firebase-uid-1"
CREATED_AT = datetime(2026, 9, 26, 3, 0, tzinfo=UTC)


def make_user(created_at=CREATED_AT):
    return SimpleNamespace(id=1, firebase_uid=FIREBASE_UID, created_at=created_at)


class UsersMeRouterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)

        # 本物のDB・Firebaseには接続しない。
        self.session = MagicMock()
        app.dependency_overrides[get_session] = lambda: self.session
        app.dependency_overrides[get_firebase_user] = lambda: AuthenticatedUser(
            firebase_uid=FIREBASE_UID
        )
        self.app = app
        self.client = TestClient(app)

        insert_patcher = patch.object(auth_repository, "insert_user_if_absent")
        self.mock_insert = insert_patcher.start()
        self.addCleanup(insert_patcher.stop)

        get_patcher = patch.object(auth_repository, "get_user_by_firebase_uid")
        self.mock_get = get_patcher.start()
        self.addCleanup(get_patcher.stop)

    def test_first_registration_returns_201(self):
        self.mock_insert.return_value = True
        self.mock_get.return_value = make_user()

        response = self.client.put("/v1/users/me")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], "1")
        self.mock_insert.assert_called_once_with(self.session, FIREBASE_UID)
        self.session.commit.assert_called_once()

    def test_registration_of_existing_user_returns_200(self):
        self.mock_insert.return_value = False
        self.mock_get.return_value = make_user()

        response = self.client.put("/v1/users/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "1")

    def test_id_is_returned_as_string_and_created_at_in_utc(self):
        jst = timezone(timedelta(hours=9))
        self.mock_insert.return_value = False
        self.mock_get.return_value = make_user(
            created_at=datetime(2026, 9, 26, 12, 0, tzinfo=jst)
        )

        body = self.client.put("/v1/users/me").json()

        self.assertIsInstance(body["id"], str)
        self.assertEqual(
            datetime.fromisoformat(body["created_at"]),
            datetime(2026, 9, 26, 3, 0, tzinfo=UTC),
        )
        self.assertEqual(
            datetime.fromisoformat(body["created_at"]).utcoffset(), timedelta(0)
        )

    def test_user_id_in_request_is_ignored(self):
        self.mock_insert.return_value = True
        self.mock_get.return_value = make_user()

        self.client.put(
            "/v1/users/me?user_id=999",
            json={"user_id": 999, "firebase_uid": "someone-else"},
        )

        # 登録に使うのは、トークンから取得した Firebase UID だけ。
        self.mock_insert.assert_called_once_with(self.session, FIREBASE_UID)

    def test_registered_user_can_read_own_information(self):
        self.mock_get.return_value = make_user()

        response = self.client.get("/v1/users/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "1")
        self.mock_get.assert_called_once_with(self.session, FIREBASE_UID)
        self.mock_insert.assert_not_called()

    def test_unregistered_user_returns_404(self):
        self.mock_get.return_value = None

        response = self.client.get("/v1/users/me")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "USER_NOT_INITIALIZED")

    def test_request_without_token_returns_401_for_both_methods(self):
        del self.app.dependency_overrides[get_firebase_user]

        for method in ("put", "get"):
            with self.subTest(method=method):
                response = getattr(self.client, method)("/v1/users/me")

                self.assertEqual(response.status_code, 401)
        self.mock_insert.assert_not_called()
        self.mock_get.assert_not_called()

    def test_response_has_only_id_and_created_at(self):
        # 準備
        self.mock_get.return_value = make_user()

        # 実行
        response = self.client.get("/v1/users/me")

        # 確認
        self.assertEqual(set(response.json().keys()), {"id", "created_at"})


if __name__ == "__main__":
    unittest.main()
