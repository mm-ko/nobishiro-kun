"""Database access for learning history."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from app.db.models import AnalysisRecord, Unit


def list_analysis_records(
    session: Session, user_id: int, limit: int, offset: int
) -> list[tuple[int, datetime, str, str, int, int]]:
    statement = (
        select(
            AnalysisRecord.id,
            AnalysisRecord.recorded_at,
            Unit.code,
            Unit.name,
            AnalysisRecord.score,
            AnalysisRecord.max_score,
        )
        .join(Unit, AnalysisRecord.unit_id == Unit.id)
        .where(AnalysisRecord.user_id == user_id)
        .order_by(AnalysisRecord.recorded_at.desc(), AnalysisRecord.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [tuple(row) for row in session.exec(statement).all()]


def list_unit_rankings(
    session: Session, user_id: int
) -> list[tuple[int, str, str, Decimal, int]]:
    # 順位は、保存済み得点率の平均を小数第1位に丸めた値で決める。
    # 同率は同順位で、次の順位を飛ばす（1位・1位・3位。DB設計「苦手単元ランキング」）。
    average = func.round(func.avg(AnalysisRecord.score_rate), 1)
    unit_rank = func.rank().over(order_by=average.asc()).label("unit_rank")
    statement = (
        select(
            unit_rank,
            Unit.code,
            Unit.name,
            average.label("average_score_rate"),
            func.count(AnalysisRecord.id),
        )
        .join(Unit, AnalysisRecord.unit_id == Unit.id)
        .where(AnalysisRecord.user_id == user_id)
        .group_by(Unit.id, Unit.code, Unit.name)
        .order_by(unit_rank, Unit.code)
    )
    return [tuple(row) for row in session.exec(statement).all()]


def insert_analysis_record(session: Session, record: AnalysisRecord) -> None:
    """Add an analysis record without committing."""
    session.add(record)
    # 制約違反を、commitの前（同じトランザクションの中）で検出する。
    session.flush()
