"""Database access for subscriptions and processed Stripe events."""

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.db.models import StripeWebhookEvent, Subscription
from app.features.payment.schemas import SubscriptionSnapshot

# 月額プランとして使える状態（#10：Stripeのサブスクリプションが active）
ACTIVE_STATUS = "active"
# Stripeで終わった状態。ここから active などへ戻ることはない。
TERMINAL_STATUSES = ("canceled", "incomplete_expired")


def get_current_subscription(session: Session, user_id: int) -> Subscription | None:
    """Return the user's active subscription, or the newest one if none is active."""
    # 解約した2つ目の契約のほうが新しい場合も、使える契約を返すため active を優先する。
    statement = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(
            case((Subscription.status == ACTIVE_STATUS, 0), else_=1),
            Subscription.created_at.desc(),
            Subscription.id.desc(),
        )
    )
    return session.exec(statement).first()


def exists_active_subscription(session: Session, user_id: int) -> bool:
    statement = select(Subscription.id).where(
        Subscription.user_id == user_id, Subscription.status == ACTIVE_STATUS
    )
    return session.exec(statement).first() is not None


def list_active_subscription_ids(
    session: Session, user_id: int, excluded_subscription_id: str | None = None
) -> list[str]:
    """Return the user's subscriptions that the DB records as active."""
    statement = select(Subscription.stripe_subscription_id).where(
        Subscription.user_id == user_id,
        Subscription.status == ACTIVE_STATUS,
    )
    if excluded_subscription_id is not None:
        statement = statement.where(
            Subscription.stripe_subscription_id != excluded_subscription_id
        )
    return list(session.exec(statement).all())


def lock_user_plan(session: Session, user_id: int) -> None:
    """Wait until no other transaction is handling the same user's monthly plan."""
    # commit・rollback で外れるロック。契約ごとのロックと番号が重ならないよう、
    # 先頭に用途を付けてから番号にする。
    statement = select(func.pg_advisory_xact_lock(func.hashtext(f"plan:{user_id}")))
    session.execute(statement)


def lock_subscription(session: Session, stripe_subscription_id: str) -> None:
    """Wait until no other transaction is handling the same subscription."""
    # commit・rollback で外れるロック。行がまだない新しい契約にも効く。
    # 別の契約が同じ番号になった場合は待つだけで、結果は変わらない。
    statement = select(
        func.pg_advisory_xact_lock(func.hashtext(stripe_subscription_id))
    )
    session.execute(statement)


def exists_webhook_event(session: Session, event_id: str) -> bool:
    statement = select(StripeWebhookEvent.id).where(
        StripeWebhookEvent.event_id == event_id
    )
    return session.exec(statement).first() is not None


def insert_webhook_event_if_absent(
    session: Session, event_id: str, event_type: str
) -> bool:
    """Record the event without committing. Return False if it was already there."""
    # 同じ通知が同時に2回届いても、片方だけが記録されるよう、DBのUNIQUE制約で判定する。
    statement = (
        insert(StripeWebhookEvent)
        .values(event_id=event_id, event_type=event_type)
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(StripeWebhookEvent.id)
    )
    return session.execute(statement).scalar_one_or_none() is not None


def upsert_subscription(
    session: Session, user_id: int, snapshot: SubscriptionSnapshot
) -> None:
    """Add the subscription, or update it if Stripe already sent it. No commit."""
    # 同じStripe契約は既存行を更新し、再加入などの新しい契約は別の行にする
    # （DB設計 3章）。契約者（user_id）は更新しない。
    values = {
        "status": snapshot.status,
        "current_period_start": snapshot.current_period_start,
        "current_period_end": snapshot.current_period_end,
    }
    statement = (
        insert(Subscription)
        .values(
            user_id=user_id,
            stripe_subscription_id=snapshot.stripe_subscription_id,
            **values,
        )
        .on_conflict_do_update(
            index_elements=["stripe_subscription_id"],
            set_={**values, "updated_at": func.now()},
            # 終わった状態の契約は、待っていた処理が持つ古い active で上書きしない
            # （WebhookとCheckoutが同時に動いた場合。PR #147 のレビュー）。
            where=Subscription.status.not_in(TERMINAL_STATUSES),
        )
    )
    session.execute(statement)
