from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Identity, Index, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlmodel import Field, SQLModel


class AnalysisUsage(SQLModel, table=True):
    __tablename__ = "analysis_usages"
    __table_args__ = (
        Index("ix_analysis_usages_user_counted", "user_id", "counted_at"),
    )

    id: int | None = Field(
        default=None, sa_column=Column(BigInteger, Identity(), primary_key=True)
    )
    user_id: int = Field(
        sa_column=Column(
            BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        )
    )
    analysis_request_id: UUID = Field(
        sa_column=Column(PostgreSQLUUID(as_uuid=True), nullable=False, unique=True)
    )
    counted_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
