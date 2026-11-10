import unittest
from datetime import UTC, datetime
from typing import Annotated
from unittest.mock import MagicMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from firebase_admin import auth
from pydantic import ValidationError

from app.core.config import Settings, SettingsConfigurationError
from app.db.session import get_session
from app.features.auth import dependencies
from app.features.auth import service as auth_service
from app.features.auth.dependencies import (
    DEV_FIXED_USER_FIREBASE_UID,
    get_current_user,
)
from app.features.auth.schemas import CurrentUser
from app.shared.exceptions import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)


@app.get("/me")
def read_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    return current_user


def make_user(user_id, firebase_uid):
    return CurrentUser(
        id=user_id, firebase_uid=firebase_uid, created_at=datetime.now(UTC)
    )


class DevFixedUserSettingsTests(unittest.TestCase):
    def test_disabled_by_default_and_production_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings(_env_file=None)

        self.assertFalse(settings.dev_fixed_user_enabled)
        self.assertEqual(settings.app_env, "production")

    def test_cannot_be_enabled_in_production(self):
        with self.assertRaises(SettingsConfigurationError) as raised:
            Settings(
                app_env="production",
                dev_fixed_user_enabled=True,
                database_url="postgresql+psycopg://user:SECRET-PASSWORD@db/app",
            )

        # 起動エラーの表示に、他の設定値を含めない。
        self.assertNotIn("SECRET-PASSWORD", str(raised.exception))

    def test_can_be_enabled_in_development(self):
        settings = Settings(app_env="development", dev_fixed_user_enabled=True)

        self.assertTrue(settings.dev_fixed_user_enabled)

    def test_unknown_app_env_is_rejected(self):
        with self.assertRaises(ValidationError):
            Settings(app_env="staging")


class DevFixedUserDependencyTests(unittest.TestCase):
    def setUp(self):
        # 本物のDB・Firebaseには接続しない。
        self.session = MagicMock()
        app.dependency_overrides[get_session] = lambda: self.session
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

        for target, name in [
            (auth_service, "get_firebase_app"),
            (auth_service.auth, "verify_id_token"),
            (auth_service, "register_user"),
            (auth_service, "find_current_user"),
        ]:
            patcher = patch.object(target, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.register_user.return_value = (
            make_user(1, DEV_FIXED_USER_FIREBASE_UID),
            True,
        )
        self.find_current_user.return_value = make_user(2, "firebase-uid-1")

    def enable_dev_fixed_user(self, enabled):
        patcher = patch.object(dependencies.settings, "dev_fixed_user_enabled", enabled)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_disabled_request_without_token_returns_401(self):
        self.enable_dev_fixed_user(False)

        response = self.client.get("/me")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "UNAUTHENTICATED")
        self.register_user.assert_not_called()

    def test_enabled_request_without_token_uses_fixed_user(self):
        self.enable_dev_fixed_user(True)

        response = self.client.get("/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["firebase_uid"], DEV_FIXED_USER_FIREBASE_UID)
        # 手で準備しなくてよいよう、なければ追加する処理で固定ユーザーを取得する。
        self.register_user.assert_called_once_with(
            self.session, DEV_FIXED_USER_FIREBASE_UID
        )
        self.verify_id_token.assert_not_called()

    def test_enabled_request_with_valid_token_uses_that_user(self):
        self.enable_dev_fixed_user(True)
        self.verify_id_token.return_value = {"uid": "firebase-uid-1"}

        response = self.client.get(
            "/me", headers={"Authorization": "Bearer valid-token"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["firebase_uid"], "firebase-uid-1")
        self.find_current_user.assert_called_once_with(self.session, "firebase-uid-1")
        self.register_user.assert_not_called()

    def test_enabled_request_with_invalid_token_returns_401(self):
        self.enable_dev_fixed_user(True)
        self.verify_id_token.side_effect = auth.InvalidIdTokenError("invalid")

        response = self.client.get(
            "/me", headers={"Authorization": "Bearer invalid-token"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "UNAUTHENTICATED")
        # 無効なトークンを、固定ユーザーに切り替えていないこと
        self.register_user.assert_not_called()

    def test_enabled_request_with_unreadable_authorization_header_returns_401(self):
        self.enable_dev_fixed_user(True)

        for header in ["Bearer", "Basic invalid-token", ""]:
            with self.subTest(header=header):
                response = self.client.get("/me", headers={"Authorization": header})

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["error"]["code"], "UNAUTHENTICATED")
        # ヘッダーが付いていれば、読み取れなくても固定ユーザーに切り替えないこと
        self.register_user.assert_not_called()
        self.verify_id_token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
