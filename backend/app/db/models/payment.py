from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    String,
    func,
)
from sqlmodel import Field, SQLModel


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "current_period_start IS NULL OR current_period_end IS NULL"
            " OR current_period_end > current_period_start",
            name="ck_subscriptions_period",
        ),
    )

    id: int | None = Field(
        default=None, sa_column=Column(BigInteger, Identity(), primary_key=True)
    )
    user_id: int = Field(
        sa_column=Column(
            BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        )
    )
    stripe_subscription_id: str = Field(
        sa_column=Column(String(255), nullable=False, unique=True)
    )
    status: str = Field(sa_column=Column(String(50), nullable=False))
    current_period_start: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    current_period_end: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
