from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session

from app.db.session import get_session
from app.features.auth import service as auth_service
from app.features.auth.dependencies import get_current_user, get_firebase_user
from app.features.auth.schemas import AuthenticatedUser, CurrentUser, UserResponse

router = APIRouter(prefix="/v1", tags=["users"])


@router.put(
    "/users/me",
    response_model=UserResponse,
    responses={201: {"model": UserResponse}},
)
def register_me(
    response: Response,
    firebase_user: Annotated[AuthenticatedUser, Depends(get_firebase_user)],
    session: Annotated[Session, Depends(get_session)],
) -> UserResponse:
    current_user, is_created = auth_service.register_user(
        session, firebase_user.firebase_uid
    )
    # 初回登録は201、登録済みなら200（API設計 3.1）。
    if is_created:
        response.status_code = status.HTTP_201_CREATED
    return auth_service.to_user_response(current_user)


@router.get("/users/me", response_model=UserResponse)
def read_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> UserResponse:
    return auth_service.to_user_response(current_user)
