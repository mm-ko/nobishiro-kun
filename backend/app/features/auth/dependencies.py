"""Authentication dependencies shared by feature routers."""

from typing import Annotated

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.config import settings
from app.db.session import get_session
from app.features.auth import service as auth_service
from app.features.auth.schemas import AuthenticatedUser, CurrentUser
from app.shared.exceptions import AppError

UNAUTHENTICATED_ERROR_CODE = "UNAUTHENTICATED"
USER_NOT_INITIALIZED_ERROR_CODE = "USER_NOT_INITIALIZED"
# 開発用の固定ユーザー（#110）。Firebase の UID は英数字28文字のため、ぶつからない。
DEV_FIXED_USER_FIREBASE_UID = "dev-fixed-user"

# ヘッダーがない場合も、無効なトークンと同じ401にそろえるため、自動エラーは使わない。
bearer_scheme = HTTPBearer(auto_error=False)


def get_firebase_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    """Identify the Firebase user from the Authorization header.

    Use this only where the user may not be registered yet (PUT /v1/users/me).
    Other APIs use get_current_user.
    """
    if credentials is None:
        # 固定ユーザーにするのは、Authorization ヘッダーがない呼び出しだけ（#110）。
        # ヘッダーが付いていて Bearer として読み取れない場合
        # （「Bearer」だけ、Basic など）は、無効なトークンと同じ401にする。
        if settings.dev_fixed_user_enabled and "authorization" not in request.headers:
            return AuthenticatedUser(firebase_uid=DEV_FIXED_USER_FIREBASE_UID)
        raise _unauthenticated_error()

    try:
        return auth_service.verify_id_token(credentials.credentials)
    except auth_service.InvalidTokenError as exc:
        raise _unauthenticated_error() from exc


def get_current_user(
    firebase_user: Annotated[AuthenticatedUser, Depends(get_firebase_user)],
    session: Annotated[Session, Depends(get_session)],
) -> CurrentUser:
    """Return the registered app user for the logged-in Firebase user."""
    if (
        settings.dev_fixed_user_enabled
        and firebase_user.firebase_uid == DEV_FIXED_USER_FIREBASE_UID
    ):
        # 手でDBを準備しなくてよいよう、最初の呼び出しで users に追加する。
        current_user, _ = auth_service.register_user(
            session, firebase_user.firebase_uid
        )
        return current_user
    try:
        return auth_service.find_current_user(session, firebase_user.firebase_uid)
    except auth_service.UserNotInitializedError as exc:
        # 初回ログイン後、FEが PUT /v1/users/me を呼ぶ前の状態（API設計 1章）。
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            USER_NOT_INITIALIZED_ERROR_CODE,
            "ユーザー登録が完了していません。",
        ) from exc


def _unauthenticated_error() -> AppError:
    # 理由（ヘッダーなし・無効・期限切れ）は区別して返さない。
    # API設計のエラー一覧で、いずれも UNAUTHENTICATED の1種類のため。
    return AppError(
        status.HTTP_401_UNAUTHORIZED,
        UNAUTHENTICATED_ERROR_CODE,
        "ログインしてください。",
        headers={"WWW-Authenticate": "Bearer"},
    )
