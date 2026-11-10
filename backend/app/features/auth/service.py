"""Firebase Admin SDK setup and ID token verification."""

import threading
from datetime import UTC

import firebase_admin
from firebase_admin import auth, credentials
from sqlmodel import Session

from app.core.config import settings
from app.db.models import User
from app.features.auth import repository as auth_repository
from app.features.auth.schemas import AuthenticatedUser, CurrentUser, UserResponse

FIREBASE_APP_NAME = "auth"

_firebase_app: firebase_admin.App | None = None
_firebase_app_lock = threading.Lock()


class AuthConfigurationError(Exception):
    """Raised when required Firebase configuration is missing."""


class InvalidTokenError(Exception):
    """Raised when the Firebase ID token is invalid, expired, or unusable."""


class UserNotInitializedError(Exception):
    """Raised when the Firebase user has not been registered in the app yet."""


def get_firebase_app() -> firebase_admin.App:
    """Return the Firebase app, initializing it on first use."""
    global _firebase_app

    # 起動時ではなく初回の検証時に初期化する。
    # 鍵ファイルがない環境（テスト・CI）でもアプリを起動できるようにするため。
    with _firebase_app_lock:
        if _firebase_app is None:
            if not settings.firebase_credentials_path:
                raise AuthConfigurationError(
                    "FIREBASE_CREDENTIALS_PATH is not configured."
                )
            _firebase_app = firebase_admin.initialize_app(
                credentials.Certificate(settings.firebase_credentials_path),
                name=FIREBASE_APP_NAME,
            )
        return _firebase_app


def verify_id_token(id_token: str) -> AuthenticatedUser:
    """Verify a Firebase ID token and return the user it identifies."""
    firebase_app = get_firebase_app()

    try:
        # check_revoked=True を付けないと、無効化されたユーザーや失効させたトークンが、
        # トークンの期限が切れるまで通ってしまう。Firebaseへの問い合わせが1回増える。
        decoded_token = auth.verify_id_token(
            id_token, app=firebase_app, check_revoked=True
        )
    except (
        # 期限切れ（ExpiredIdTokenError）と失効（RevokedIdTokenError）は、
        # InvalidIdTokenError に含まれる。
        auth.InvalidIdTokenError,
        auth.UserDisabledError,
        # Firebase側でユーザーが削除されている場合
        auth.UserNotFoundError,
        # 空文字など、トークンの形になっていない場合
        ValueError,
    ) as exc:
        raise InvalidTokenError("Firebase ID token is invalid.") from exc

    return AuthenticatedUser(
        firebase_uid=decoded_token["uid"],
        email=decoded_token.get("email"),
    )


def register_user(session: Session, firebase_uid: str) -> tuple[CurrentUser, bool]:
    """Register the user if needed. Return the user and whether it was created."""
    is_created = auth_repository.insert_user_if_absent(session, firebase_uid)
    session.commit()
    user = auth_repository.get_user_by_firebase_uid(session, firebase_uid)
    if user is None:
        raise RuntimeError("Registered user could not be loaded.")
    return _to_current_user(user), is_created


def find_current_user(session: Session, firebase_uid: str) -> CurrentUser:
    """Return the registered user, or raise UserNotInitializedError."""
    user = auth_repository.get_user_by_firebase_uid(session, firebase_uid)
    if user is None:
        raise UserNotInitializedError("User is not registered.")
    return _to_current_user(user)


def to_user_response(current_user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=str(current_user.id),
        # API設計に合わせ、日時はUTCで返す。
        created_at=current_user.created_at.astimezone(UTC),
    )


def _to_current_user(user: User) -> CurrentUser:
    # DBモデルを、そのまま外へ渡さない（規約11章）。
    return CurrentUser.model_validate(user, from_attributes=True)
