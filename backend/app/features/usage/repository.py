"""Database access for analysis usages."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.db.models import AnalysisUsage


def exists_usage(session: Session, analysis_request_id: UUID) -> bool:
    statement = select(AnalysisUsage.id).where(
        AnalysisUsage.analysis_request_id == analysis_request_id
    )
    return session.exec(statement).first() is not None


def count_usages(
    session: Session, user_id: int, counted_from: datetime, counted_until: datetime
) -> int:
    """Count the user's usages from counted_from up to (not including) counted_until."""
    statement = select(func.count(AnalysisUsage.id)).where(
        AnalysisUsage.user_id == user_id,
        AnalysisUsage.counted_at >= counted_from,
        AnalysisUsage.counted_at < counted_until,
    )
    return session.exec(statement).one()


def lock_user_usage(session: Session, user_id: int) -> None:
    """Wait until no other transaction is saving a usage for the same user."""
    # commit・rollback で外れるロック。DBのロックなので、サーバーが複数あっても効く。
    # 月額プランのロック（plan:）と番号が重ならないよう、先頭に用途を付ける。
    statement = select(func.pg_advisory_xact_lock(func.hashtext(f"usage:{user_id}")))
    session.execute(statement)


def insert_usage(
    session: Session, user_id: int, analysis_request_id: UUID, counted_at: datetime
) -> int:
    """Add a usage row without committing. Return its ID."""
    usage = AnalysisUsage(
        user_id=user_id,
        analysis_request_id=analysis_request_id,
        counted_at=counted_at,
    )
    session.add(usage)
    # 分析記録に利用実績のIDを入れるため、commitせずにDBの採番だけ受け取る。
    session.flush()
    if usage.id is None:
        raise RuntimeError("Analysis usage ID was not assigned.")
    return usage.id
