"""Usage request and response schemas."""

from typing import Literal

from pydantic import BaseModel


class UsageResponse(BaseModel):
    can_analyze: bool
    used_count: int
    free_limit: int
    # 分析できない理由。分析できるときは null（#23）
    blocked_reason: Literal["plan_required", "monthly_limit_reached"] | None
