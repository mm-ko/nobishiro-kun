"""Stripe API access: webhook signature checks and subscription lookups."""

from datetime import UTC, datetime
from typing import Any

import stripe

from app.core.config import settings
from app.features.payment.schemas import SubscriptionSnapshot, WebhookEvent

# SDKのメジャー版ごとに固定されるAPIバージョン。Webhookもこの版で送られる前提で読む。
SDK_API_VERSION = stripe.api_version


class StripeConfigurationError(Exception):
    """Raised when required Stripe configuration is missing."""


class StripeSignatureError(Exception):
    """Raised when the webhook payload is not signed by Stripe."""


class StripeRequestError(Exception):
    """Raised when a request to the Stripe API fails."""


def verify_webhook_event(payload: bytes, signature: str | None) -> WebhookEvent:
    """Verify the Stripe-Signature header and return the event it signs."""
    if not settings.stripe_webhook_secret:
        raise StripeConfigurationError("STRIPE_WEBHOOK_SECRET is not configured.")
    if not signature:
        raise StripeSignatureError("Stripe-Signature header is missing.")
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError as exc:
        raise StripeSignatureError("Stripe signature is invalid.") from exc
    except ValueError as exc:
        # 署名は通っても、本文がJSONとして読めない場合
        raise StripeSignatureError("Stripe payload is invalid.") from exc

    # このSDKのオブジェクトは dict として読めないため、普通の dict に変えてから読む。
    data_object = event.data.object.to_dict()
    return WebhookEvent(
        id=event.id,
        type=event.type,
        api_version=event.api_version,
        object_id=data_object.get("id"),
    )


def expire_open_checkout_sessions(user_id: int) -> int:
    """Expire the user's Checkout pages that are still open. Return how many."""
    if not settings.stripe_secret_key:
        raise StripeConfigurationError("STRIPE_SECRET_KEY is not configured.")
    client = stripe.StripeClient(settings.stripe_secret_key)
    expired_count = 0
    try:
        # Stripeは開いているCheckoutをユーザーで絞り込めないため、開いているもの全体から
        # client_reference_id で探す。MVPの利用者数を前提にした方法。
        open_sessions = client.v1.checkout.sessions.list(
            params={"status": "open", "limit": 100}
        )
        for checkout_session in open_sessions.auto_paging_iter():
            if checkout_session.client_reference_id != str(user_id):
                continue
            client.v1.checkout.sessions.expire(checkout_session.id)
            expired_count += 1
    except stripe.StripeError as exc:
        raise StripeRequestError("Stripe Checkout session expiration failed.") from exc
    return expired_count


def create_checkout_session(user_id: int) -> str:
    """Create a Checkout page for the monthly plan and return its URL."""
    if not (
        settings.stripe_secret_key
        and settings.stripe_price_id
        and settings.stripe_success_url
        and settings.stripe_cancel_url
    ):
        raise StripeConfigurationError("Stripe Checkout settings are not configured.")
    client = stripe.StripeClient(settings.stripe_secret_key)
    try:
        checkout_session = client.v1.checkout.sessions.create(
            params={
                "mode": "subscription",
                # 月額300円の1プランだけなので、価格はBEで固定し、FEからは受け取らない。
                "line_items": [{"price": settings.stripe_price_id, "quantity": 1}],
                "success_url": settings.stripe_success_url,
                "cancel_url": settings.stripe_cancel_url,
                "client_reference_id": str(user_id),
                # Webhookで、契約とアプリのユーザーを結びつけるために使う。
                "subscription_data": {"metadata": {"user_id": str(user_id)}},
            }
        )
    except stripe.StripeError as exc:
        raise StripeRequestError("Stripe Checkout session creation failed.") from exc
    if not checkout_session.url:
        raise StripeRequestError("Stripe Checkout session has no URL.")
    return checkout_session.url


def retrieve_subscription(subscription_id: str) -> SubscriptionSnapshot:
    """Read the current state of a subscription from Stripe."""
    if not settings.stripe_secret_key:
        raise StripeConfigurationError("STRIPE_SECRET_KEY is not configured.")
    client = stripe.StripeClient(settings.stripe_secret_key)
    try:
        subscription = client.v1.subscriptions.retrieve(subscription_id)
    except stripe.StripeError as exc:
        raise StripeRequestError("Stripe subscription lookup failed.") from exc
    return _to_snapshot(subscription)


def cancel_subscription(subscription_id: str) -> SubscriptionSnapshot:
    """Cancel a subscription now and return its state after cancelling."""
    if not settings.stripe_secret_key:
        raise StripeConfigurationError("STRIPE_SECRET_KEY is not configured.")
    client = stripe.StripeClient(settings.stripe_secret_key)
    try:
        subscription = client.v1.subscriptions.cancel(subscription_id)
    except stripe.StripeError as exc:
        raise StripeRequestError("Stripe subscription cancellation failed.") from exc
    return _to_snapshot(subscription)


def _to_snapshot(subscription: stripe.Subscription) -> SubscriptionSnapshot:
    data = subscription.to_dict()
    # 2025-03-31 以降のAPIバージョンでは、契約期間はサブスクリプションではなく
    # その明細（items）が持つ。月額プランは1明細なので先頭を使う。
    items = (data.get("items") or {}).get("data") or []
    first_item = items[0] if items else {}
    return SubscriptionSnapshot(
        stripe_subscription_id=data["id"],
        status=data["status"],
        user_id=_parse_user_id(data.get("metadata") or {}),
        current_period_start=_to_datetime(first_item.get("current_period_start")),
        current_period_end=_to_datetime(first_item.get("current_period_end")),
    )


def _parse_user_id(metadata: dict[str, Any]) -> int | None:
    value = metadata.get("user_id")
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _to_datetime(timestamp: int | None) -> datetime | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)
