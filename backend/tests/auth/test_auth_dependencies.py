import unittest
from typing import Annotated
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from firebase_admin import auth

from app.features.auth import service as auth_service
from app.features.auth.dependencies import get_firebase_user
from app.features.auth.schemas import AuthenticatedUser
from app.shared.exceptions import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)


@app.get("/protected")
def read_protected(
    current_user: Annotated[AuthenticatedUser, Depends(get_firebase_user)],
) -> AuthenticatedUser:
    return current_user


class GetFirebaseUserTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

        # 本物の鍵ファイルとFirebaseには接続しない。
        app_patcher = patch.object(auth_service, "get_firebase_app")
        app_patcher.start()
        self.addCleanup(app_patcher.stop)

        verify_patcher = patch.object(auth_service.auth, "verify_id_token")
        self.mock_verify = verify_patcher.start()
        self.addCleanup(verify_patcher.stop)

    def get_protected(self, headers=None):
        return self.client.get("/protected", headers=headers)

    def test_valid_token_returns_firebase_uid_and_email(self):
        self.mock_verify.return_value = {
            "uid": "firebase-uid-1",
            "email": "parent@example.com",
        }

        response = self.get_protected({"Authorization": "Bearer valid-token"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"firebase_uid": "firebase-uid-1", "email": "parent@example.com"},
        )
        self.assertEqual(self.mock_verify.call_args.args[0], "valid-token")

    def test_missing_authorization_header_returns_401(self):
        response = self.get_protected()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "UNAUTHENTICATED")
        self.mock_verify.assert_not_called()

    def test_non_bearer_scheme_returns_401(self):
        response = self.get_protected({"Authorization": "Basic dXNlcjpwYXNz"})

        self.assertEqual(response.status_code, 401)
        self.mock_verify.assert_not_called()

    def test_invalid_token_returns_401(self):
        self.mock_verify.side_effect = auth.InvalidIdTokenError("invalid")

        response = self.get_protected({"Authorization": "Bearer invalid-token"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "UNAUTHENTICATED")

    def test_expired_token_returns_401(self):
        self.mock_verify.side_effect = auth.ExpiredIdTokenError("expired", None)

        response = self.get_protected({"Authorization": "Bearer expired-token"})

        self.assertEqual(response.status_code, 401)

    def test_token_is_verified_with_revocation_check(self):
        # check_revoked=True がないと、無効化されたユーザーと失効したトークンは
        # Firebase側で確認されず、下の3つのテストのエラーは実際には発生しない。
        self.mock_verify.return_value = {"uid": "firebase-uid-1"}

        self.get_protected({"Authorization": "Bearer valid-token"})

        self.assertIs(self.mock_verify.call_args.kwargs["check_revoked"], True)

    def test_disabled_user_returns_401(self):
        self.mock_verify.side_effect = auth.UserDisabledError("disabled")

        response = self.get_protected({"Authorization": "Bearer disabled-token"})

        self.assertEqual(response.status_code, 401)

    def test_revoked_token_returns_401(self):
        self.mock_verify.side_effect = auth.RevokedIdTokenError("revoked")

        response = self.get_protected({"Authorization": "Bearer revoked-token"})

        self.assertEqual(response.status_code, 401)

    def test_deleted_user_returns_401(self):
        self.mock_verify.side_effect = auth.UserNotFoundError("not found")

        response = self.get_protected({"Authorization": "Bearer deleted-token"})

        self.assertEqual(response.status_code, 401)

    def test_malformed_token_returns_401(self):
        self.mock_verify.side_effect = ValueError("malformed")

        response = self.get_protected({"Authorization": "Bearer malformed"})

        self.assertEqual(response.status_code, 401)

    def test_error_response_does_not_include_token_or_reason(self):
        self.mock_verify.side_effect = auth.InvalidIdTokenError("secret reason")

        response = self.get_protected({"Authorization": "Bearer secret-token"})

        self.assertNotIn("secret-token", response.text)
        self.assertNotIn("secret reason", response.text)


class GetFirebaseAppTests(unittest.TestCase):
    def setUp(self):
        app_reset = patch.object(auth_service, "_firebase_app", None)
        app_reset.start()
        self.addCleanup(app_reset.stop)

    def test_missing_credentials_path_raises_configuration_error(self):
        with patch.object(auth_service.settings, "firebase_credentials_path", None):
            with self.assertRaises(auth_service.AuthConfigurationError):
                auth_service.get_firebase_app()

    def test_app_is_initialized_only_once(self):
        with (
            patch.object(
                auth_service.settings,
                "firebase_credentials_path",
                "secrets/dummy.json",
            ),
            patch.object(auth_service.credentials, "Certificate") as mock_certificate,
            patch.object(
                auth_service.firebase_admin, "initialize_app"
            ) as mock_initialize,
        ):
            first_app = auth_service.get_firebase_app()
            second_app = auth_service.get_firebase_app()

        self.assertIs(first_app, second_app)
        mock_certificate.assert_called_once_with("secrets/dummy.json")
        mock_initialize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
