from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel


class AnalysisRecord(SQLModel, table=True):
    __tablename__ = "analysis_records"
    __table_args__ = (
        CheckConstraint("score_rate >= 0 AND score_rate <= 100", name="ck_score_rate"),
        CheckConstraint("max_score > 0", name="ck_max_score"),
        CheckConstraint("score >= 0 AND score <= max_score", name="ck_score"),
        Index("ix_analysis_records_user_recorded", "user_id", "recorded_at"),
        Index("ix_analysis_records_user_unit", "user_id", "unit_id"),
    )

    id: int | None = Field(
        default=None, sa_column=Column(BigInteger, Identity(), primary_key=True)
    )
    user_id: int = Field(
        sa_column=Column(
            BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        )
    )
    unit_id: int = Field(
        sa_column=Column(
            BigInteger, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
        )
    )
    analysis_usage_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("analysis_usages.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        )
    )
    score: int = Field(sa_column=Column(Integer, nullable=False))
    max_score: int = Field(sa_column=Column(Integer, nullable=False))
    score_rate: Decimal = Field(sa_column=Column(Numeric(5, 2), nullable=False))
    incorrect_question_numbers: list[str] = Field(
        default_factory=list,
        sa_column=Column(
            ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
        ),
    )
    analysis_result: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    comment_title: str = Field(sa_column=Column(Text, nullable=False))
    comment_body: str = Field(sa_column=Column(Text, nullable=False))
    recorded_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
