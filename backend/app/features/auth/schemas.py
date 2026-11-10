"""Authentication schemas."""

from datetime import datetime

from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    """User identified from a verified Firebase ID token."""

    firebase_uid: str
    email: str | None = None


class CurrentUser(BaseModel):
    """Registered app user identified from a verified Firebase ID token."""

    id: int
    firebase_uid: str
    created_at: datetime


class UserResponse(BaseModel):
    """Response body of PUT /v1/users/me and GET /v1/users/me (API設計 3.1)."""

    # DBのbigintは、JavaScriptで桁が落ちないよう、文字列で返す（API設計 1章）。
    id: str
    created_at: datetime
