import hashlib
import hmac
import json
import threading
import time
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.core.config import settings
from app.db.session import get_session
from app.features.payment import client as stripe_client
from app.features.payment import repository as payment_repository
from app.features.payment import service as payment_service
from app.features.payment.router import router
from app.features.payment.schemas import SubscriptionSnapshot, WebhookEvent
from app.shared.exceptions import register_exception_handlers

# テスト用のダミー値。本物の鍵ではない。
WEBHOOK_SECRET = "whsec_test_dummy"
SUBSCRIPTION = SubscriptionSnapshot(
    stripe_subscription_id="sub_test_1",
    status="active",
    user_id=7,
    current_period_start=datetime(2026, 10, 24, tzinfo=UTC),
    current_period_end=datetime(2026, 11, 24, tzinfo=UTC),
)


def event_payload(
    event_type: str = "customer.subscription.updated",
    api_version: str = stripe_client.SDK_API_VERSION,
) -> bytes:
    return json.dumps(
        {
            "id": "evt_test_1",
            "object": "event",
            "api_version": api_version,
            "type": event_type,
            "data": {"object": {"id": "sub_test_1", "object": "subscription"}},
        }
    ).encode()


def sign(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    # Stripeと同じ方式（タイムスタンプ.本文 のHMAC-SHA256）で署名を作る。
    timestamp = int(time.time())
    signed = f"{timestamp}.{payload.decode()}".encode()
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


class StripeWebhookRouterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        self.session = MagicMock()
        app.dependency_overrides[get_session] = lambda: self.session
        self.client = TestClient(app)
        self.enterContext(
            patch.object(settings, "stripe_webhook_secret", WEBHOOK_SECRET)
        )
        self.retrieve = self.enterContext(
            patch.object(
                stripe_client, "retrieve_subscription", return_value=SUBSCRIPTION
            )
        )
        self.exists = self.enterContext(
            patch.object(payment_repository, "exists_webhook_event", return_value=False)
        )
        self.insert_event = self.enterContext(
            patch.object(
                payment_repository,
                "insert_webhook_event_if_absent",
                return_value=True,
            )
        )
        self.upsert = self.enterContext(
            patch.object(payment_repository, "upsert_subscription")
        )
        self.lock = self.enterContext(
            patch.object(payment_repository, "lock_subscription")
        )
        self.lock_user = self.enterContext(
            patch.object(payment_repository, "lock_user_plan")
        )
        self.other_active_ids = self.enterContext(
            patch.object(
                payment_repository,
                "list_active_subscription_ids",
                return_value=[],
            )
        )
        self.cancel = self.enterContext(
            patch.object(stripe_client, "cancel_subscription")
        )

    def post(self, payload: bytes, signature: str | None):
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers["Stripe-Signature"] = signature
        return self.client.post("/v1/webhooks/stripe", content=payload, headers=headers)

    def assert_nothing_saved(self):
        self.retrieve.assert_not_called()
        self.upsert.assert_not_called()
        self.session.commit.assert_not_called()

    def test_saves_latest_subscription_for_new_event(self):
        payload = event_payload()

        response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"received": True})
        self.retrieve.assert_called_once_with("sub_test_1")
        self.insert_event.assert_called_once_with(
            self.session, "evt_test_1", "customer.subscription.updated"
        )
        self.upsert.assert_called_once_with(self.session, 7, SUBSCRIPTION)
        self.session.commit.assert_called_once_with()

    def test_locks_subscription_before_reading_latest_state(self):
        calls = []
        self.lock.side_effect = lambda *args: calls.append("lock")
        self.retrieve.side_effect = lambda *args: (
            calls.append("retrieve") or (SUBSCRIPTION)
        )
        self.upsert.side_effect = lambda *args: calls.append("save")
        self.session.commit.side_effect = lambda: calls.append("commit")
        payload = event_payload()

        self.post(payload, sign(payload))

        # 取り直しから保存・commit（ロックが外れる）までを、ロックの中で行う。
        self.assertEqual(calls, ["lock", "retrieve", "save", "commit"])
        self.lock.assert_called_once_with(self.session, "sub_test_1")

    def test_rejects_invalid_signature(self):
        payload = event_payload()

        response = self.post(payload, sign(payload, secret="whsec_other"))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_WEBHOOK_SIGNATURE")
        self.assert_nothing_saved()

    def test_rejects_payload_changed_after_signing(self):
        signature = sign(event_payload())

        response = self.post(event_payload("customer.subscription.deleted"), signature)

        self.assertEqual(response.status_code, 400)
        self.assert_nothing_saved()

    def test_rejects_missing_signature(self):
        response = self.post(event_payload(), signature=None)

        self.assertEqual(response.status_code, 400)
        self.assert_nothing_saved()

    def test_returns_503_when_webhook_secret_is_not_configured(self):
        payload = event_payload()
        with patch.object(settings, "stripe_webhook_secret", None):
            response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"], "PAYMENT_SERVICE_UNAVAILABLE"
        )
        self.assert_nothing_saved()

    def test_skips_event_already_processed(self):
        self.exists.return_value = True
        payload = event_payload()

        response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.insert_event.assert_not_called()
        self.assert_nothing_saved()

    def test_skips_event_recorded_by_concurrent_delivery(self):
        self.insert_event.return_value = False
        payload = event_payload()

        response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.upsert.assert_not_called()
        self.session.rollback.assert_called_once_with()
        self.session.commit.assert_not_called()

    def test_ignores_invoice_events(self):
        payload = event_payload("invoice.payment_failed")

        response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.insert_event.assert_not_called()
        self.assert_nothing_saved()

    def test_records_event_without_app_user_id_but_does_not_save_subscription(self):
        self.retrieve.return_value = SUBSCRIPTION.model_copy(update={"user_id": None})
        payload = event_payload()

        response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.insert_event.assert_called_once()
        self.upsert.assert_not_called()
        self.session.commit.assert_called_once_with()

    def test_returns_503_so_stripe_retries_when_lookup_fails(self):
        self.retrieve.side_effect = stripe_client.StripeRequestError("down")
        payload = event_payload()

        response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 503)
        self.insert_event.assert_not_called()
        self.session.commit.assert_not_called()
        # 同じ契約のほかの通知を待たせないよう、ロックを外している。
        self.session.rollback.assert_called_once_with()

    def test_logs_warning_when_event_api_version_differs(self):
        payload = event_payload(api_version="2020-08-27")

        with self.assertLogs("app.features.payment.service", "WARNING") as logs:
            response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.assertIn("2020-08-27", logs.output[0])
        self.upsert.assert_called_once()

    def use_stripe_states(self, states: dict[str, str]):
        # Stripe上の今の状態を、契約IDごとに返す。
        self.retrieve.side_effect = lambda subscription_id: SUBSCRIPTION.model_copy(
            update={
                "stripe_subscription_id": subscription_id,
                "status": states[subscription_id],
            }
        )

    def test_cancels_second_subscription_when_other_is_active_on_stripe(self):
        self.other_active_ids.return_value = ["sub_old"]
        self.use_stripe_states({"sub_test_1": "active", "sub_old": "active"})
        cancelled = SUBSCRIPTION.model_copy(update={"status": "canceled"})
        self.cancel.return_value = cancelled
        payload = event_payload("customer.subscription.created")

        with self.assertLogs("app.features.payment.service", "WARNING"):
            response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.other_active_ids.assert_called_once_with(self.session, 7, "sub_test_1")
        self.retrieve.assert_any_call("sub_old")
        self.cancel.assert_called_once_with("sub_test_1")
        # 先の契約は残し、後から来た契約は解約後の状態で保存する。
        self.upsert.assert_called_once_with(self.session, 7, cancelled)
        self.session.commit.assert_called_once_with()

    def test_keeps_new_subscription_when_old_one_is_already_cancelled_on_stripe(self):
        # 旧契約の解約の通知が遅れて、DBにだけ active が残っている場合
        self.other_active_ids.return_value = ["sub_old"]
        self.use_stripe_states({"sub_test_1": "active", "sub_old": "canceled"})
        payload = event_payload("customer.subscription.created")

        response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.cancel.assert_not_called()
        saved = [
            (call.args[2].stripe_subscription_id, call.args[2].status)
            for call in self.upsert.call_args_list
        ]
        # 旧契約はStripeの最新の状態にそろえ、新しい契約は active のまま保存する。
        self.assertEqual(saved, [("sub_old", "canceled"), ("sub_test_1", "active")])
        self.session.commit.assert_called_once_with()

    def test_returns_503_when_other_subscription_cannot_be_checked(self):
        self.other_active_ids.return_value = ["sub_old"]
        self.retrieve.side_effect = [
            SUBSCRIPTION,
            stripe_client.StripeRequestError("down"),
        ]
        payload = event_payload("customer.subscription.created")

        response = self.post(payload, sign(payload))

        # 確かめられないまま解約しない。通知を記録せず、Stripeの送り直しを待つ。
        self.assertEqual(response.status_code, 503)
        self.cancel.assert_not_called()
        self.upsert.assert_not_called()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_called_once_with()

    def test_checks_for_second_subscription_under_user_lock(self):
        calls = []
        self.lock_user.side_effect = lambda *args: calls.append("lock user")
        self.other_active_ids.side_effect = lambda *args: calls.append("check") or []
        self.upsert.side_effect = lambda *args: calls.append("save")
        self.session.commit.side_effect = lambda: calls.append("commit")
        payload = event_payload()

        self.post(payload, sign(payload))

        # 同じ人の2つの契約の通知が同時に届いても、両方が残らないようにする。
        self.assertEqual(calls, ["lock user", "check", "save", "commit"])
        self.lock_user.assert_called_once_with(self.session, 7)
        self.cancel.assert_not_called()

    def test_does_not_check_others_when_new_subscription_is_not_active(self):
        self.other_active_ids.return_value = ["sub_old"]
        self.retrieve.return_value = SUBSCRIPTION.model_copy(
            update={"status": "canceled"}
        )
        payload = event_payload("customer.subscription.deleted")

        response = self.post(payload, sign(payload))

        self.assertEqual(response.status_code, 200)
        self.other_active_ids.assert_not_called()
        self.cancel.assert_not_called()
        self.upsert.assert_called_once()

    def test_returns_503_without_saving_when_cancel_fails(self):
        self.other_active_ids.return_value = ["sub_old"]
        self.use_stripe_states({"sub_test_1": "active", "sub_old": "active"})
        self.cancel.side_effect = stripe_client.StripeRequestError("down")
        payload = event_payload("customer.subscription.created")

        response = self.post(payload, sign(payload))

        # 通知を記録しないため、Stripeの送り直しでもう一度解約を試す。
        self.assertEqual(response.status_code, 503)
        self.upsert.assert_not_called()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_called_once_with()


class RetrieveSubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(settings, "stripe_secret_key", "sk_test_x"))
        stripe_client_class = self.enterContext(
            patch.object(stripe_client.stripe, "StripeClient")
        )
        self.retrieve = stripe_client_class.return_value.v1.subscriptions.retrieve

    def test_reads_period_from_item_and_user_id_from_metadata(self):
        self.retrieve.return_value = stripe.Subscription.construct_from(
            {
                "id": "sub_test_1",
                "object": "subscription",
                "status": "active",
                "metadata": {"user_id": "7"},
                "items": {
                    "object": "list",
                    "data": [
                        {
                            "id": "si_test_1",
                            "object": "subscription_item",
                            "current_period_start": 1792800000,
                            "current_period_end": 1795478400,
                        }
                    ],
                },
            },
            "sk_test_x",
        )

        snapshot = stripe_client.retrieve_subscription("sub_test_1")

        self.assertEqual(snapshot.stripe_subscription_id, "sub_test_1")
        self.assertEqual(snapshot.status, "active")
        self.assertEqual(snapshot.user_id, 7)
        self.assertEqual(
            snapshot.current_period_start, datetime.fromtimestamp(1792800000, UTC)
        )
        self.assertEqual(
            snapshot.current_period_end, datetime.fromtimestamp(1795478400, UTC)
        )

    def test_wraps_stripe_errors(self):
        self.retrieve.side_effect = stripe.APIConnectionError("down")

        with self.assertRaises(stripe_client.StripeRequestError):
            stripe_client.retrieve_subscription("sub_test_1")

    def test_requires_secret_key(self):
        with patch.object(settings, "stripe_secret_key", None):
            with self.assertRaises(stripe_client.StripeConfigurationError):
                stripe_client.retrieve_subscription("sub_test_1")


class CancelSubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(settings, "stripe_secret_key", "sk_test_x"))
        stripe_client_class = self.enterContext(
            patch.object(stripe_client.stripe, "StripeClient")
        )
        self.cancel = stripe_client_class.return_value.v1.subscriptions.cancel

    def test_returns_state_after_cancelling(self):
        self.cancel.return_value = stripe.Subscription.construct_from(
            {
                "id": "sub_test_2",
                "object": "subscription",
                "status": "canceled",
                "metadata": {"user_id": "7"},
                "items": {"object": "list", "data": []},
            },
            "sk_test_x",
        )

        snapshot = stripe_client.cancel_subscription("sub_test_2")

        self.cancel.assert_called_once_with("sub_test_2")
        self.assertEqual(
            (snapshot.stripe_subscription_id, snapshot.status, snapshot.user_id),
            ("sub_test_2", "canceled", 7),
        )

    def test_wraps_stripe_errors(self):
        self.cancel.side_effect = stripe.APIConnectionError("down")

        with self.assertRaises(stripe_client.StripeRequestError):
            stripe_client.cancel_subscription("sub_test_2")


class UpsertSubscriptionTests(unittest.TestCase):
    def test_second_contract_check_excludes_the_contract_itself(self):
        session = MagicMock()

        payment_repository.list_active_subscription_ids(session, 7, "sub_test_2")

        statement = session.exec.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn("subscriptions.stripe_subscription_id != ", str(compiled))
        self.assertEqual(
            sorted(map(str, compiled.params.values())), ["7", "active", "sub_test_2"]
        )

    def test_keeps_owner_when_same_subscription_is_updated(self):
        session = MagicMock()

        payment_repository.upsert_subscription(session, 7, SUBSCRIPTION)

        statement = session.execute.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("ON CONFLICT (stripe_subscription_id) DO UPDATE SET", sql)
        update_clause = sql.split("DO UPDATE SET", 1)[1]
        self.assertIn("status", update_clause)
        self.assertNotIn("user_id", update_clause)
        session.commit.assert_not_called()

    def test_does_not_update_contract_that_has_already_ended(self):
        session = MagicMock()

        payment_repository.upsert_subscription(session, 7, SUBSCRIPTION)

        statement = session.execute.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        # 既存の行が終わった状態なら更新しない（古い active で上書きしない）。
        where_clause = str(compiled).split("DO UPDATE SET", 1)[1].split("WHERE", 1)[1]
        self.assertIn("subscriptions.status NOT IN", where_clause)
        self.assertIn(["canceled", "incomplete_expired"], compiled.params.values())

    def test_lock_key_is_the_stripe_subscription_id(self):
        session = MagicMock()

        payment_repository.lock_subscription(session, "sub_test_1")

        statement = session.execute.call_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn("pg_advisory_xact_lock(hashtext(", str(compiled))
        self.assertEqual(list(compiled.params.values()), ["sub_test_1"])


class ConcurrentSubscriptionEventTests(unittest.TestCase):
    """Two events for one subscription arrive at the same time (PR #145 review)."""

    def test_older_state_does_not_overwrite_cancellation(self):
        # 本物のDBは使わないため、DBのロックを threading.Lock で置き換え、
        # 「Aが active を取得 → Bが解約後に届く → Aが遅れて保存」の順を再現する。
        db_lock = threading.Lock()
        stripe_state = {"status": "active"}
        saved = []
        a_retrieved = threading.Event()
        b_waiting_for_lock = threading.Event()

        def lock(session, subscription_id):
            if session.name == "B":
                b_waiting_for_lock.set()
            db_lock.acquire()

        def retrieve(subscription_id):
            snapshot = SUBSCRIPTION.model_copy(
                update={"status": stripe_state["status"]}
            )
            if threading.current_thread().name == "A":
                a_retrieved.set()
                # Bが同じ契約の処理を始めるまで、Aの保存を遅らせる。
                b_waiting_for_lock.wait(timeout=5)
            return snapshot

        def new_session(name):
            session = MagicMock(name=name)
            session.name = name
            session.commit.side_effect = db_lock.release
            return session

        def run(name, event_id):
            event = WebhookEvent(
                id=event_id,
                type="customer.subscription.updated",
                api_version=stripe_client.SDK_API_VERSION,
                object_id="sub_test_1",
            )
            payment_service._apply_subscription_event(new_session(name), event)

        with (
            patch.object(payment_repository, "lock_subscription", side_effect=lock),
            patch.object(payment_repository, "lock_user_plan"),
            patch.object(
                payment_repository,
                "list_active_subscription_ids",
                return_value=[],
            ),
            patch.object(stripe_client, "retrieve_subscription", side_effect=retrieve),
            patch.object(
                payment_repository, "insert_webhook_event_if_absent", return_value=True
            ),
            patch.object(
                payment_repository,
                "upsert_subscription",
                side_effect=lambda session, user_id, snapshot: saved.append(
                    snapshot.status
                ),
            ),
        ):
            thread_a = threading.Thread(target=run, args=("A", "evt_a"), name="A")
            thread_a.start()
            self.assertTrue(a_retrieved.wait(timeout=5))
            stripe_state["status"] = "canceled"
            thread_b = threading.Thread(target=run, args=("B", "evt_b"), name="B")
            thread_b.start()
            thread_a.join(timeout=5)
            thread_b.join(timeout=5)

        # BはAの保存を待ってから取り直すため、最後に残るのは解約後の状態。
        self.assertEqual(saved, ["active", "canceled"])


class LateCancellationNoticeTests(unittest.TestCase):
    """The old contract's cancel notice arrives after the new one (PR #147 review)."""

    def test_new_subscription_survives_late_cancel_notice_of_old_one(self):
        # DB（契約ID → 状態）と、Stripe上の今の状態の代わり。
        db = {"sub_old": "active"}
        stripe_now = {"sub_old": "canceled", "sub_new": "active"}

        def retrieve(subscription_id):
            return SUBSCRIPTION.model_copy(
                update={
                    "stripe_subscription_id": subscription_id,
                    "status": stripe_now[subscription_id],
                }
            )

        def other_active_ids(session, user_id, subscription_id):
            return [
                other
                for other, status in db.items()
                if status == "active" and other != subscription_id
            ]

        def upsert(session, user_id, snapshot):
            db[snapshot.stripe_subscription_id] = snapshot.status

        def deliver(event_type, subscription_id):
            event = WebhookEvent(
                id=f"evt_{event_type}_{subscription_id}",
                type=event_type,
                api_version=stripe_client.SDK_API_VERSION,
                object_id=subscription_id,
            )
            payment_service._apply_subscription_event(MagicMock(), event)

        with (
            patch.object(payment_repository, "lock_subscription"),
            patch.object(payment_repository, "lock_user_plan"),
            patch.object(
                payment_repository, "insert_webhook_event_if_absent", return_value=True
            ),
            patch.object(
                payment_repository,
                "list_active_subscription_ids",
                side_effect=other_active_ids,
            ),
            patch.object(payment_repository, "upsert_subscription", side_effect=upsert),
            patch.object(stripe_client, "retrieve_subscription", side_effect=retrieve),
            patch.object(stripe_client, "cancel_subscription") as cancel,
        ):
            # 新しい契約の通知が先に届き、旧契約の解約の通知があとから届く。
            deliver("customer.subscription.created", "sub_new")
            deliver("customer.subscription.deleted", "sub_old")

        cancel.assert_not_called()
        self.assertEqual(db, {"sub_old": "canceled", "sub_new": "active"})


if __name__ == "__main__":
    unittest.main()
