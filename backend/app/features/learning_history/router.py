from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db.session import get_session
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.learning_history import service as history_service
from app.features.learning_history.schemas import (
    HistoryResponse,
    UnitRankingResponse,
)

router = APIRouter(prefix="/v1", tags=["learning_history"])


@router.get("/analysis-records", response_model=HistoryResponse)
def read_history(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HistoryResponse:
    return history_service.get_history(session, current_user.id, limit, offset)


@router.get("/rankings/units", response_model=UnitRankingResponse)
def read_unit_rankings(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> UnitRankingResponse:
    return history_service.get_unit_rankings(session, current_user.id)
