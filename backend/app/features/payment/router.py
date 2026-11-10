from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlmodel import Session

from app.db.session import get_session
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.payment import service as payment_service
from app.features.payment.schemas import (
    CheckoutSessionResponse,
    CurrentSubscriptionResponse,
    WebhookResponse,
)

router = APIRouter(prefix="/v1", tags=["payment"])


@router.post(
    "/billing/checkout-sessions",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_checkout_session(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> CheckoutSessionResponse:
    return payment_service.create_checkout_session(session, current_user.id)


@router.get("/subscriptions/current", response_model=CurrentSubscriptionResponse)
def read_current_subscription(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> CurrentSubscriptionResponse:
    return payment_service.get_current_subscription(session, current_user.id)


async def read_raw_body(request: Request) -> bytes:
    # 署名は受け取ったままのバイト列で確かめるため、JSONとして読む前の本文が要る。
    # 本文はasyncでしか読めないので、この依存関係だけasyncにする
    # （中で同期処理は呼ばない）。
    return await request.body()


# Stripeからの通知。Firebaseの認証は通さず、Stripeの署名で送り主を確かめる。
@router.post("/webhooks/stripe", response_model=WebhookResponse)
def receive_stripe_webhook(
    payload: Annotated[bytes, Depends(read_raw_body)],
    session: Annotated[Session, Depends(get_session)],
    stripe_signature: Annotated[str | None, Header()] = None,
) -> WebhookResponse:
    payment_service.handle_webhook(session, payload, stripe_signature)
    return WebhookResponse(received=True)
