from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, UploadFile, status
from sqlmodel import Session

from app.db.session import get_session
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.test_analysis import service as test_analysis_service
from app.features.test_analysis.schemas import (
    StageAResponse,
    StageBRequest,
    StageBResponse,
)
from app.features.test_analysis.upload import LimitedUploadRoute

router = APIRouter(prefix="/v1", tags=["analyses"])


def create_analysis(
    images: Annotated[list[UploadFile], File()],
    # 必須であることと形式だけを確かめる。保存と再送への応答は、保持方式を
    # #27 で決めてから実装する。
    idempotency_key: Annotated[UUID, Header()],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> StageAResponse:
    return test_analysis_service.run_stage_a(session, current_user.id, images)


# 画像を受け取るこのAPIだけ、受け取る量と枚数を受信の段階で制限する。
router.add_api_route(
    "/analyses",
    create_analysis,
    methods=["POST"],
    response_model=StageAResponse,
    status_code=status.HTTP_201_CREATED,
    route_class_override=LimitedUploadRoute,
)


@router.post("/analyses/{analysis_request_id}/result", response_model=StageBResponse)
def create_analysis_result(
    analysis_request_id: UUID,
    request: StageBRequest,
    idempotency_key: Annotated[UUID, Header()],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> StageBResponse:
    # Stage Aと同様、IDの保持・所有者・期限・再送の制御は後続で接続する。
    return test_analysis_service.run_stage_b(
        session, current_user.id, analysis_request_id, request
    )
