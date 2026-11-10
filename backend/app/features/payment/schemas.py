"""Payment request and response schemas."""

from datetime import datetime

from pydantic import BaseModel


class WebhookEvent(BaseModel):
    """The parts of a verified Stripe event that the app uses."""

    id: str
    type: str
    api_version: str | None
    object_id: str | None


class SubscriptionSnapshot(BaseModel):
    """The latest state of a Stripe subscription, read from Stripe."""

    stripe_subscription_id: str
    status: str
    # Checkoutを作るときに metadata へ入れたアプリのユーザーID（#25 PR②）
    user_id: int | None
    current_period_start: datetime | None
    current_period_end: datetime | None


class WebhookResponse(BaseModel):
    received: bool


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class CurrentSubscriptionResponse(BaseModel):
    is_subscribed: bool
    # Stripeのサブスクリプションの状態をそのまま返す。契約がなければ null
    status: str | None
    current_period_end: datetime | None
