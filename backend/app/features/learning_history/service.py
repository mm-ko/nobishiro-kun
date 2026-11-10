"""Learning history service."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import Session

from app.db.models import AnalysisRecord
from app.features.learning_history import repository as history_repository
from app.features.learning_history.schemas import (
    HistoryItem,
    HistoryResponse,
    HistoryUnit,
    UnitRankingItem,
    UnitRankingResponse,
)


def get_history(
    session: Session, user_id: int, limit: int, offset: int
) -> HistoryResponse:
    # 全件数を数えず、次の1件があるかで続きの有無を判定する。
    records = history_repository.list_analysis_records(
        session, user_id, limit + 1, offset
    )
    items = [
        HistoryItem(
            id=str(record_id),
            recorded_at=recorded_at.astimezone(UTC),
            unit=HistoryUnit(code=code, name=name),
            score=score,
            max_score=max_score,
        )
        for record_id, recorded_at, code, name, score, max_score in records[:limit]
    ]
    return HistoryResponse(
        items=items, limit=limit, offset=offset, has_more=len(records) > limit
    )


def get_unit_rankings(session: Session, user_id: int) -> UnitRankingResponse:
    # 順位・平均・件数はDBで集計済み。ここでは返す形に組み立てるだけにする。
    rows = history_repository.list_unit_rankings(session, user_id)
    return UnitRankingResponse(
        items=[
            UnitRankingItem(
                rank=rank,
                unit=HistoryUnit(code=code, name=name),
                average_score_rate=float(average),
                record_count=record_count,
            )
            for rank, code, name, average, record_count in rows
        ]
    )


def save_analysis(
    session: Session,
    *,
    user_id: int,
    unit_id: int,
    analysis_usage_id: int,
    score: int,
    max_score: int,
    score_rate: Decimal,
    incorrect_question_numbers: list[str],
    analysis_result: dict[str, object],
    comment_title: str,
    comment_body: str,
    recorded_at: datetime,
) -> None:
    """Add the analysis record of a completed analysis. The caller commits."""
    # 利用実績と同じトランザクションで確定するため、ここではcommitしない（DB設計 5章）。
    # 画像・問題文・解答・AIの出力全文は保存しない。
    history_repository.insert_analysis_record(
        session,
        AnalysisRecord(
            user_id=user_id,
            unit_id=unit_id,
            analysis_usage_id=analysis_usage_id,
            score=score,
            max_score=max_score,
            score_rate=score_rate,
            incorrect_question_numbers=incorrect_question_numbers,
            analysis_result=analysis_result,
            comment_title=comment_title,
            comment_body=comment_body,
            recorded_at=recorded_at,
        ),
    )
