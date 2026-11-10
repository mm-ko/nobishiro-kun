from fastapi import APIRouter, Response, status

from app.features.health.repository import is_database_available
from app.features.health.schemas import HealthResponse

router = APIRouter(prefix="/v1", tags=["health"])


@router.get(
    "/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}}
)
def check_health(response: Response) -> HealthResponse:
    if is_database_available():
        return HealthResponse(status="ok", database="ok")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="error", database="unavailable")
