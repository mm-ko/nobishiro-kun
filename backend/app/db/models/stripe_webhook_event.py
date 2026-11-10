from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Identity, String, func
from sqlmodel import Field, SQLModel


class StripeWebhookEvent(SQLModel, table=True):
    """A Stripe event that has already been applied, to skip redeliveries."""

    __tablename__ = "stripe_webhook_events"

    id: int | None = Field(
        default=None, sa_column=Column(BigInteger, Identity(), primary_key=True)
    )
    event_id: str = Field(sa_column=Column(String(255), nullable=False, unique=True))
    event_type: str = Field(sa_column=Column(String(255), nullable=False))
    processed_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
