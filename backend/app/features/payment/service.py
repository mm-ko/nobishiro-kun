"""Payment service: monthly plan checkout, plan status, and Stripe webhooks."""

import logging

from fastapi import status
from sqlmodel import Session

from app.features.payment import client as stripe_client
from app.features.payment import repository as payment_repository
from app.features.payment.schemas import (
    CheckoutSessionResponse,
    CurrentSubscriptionResponse,
    SubscriptionSnapshot,
    WebhookEvent,
)
from app.shared.exceptions import AppError

PAYMENT_SERVICE_UNAVAILABLE_ERROR_CODE = "PAYMENT_SERVICE_UNAVAILABLE"
INVALID_WEBHOOK_SIGNATURE_ERROR_CODE = "INVALID_WEBHOOK_SIGNATURE"
ALREADY_SUBSCRIBED_ERROR_CODE = "ALREADY_SUBSCRIBED"

# 月額プランの判定は、請求書ではなくサブスクリプションの状態で行う（#10）。
HANDLED_EVENT_TYPES = frozenset(
    {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }
)

logger = logging.getLogger(__name__)


def has_active_subscription(session: Session, user_id: int) -> bool:
    """Return whether the user has a monthly plan that is active now."""
    return payment_repository.exists_active_subscription(session, user_id)


def create_checkout_session(session: Session, user_id: int) -> CheckoutSessionResponse:
    """Start a Checkout for the monthly plan, unless the user already has one."""
    # 同じ人のCheckoutの作成を1件ずつ進め、開いているCheckoutを常に1つにする。
    # 2つのタブで別々に支払って、契約が2つできるのを防ぐ（PR #147 のレビュー）。
    payment_repository.lock_user_plan(session, user_id)
    try:
        # DBの active だけで断ると、解約の通知を取りこぼしたときに再契約できなくなる。
        if _is_any_active_on_stripe(session, user_id):
            # 同じ人が2つ契約しないようにする（10/24 みなみさんと合意）。
            raise AppError(
                status.HTTP_409_CONFLICT,
                ALREADY_SUBSCRIBED_ERROR_CODE,
                "すでに月額プランをご利用中です。",
            )
        try:
            stripe_client.expire_open_checkout_sessions(user_id)
            checkout_url = stripe_client.create_checkout_session(user_id)
        except (
            stripe_client.StripeConfigurationError,
            stripe_client.StripeRequestError,
        ) as exc:
            raise _payment_unavailable_error() from exc
        # Stripeの最新にそろえた契約の状態を保存し、ロックを外す。
        session.commit()
    finally:
        # 途中で失敗したときは取り消してロックを外す
        # （成功時は commit 済みで何もしない）。
        session.rollback()
    return CheckoutSessionResponse(checkout_url=checkout_url)


def get_current_subscription(
    session: Session, user_id: int
) -> CurrentSubscriptionResponse:
    """Return the user's usable subscription, so the screen can refresh after paying."""
    subscription = payment_repository.get_current_subscription(session, user_id)
    if subscription is None:
        return CurrentSubscriptionResponse(
            is_subscribed=False, status=None, current_period_end=None
        )
    return CurrentSubscriptionResponse(
        is_subscribed=subscription.status == payment_repository.ACTIVE_STATUS,
        status=subscription.status,
        current_period_end=subscription.current_period_end,
    )


def handle_webhook(session: Session, payload: bytes, signature: str | None) -> None:
    """Verify a Stripe webhook and apply it at most once."""
    try:
        event = stripe_client.verify_webhook_event(payload, signature)
    except stripe_client.StripeConfigurationError as exc:
        raise _payment_unavailable_error() from exc
    except stripe_client.StripeSignatureError as exc:
        # 署名を確かめられない通知は、内容を一切使わずに拒否する。
        raise AppError(
            status.HTTP_400_BAD_REQUEST,
            INVALID_WEBHOOK_SIGNATURE_ERROR_CODE,
            "通知の署名を確認できませんでした。",
        ) from exc

    if event.api_version != stripe_client.SDK_API_VERSION:
        # 版が違うと項目の場所が変わることがあるため、気づけるように残す。
        logger.warning(
            "Stripe event API version %s differs from SDK version %s.",
            event.api_version,
            stripe_client.SDK_API_VERSION,
        )

    if event.type not in HANDLED_EVENT_TYPES or event.object_id is None:
        return
    if payment_repository.exists_webhook_event(session, event.id):
        return

    _apply_subscription_event(session, event)


def _apply_subscription_event(session: Session, event: WebhookEvent) -> None:
    # 同じ契約の通知が同時に届いても、取り直しから保存までを1件ずつ進める。
    # 取り直しと保存の間に別の通知が割り込むと、先に取得した古い状態
    # （解約前の active など）で、新しい状態を上書きしてしまうため。
    payment_repository.lock_subscription(session, event.object_id)

    # 通知は順番どおりに届くとは限らないため、通知の中身ではなく、
    # Stripeから取り直した最新の状態を保存する。
    try:
        snapshot = stripe_client.retrieve_subscription(event.object_id)
    except (
        stripe_client.StripeConfigurationError,
        stripe_client.StripeRequestError,
    ) as exc:
        # ほかの通知を待たせないよう、ロックをすぐに外す。
        session.rollback()
        # 5xxを返すと、Stripeが時間をおいて同じ通知を送り直す。
        raise _payment_unavailable_error() from exc

    is_new_event = payment_repository.insert_webhook_event_if_absent(
        session, event.id, event.type
    )
    if not is_new_event:
        # ロックを待つあいだに、同じ通知が先に記録された場合
        session.rollback()
        return
    if snapshot.user_id is None:
        # アプリのCheckout以外で作られた契約。送り直されても同じなので記録だけ残す。
        logger.warning(
            "Stripe subscription event %s has no app user_id; skipped.", event.id
        )
    else:
        # 同じ人の2つ目の契約の判定と保存を、1件ずつ進める。
        payment_repository.lock_user_plan(session, snapshot.user_id)
        if snapshot.status == payment_repository.ACTIVE_STATUS and (
            _is_any_active_on_stripe(
                session, snapshot.user_id, snapshot.stripe_subscription_id
            )
        ):
            snapshot = _cancel_second_subscription(session, snapshot)
        payment_repository.upsert_subscription(session, snapshot.user_id, snapshot)
    # 通知の記録と契約の更新は、両方保存するか、両方保存しない。
    session.commit()


def _is_any_active_on_stripe(
    session: Session, user_id: int, excluded_subscription_id: str | None = None
) -> bool:
    """Return whether a subscription the DB records as active is active on Stripe now.

    Subscriptions that are no longer active on Stripe are updated in the session.
    """
    active_ids = payment_repository.list_active_subscription_ids(
        session, user_id, excluded_subscription_id
    )
    for subscription_id in active_ids:
        # 通知は順番どおりに届かず、取りこぼすこともあるため、
        # DBの active が古いことがある。解約済みの契約を理由に断ったり
        # 解約したりしないよう、Stripeで確かめる。
        try:
            latest = stripe_client.retrieve_subscription(subscription_id)
        except (
            stripe_client.StripeConfigurationError,
            stripe_client.StripeRequestError,
        ) as exc:
            session.rollback()
            raise _payment_unavailable_error() from exc
        if latest.status == payment_repository.ACTIVE_STATUS:
            return True
        # 遅れている通知を待たず、DBも最新の状態にそろえる。その契約のロックは取らない
        # （その契約の通知とロックを待ち合わないため。どちらもStripeの最新を書く）。
        payment_repository.upsert_subscription(session, user_id, latest)
    return False


def _cancel_second_subscription(
    session: Session, snapshot: SubscriptionSnapshot
) -> SubscriptionSnapshot:
    # Checkoutを失効させても、支払いの直後で通知が届く前に新しいCheckoutから
    # 支払われると、契約が2つになりうる。先の契約を残し、後から来たほうを解約する。
    # テストモードのため返金はしない（本番で使う場合は返金も必要）。
    try:
        cancelled = stripe_client.cancel_subscription(snapshot.stripe_subscription_id)
    except (
        stripe_client.StripeConfigurationError,
        stripe_client.StripeRequestError,
    ) as exc:
        # 通知を記録せずに5xxを返し、Stripeの送り直しでもう一度解約を試す。
        session.rollback()
        raise _payment_unavailable_error() from exc
    logger.warning(
        "Cancelled a second active subscription %s for one user.",
        snapshot.stripe_subscription_id,
    )
    return cancelled


def _payment_unavailable_error() -> AppError:
    return AppError(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        PAYMENT_SERVICE_UNAVAILABLE_ERROR_CODE,
        "ただいま決済を利用できません。",
    )
