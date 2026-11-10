from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.usage import service as usage_service
from app.features.usage.schemas import UsageResponse

router = APIRouter(prefix="/v1", tags=["usage"])


@router.get("/usage", response_model=UsageResponse)
def read_usage(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> UsageResponse:
    return usage_service.get_usage(session, current_user.id)
