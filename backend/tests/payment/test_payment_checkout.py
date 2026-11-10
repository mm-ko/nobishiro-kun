import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.config import settings
from app.db.models import Subscription
from app.db.session import get_session
from app.features.auth import repository as auth_repository
from app.features.auth.dependencies import get_firebase_user
from app.features.auth.schemas import AuthenticatedUser, CurrentUser
from app.features.payment import client as stripe_client
from app.features.payment import repository as payment_repository
from app.features.payment.router import router
from app.features.payment.schemas import SubscriptionSnapshot
from app.shared.exceptions import register_exception_handlers

# テスト用のダミー値。本物の鍵・価格IDではない。
CHECKOUT_SETTINGS = {
    "stripe_secret_key": "sk_test_x",
    "stripe_price_id": "price_test_monthly",
    "stripe_success_url": "http://localhost:3000/plan/result?status=success",
    "stripe_cancel_url": "http://localhost:3000/plan/result?status=cancel",
}
CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_dummy"


def make_snapshot(status: str) -> SubscriptionSnapshot:
    return SubscriptionSnapshot(
        stripe_subscription_id="sub_test_1",
        status=status,
        user_id=7,
        current_period_start=datetime(2026, 10, 25, tzinfo=UTC),
        current_period_end=datetime(2026, 11, 25, tzinfo=UTC),
    )


def make_subscription(status: str) -> Subscription:
    return Subscription(
        id=1,
        user_id=7,
        stripe_subscription_id="sub_test_1",
        status=status,
        current_period_start=datetime(2026, 10, 25, tzinfo=UTC),
        current_period_end=datetime(2026, 11, 25, tzinfo=UTC),
    )


class PaymentRouterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        self.session = MagicMock()
        app.dependency_overrides[get_session] = lambda: self.session
        self.app = app
        self.client = TestClient(app)
        self.enterContext(patch.object(settings, "dev_fixed_user_enabled", False))
        self.mock_user = self.enterContext(
            patch.object(auth_repository, "get_user_by_firebase_uid")
        )
        self.mock_user.return_value = CurrentUser(
            id=7, firebase_uid="payment-test-user", created_at=datetime.now(UTC)
        )
        self.active_ids = self.enterContext(
            patch.object(
                payment_repository, "list_active_subscription_ids", return_value=[]
            )
        )
        self.retrieve = self.enterContext(
            patch.object(stripe_client, "retrieve_subscription")
        )
        self.upsert = self.enterContext(
            patch.object(payment_repository, "upsert_subscription")
        )
        self.latest = self.enterContext(
            patch.object(
                payment_repository, "get_current_subscription", return_value=None
            )
        )
        self.create_checkout = self.enterContext(
            patch.object(
                stripe_client, "create_checkout_session", return_value=CHECKOUT_URL
            )
        )
        self.expire_open = self.enterContext(
            patch.object(stripe_client, "expire_open_checkout_sessions", return_value=0)
        )
        self.lock = self.enterContext(
            patch.object(payment_repository, "lock_user_plan")
        )

    def log_in(self):
        self.app.dependency_overrides[get_firebase_user] = lambda: AuthenticatedUser(
            firebase_uid="payment-test-user"
        )

    def test_checkout_returns_url_for_logged_in_user(self):
        self.log_in()

        response = self.client.post("/v1/billing/checkout-sessions")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"checkout_url": CHECKOUT_URL})
        self.create_checkout.assert_called_once_with(7)

    def test_checkout_ignores_plan_sent_by_frontend(self):
        self.log_in()

        self.client.post(
            "/v1/billing/checkout-sessions",
            json={"price": "price_other", "user_id": 99},
        )

        # 価格とユーザーはBEで決めるため、本文の値は使わない。
        self.create_checkout.assert_called_once_with(7)

    def stripe_says(self, status: str):
        self.retrieve.return_value = make_snapshot(status)

    def test_checkout_is_rejected_when_active_on_stripe(self):
        self.log_in()
        self.active_ids.return_value = ["sub_test_1"]
        self.stripe_says("active")

        response = self.client.post("/v1/billing/checkout-sessions")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "ALREADY_SUBSCRIBED")
        self.retrieve.assert_called_once_with("sub_test_1")
        self.expire_open.assert_not_called()
        self.create_checkout.assert_not_called()
        self.session.commit.assert_not_called()
        # 断る場合も、ユーザーごとのロックを外している。
        self.session.rollback.assert_called_once_with()

    def test_checkout_proceeds_when_db_active_is_already_cancelled_on_stripe(self):
        # 解約の通知を取りこぼして、DBにだけ active が残っている場合
        self.log_in()
        self.active_ids.return_value = ["sub_test_1"]
        self.stripe_says("canceled")

        response = self.client.post("/v1/billing/checkout-sessions")

        self.assertEqual(response.status_code, 201)
        # DBをStripeの最新にそろえて保存してから、新しいCheckoutを返す。
        self.upsert.assert_called_once_with(self.session, 7, self.retrieve.return_value)
        self.create_checkout.assert_called_once_with(7)
        self.session.commit.assert_called_once_with()

    def test_checkout_returns_503_when_active_contract_cannot_be_checked(self):
        self.log_in()
        self.active_ids.return_value = ["sub_test_1"]
        self.retrieve.side_effect = stripe_client.StripeRequestError("down")

        response = self.client.post("/v1/billing/checkout-sessions")

        self.assertEqual(response.status_code, 503)
        self.create_checkout.assert_not_called()
        self.session.commit.assert_not_called()

    def test_checkout_expires_open_checkouts_under_lock_before_creating(self):
        self.log_in()
        calls = []
        self.lock.side_effect = lambda *args: calls.append("lock")
        self.active_ids.side_effect = lambda *args: calls.append("check") or []
        self.expire_open.side_effect = lambda *args: calls.append("expire") or 1
        self.create_checkout.side_effect = lambda *args: (
            calls.append("create") or CHECKOUT_URL
        )
        self.session.commit.side_effect = lambda: calls.append("commit")

        self.client.post("/v1/billing/checkout-sessions")

        # 開いているCheckoutを常に1つにし、2つのタブで別々に支払えないようにする。
        self.assertEqual(calls, ["lock", "check", "expire", "create", "commit"])
        self.lock.assert_called_once_with(self.session, 7)
        self.active_ids.assert_called_once_with(self.session, 7, None)
        self.expire_open.assert_called_once_with(7)

    def test_checkout_returns_503_when_stripe_is_not_configured(self):
        self.log_in()
        self.create_checkout.side_effect = stripe_client.StripeConfigurationError()

        response = self.client.post("/v1/billing/checkout-sessions")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"], "PAYMENT_SERVICE_UNAVAILABLE"
        )

    def test_payment_apis_require_login(self):
        for method, path in (
            ("post", "/v1/billing/checkout-sessions"),
            ("get", "/v1/subscriptions/current"),
        ):
            with self.subTest(path=path):
                response = getattr(self.client, method)(path)

                self.assertEqual(response.status_code, 401)
        self.create_checkout.assert_not_called()

    def test_current_subscription_without_contract(self):
        self.log_in()

        response = self.client.get("/v1/subscriptions/current")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"is_subscribed": False, "status": None, "current_period_end": None},
        )
        self.latest.assert_called_once_with(self.session, 7)

    def test_current_subscription_when_active(self):
        self.log_in()
        self.latest.return_value = make_subscription("active")

        response = self.client.get("/v1/subscriptions/current")

        self.assertEqual(
            response.json(),
            {
                "is_subscribed": True,
                "status": "active",
                "current_period_end": "2026-11-25T00:00:00Z",
            },
        )

    def test_current_subscription_is_not_paid_unless_active(self):
        self.log_in()
        for status in ("canceled", "past_due", "incomplete"):
            with self.subTest(status=status):
                self.latest.return_value = make_subscription(status)

                body = self.client.get("/v1/subscriptions/current").json()

                self.assertFalse(body["is_subscribed"])
                self.assertEqual(body["status"], status)


class CreateCheckoutSessionClientTests(unittest.TestCase):
    def setUp(self):
        for name, value in CHECKOUT_SETTINGS.items():
            self.enterContext(patch.object(settings, name, value))
        stripe_client_class = self.enterContext(
            patch.object(stripe_client.stripe, "StripeClient")
        )
        self.create = stripe_client_class.return_value.v1.checkout.sessions.create
        self.create.return_value = MagicMock(url=CHECKOUT_URL)

    def test_creates_monthly_subscription_checkout_with_app_user_id(self):
        url = stripe_client.create_checkout_session(7)

        self.assertEqual(url, CHECKOUT_URL)
        params = self.create.call_args.kwargs["params"]
        self.assertEqual(params["mode"], "subscription")
        self.assertEqual(
            params["line_items"], [{"price": "price_test_monthly", "quantity": 1}]
        )
        self.assertEqual(params["success_url"], CHECKOUT_SETTINGS["stripe_success_url"])
        self.assertEqual(params["cancel_url"], CHECKOUT_SETTINGS["stripe_cancel_url"])
        # Webhook（PR①）が契約とユーザーを結びつけるのに使う。
        self.assertEqual(params["subscription_data"], {"metadata": {"user_id": "7"}})

    def test_requires_all_checkout_settings(self):
        for name in CHECKOUT_SETTINGS:
            with self.subTest(setting=name), patch.object(settings, name, None):
                with self.assertRaises(stripe_client.StripeConfigurationError):
                    stripe_client.create_checkout_session(7)
        self.create.assert_not_called()

    def test_wraps_stripe_errors(self):
        self.create.side_effect = stripe.APIConnectionError("down")

        with self.assertRaises(stripe_client.StripeRequestError):
            stripe_client.create_checkout_session(7)


class ExpireOpenCheckoutSessionsClientTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(settings, "stripe_secret_key", "sk_test_x"))
        stripe_client_class = self.enterContext(
            patch.object(stripe_client.stripe, "StripeClient")
        )
        sessions = stripe_client_class.return_value.v1.checkout.sessions
        self.list = sessions.list
        self.expire = sessions.expire
        self.list.return_value.auto_paging_iter.return_value = [
            MagicMock(id="cs_test_mine_1", client_reference_id="7"),
            MagicMock(id="cs_test_other", client_reference_id="8"),
            MagicMock(id="cs_test_mine_2", client_reference_id="7"),
        ]

    def test_expires_only_the_users_open_checkouts(self):
        expired_count = stripe_client.expire_open_checkout_sessions(7)

        self.assertEqual(self.list.call_args.kwargs["params"]["status"], "open")
        self.assertEqual(
            [call.args[0] for call in self.expire.call_args_list],
            ["cs_test_mine_1", "cs_test_mine_2"],
        )
        self.assertEqual(expired_count, 2)

    def test_wraps_stripe_errors(self):
        self.expire.side_effect = stripe.InvalidRequestError("not open", "session")

        with self.assertRaises(stripe_client.StripeRequestError):
            stripe_client.expire_open_checkout_sessions(7)

    def test_requires_secret_key(self):
        with patch.object(settings, "stripe_secret_key", None):
            with self.assertRaises(stripe_client.StripeConfigurationError):
                stripe_client.expire_open_checkout_sessions(7)
        self.list.assert_not_called()


class SubscriptionQueryTests(unittest.TestCase):
    def test_checkout_lock_key_is_per_user(self):
        session = MagicMock()

        payment_repository.lock_user_plan(session, 7)

        statement = session.execute.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn("pg_advisory_xact_lock(hashtext(", str(compiled))
        self.assertEqual(list(compiled.params.values()), ["plan:7"])

    def test_active_ids_without_exclusion_look_at_all_the_users_active_contracts(
        self,
    ):
        session = MagicMock()

        payment_repository.list_active_subscription_ids(session, 7)

        statement = session.exec.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertNotIn("stripe_subscription_id != ", str(compiled))
        self.assertEqual(sorted(map(str, compiled.params.values())), ["7", "active"])

    def test_active_check_looks_only_at_the_users_active_contracts(self):
        session = MagicMock()

        payment_repository.exists_active_subscription(session, 7)

        statement = session.exec.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn("subscriptions.user_id = ", str(compiled))
        self.assertIn("subscriptions.status = ", str(compiled))
        self.assertEqual(sorted(map(str, compiled.params.values())), ["7", "active"])

    def test_current_subscription_prefers_active_over_newer_cancelled(self):
        session = MagicMock()

        payment_repository.get_current_subscription(session, 7)

        statement = session.exec.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        # 解約した2つ目の契約のほうが新しくても、active を先に並べる。
        order_by = sql.split("ORDER BY", 1)[1]
        self.assertLess(
            order_by.index("CASE WHEN (subscriptions.status ="),
            order_by.index("subscriptions.created_at DESC"),
        )


if __name__ == "__main__":
    unittest.main()
