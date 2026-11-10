"""Usage tracking service."""

import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import status
from sqlmodel import Session

from app.core.config import settings
from app.features.payment import service as payment_service
from app.features.usage import cache as usage_cache
from app.features.usage import repository as usage_repository
from app.features.usage.schemas import UsageResponse
from app.shared.exceptions import AppError

# 暫定値（#10）。#30 の計測結果を見て見直す。
RATE_LIMIT_PER_MINUTE = 3
# 1分の枠に余裕を持たせた期限。古いカウンターはMemcachedが消す。
RATE_LIMIT_KEY_EXPIRE_SECONDS = 120
RATE_LIMIT_EXCEEDED_ERROR_CODE = "RATE_LIMIT_EXCEEDED"
# 月2回まで無料（PRD 10章）。有料プランの上限は設定値（MONTHLY_ANALYSIS_LIMIT）。
FREE_ANALYSIS_LIMIT = 2
# 利用回数は日本時間の暦月で数える（#10）。
USAGE_TIME_ZONE = ZoneInfo("Asia/Tokyo")

logger = logging.getLogger(__name__)


class RateLimitTarget(StrEnum):
    """The API being limited. Each one has its own counter."""

    # 普段の使い方（読み取り → 確認 → 分析）で引っかからないよう、別々に数える。
    STAGE_A = "analysis_a"
    STAGE_B = "analysis_b"


class BlockedReason(StrEnum):
    """Why the user cannot analyze now (API設計 3.8)."""

    PLAN_REQUIRED = "plan_required"
    MONTHLY_LIMIT_REACHED = "monthly_limit_reached"


def get_usage(
    session: Session, user_id: int, now: datetime | None = None
) -> UsageResponse:
    """Return this month's usage and whether the user may analyze now."""
    used_count = _count_this_month(session, user_id, now)
    blocked_reason = _get_blocked_reason(session, user_id, used_count)
    return UsageResponse(
        can_analyze=blocked_reason is None,
        used_count=used_count,
        free_limit=FREE_ANALYSIS_LIMIT,
        blocked_reason=blocked_reason,
    )


def check_remaining_usage(
    session: Session, user_id: int, now: datetime | None = None
) -> None:
    """Raise 403 unless the user may analyze (free quota, paid plan, monthly limit)."""
    used_count = _count_this_month(session, user_id, now)
    blocked_reason = _get_blocked_reason(session, user_id, used_count)
    if blocked_reason == BlockedReason.MONTHLY_LIMIT_REACHED:
        raise AppError(
            status.HTTP_403_FORBIDDEN,
            "MONTHLY_LIMIT_REACHED",
            f"今月の分析は{settings.monthly_analysis_limit}回までです。"
            "来月1日から、また分析できます。",
        )
    if blocked_reason == BlockedReason.PLAN_REQUIRED:
        raise AppError(
            status.HTTP_403_FORBIDDEN,
            "PLAN_REQUIRED",
            f"今月の無料の分析（{FREE_ANALYSIS_LIMIT}回）を使い切りました。"
            "続けて分析するには、月額プランへの登録が必要です。",
        )


def lock_usage(session: Session, user_id: int) -> None:
    """Save the user's usages one at a time. The caller commits or rolls back."""
    # ロックを取ってから数え直せば、先に確定した保存も含めて数えられる。
    # 家族が別の端末で同時に分析しても、上限を超えて保存しない（#10・#23）。
    usage_repository.lock_user_usage(session, user_id)


def current_month_range(now: datetime) -> tuple[datetime, datetime]:
    """Return the start and the end (exclusive) of now's month in Japan, in UTC."""
    local_now = now.astimezone(USAGE_TIME_ZONE)
    month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # どの月も28日に4日足せば、翌月に入る。
    next_month_start = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return month_start.astimezone(UTC), next_month_start.astimezone(UTC)


def _count_this_month(session: Session, user_id: int, now: datetime | None) -> int:
    counted_from, counted_until = current_month_range(now or datetime.now(UTC))
    return usage_repository.count_usages(session, user_id, counted_from, counted_until)


def _get_blocked_reason(
    session: Session, user_id: int, used_count: int
) -> BlockedReason | None:
    # 月の上限は、契約の有無にかかわらず優先する（10/24 合意）。
    if used_count >= settings.monthly_analysis_limit:
        return BlockedReason.MONTHLY_LIMIT_REACHED
    if used_count >= FREE_ANALYSIS_LIMIT and not (
        payment_service.has_active_subscription(session, user_id)
    ):
        return BlockedReason.PLAN_REQUIRED
    return None


def check_rate_limit(
    user_id: int, target: RateLimitTarget, now: datetime | None = None
) -> None:
    """Limit how often the user may call an analysis API in a short time."""
    now = now or datetime.now(UTC)
    # ユーザーID・対象・分単位の時刻（UTC）で数える（#10）。個人情報は含めない。
    key = f"{user_id}:{target}:{now:%Y%m%d%H%M}"
    try:
        count = usage_cache.increment_counter(key, RATE_LIMIT_KEY_EXPIRE_SECONDS)
    except usage_cache.CacheUnavailableError:
        # Memcachedが止まっていても分析は止めない（#10）。停止に気づけるようログに残す。
        # ユーザーやキーの値は残さない。
        logger.warning("Memcachedに接続できず、レート制限をせずに通しました。")
        return
    if count > RATE_LIMIT_PER_MINUTE:
        # 次の「分」になれば、新しいカウンターで数え直す。
        retry_after_seconds = 60 - now.second
        raise AppError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            RATE_LIMIT_EXCEEDED_ERROR_CODE,
            "短い時間に続けて分析しています。少し時間をおいてから、もう一度お試しください。",
            headers={"Retry-After": str(retry_after_seconds)},
        )


def is_analysis_counted(session: Session, analysis_request_id: UUID) -> bool:
    """Return whether this analysis has already been counted and saved."""
    return usage_repository.exists_usage(session, analysis_request_id)


def record_usage(
    session: Session, user_id: int, analysis_request_id: UUID, counted_at: datetime
) -> int:
    """Add one usage for a completed analysis. The caller commits (#20)."""
    # 分析記録と同じトランザクションで確定するため、ここではcommitしない。
    return usage_repository.insert_usage(
        session, user_id, analysis_request_id, counted_at
    )
