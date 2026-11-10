import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import get_session
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.usage import repository as usage_repository
from app.features.usage import service as usage_service
from app.features.usage.router import router
from app.shared.exceptions import AppError, register_exception_handlers

# 日本時間 2026/10/25 14:30
NOW = datetime(2026, 10, 25, 5, 30, tzinfo=UTC)


class UsageLimitTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.enterContext(patch.object(settings, "monthly_analysis_limit", 10))
        self.count = self.enterContext(patch.object(usage_repository, "count_usages"))
        self.is_paid = self.enterContext(
            patch.object(usage_service.payment_service, "has_active_subscription")
        )

    def usage(self, used_count, is_paid):
        self.count.return_value = used_count
        self.is_paid.return_value = is_paid
        return usage_service.get_usage(self.session, 7, NOW)

    def test_blocked_reason_follows_free_quota_plan_and_monthly_limit(self):
        # (当月の回数, 有料か, 分析できない理由)
        cases = [
            (0, False, None),
            (1, False, None),
            (2, False, "plan_required"),
            (2, True, None),
            (9, True, None),
            (10, True, "monthly_limit_reached"),
            # 月の上限は、契約の有無にかかわらず優先する。
            (10, False, "monthly_limit_reached"),
        ]
        for used_count, is_paid, blocked_reason in cases:
            with self.subTest(used_count=used_count, is_paid=is_paid):
                usage = self.usage(used_count, is_paid)

                self.assertEqual(usage.blocked_reason, blocked_reason)
                self.assertEqual(usage.can_analyze, blocked_reason is None)
                self.assertEqual(usage.used_count, used_count)
                self.assertEqual(usage.free_limit, 2)

    def test_monthly_limit_comes_from_settings(self):
        with patch.object(settings, "monthly_analysis_limit", 5):
            self.assertEqual(
                self.usage(5, True).blocked_reason, "monthly_limit_reached"
            )
            self.assertIsNone(self.usage(4, True).blocked_reason)

    def test_check_raises_403_with_the_reason_code(self):
        cases = [
            (2, False, "PLAN_REQUIRED"),
            (10, True, "MONTHLY_LIMIT_REACHED"),
            (10, False, "MONTHLY_LIMIT_REACHED"),
        ]
        for used_count, is_paid, code in cases:
            with self.subTest(used_count=used_count, is_paid=is_paid):
                self.count.return_value = used_count
                self.is_paid.return_value = is_paid

                with self.assertRaises(AppError) as raised:
                    usage_service.check_remaining_usage(self.session, 7, NOW)

                self.assertEqual(raised.exception.status_code, 403)
                self.assertEqual(raised.exception.code, code)

    def test_check_passes_when_the_user_can_analyze(self):
        self.count.return_value = 1
        self.is_paid.return_value = False

        usage_service.check_remaining_usage(self.session, 7, NOW)

    def test_counts_this_month_in_japan_time(self):
        self.usage(0, False)

        self.count.assert_called_once_with(
            self.session,
            7,
            datetime(2026, 9, 30, 15, 0, tzinfo=UTC),
            datetime(2026, 10, 31, 15, 0, tzinfo=UTC),
        )

    def test_lock_usage_takes_the_users_lock(self):
        lock = self.enterContext(patch.object(usage_repository, "lock_user_usage"))

        usage_service.lock_usage(self.session, 7)

        lock.assert_called_once_with(self.session, 7)

    def test_save_time_check_rejects_the_second_of_two_concurrent_analyses(self):
        # 残り1回で2つ同時に分析した。先の保存が確定したあと、ロックの中で
        # 数え直すと、後の保存は上限を超える。
        self.enterContext(patch.object(usage_repository, "lock_user_usage"))
        cases = [
            (1, 2, False, "PLAN_REQUIRED"),
            (9, 10, True, "MONTHLY_LIMIT_REACHED"),
        ]
        for before, after, is_paid, code in cases:
            with self.subTest(code=code):
                self.count.side_effect = [before, after]
                self.is_paid.return_value = is_paid

                usage_service.check_remaining_usage(self.session, 7, NOW)
                usage_service.lock_usage(self.session, 7)
                with self.assertRaises(AppError) as raised:
                    usage_service.check_remaining_usage(self.session, 7, NOW)

                self.assertEqual(raised.exception.code, code)


class CurrentMonthRangeTests(unittest.TestCase):
    def test_month_changes_at_midnight_in_japan(self):
        cases = [
            # 日本時間 10/31 23:59 は10月
            (
                datetime(2026, 10, 31, 14, 59, tzinfo=UTC),
                datetime(2026, 9, 30, 15, 0, tzinfo=UTC),
                datetime(2026, 10, 31, 15, 0, tzinfo=UTC),
            ),
            # 日本時間 11/1 0:00 は11月
            (
                datetime(2026, 10, 31, 15, 0, tzinfo=UTC),
                datetime(2026, 10, 31, 15, 0, tzinfo=UTC),
                datetime(2026, 11, 30, 15, 0, tzinfo=UTC),
            ),
            # 日本時間 1/1 0:00 は年が変わる
            (
                datetime(2026, 12, 31, 15, 0, tzinfo=UTC),
                datetime(2026, 12, 31, 15, 0, tzinfo=UTC),
                datetime(2027, 1, 31, 15, 0, tzinfo=UTC),
            ),
        ]
        for now, start, end in cases:
            with self.subTest(now=now):
                self.assertEqual(usage_service.current_month_range(now), (start, end))

    def test_usage_saved_last_month_is_not_counted_this_month(self):
        # 日本時間 10/31 23:59 の利用は、11月の範囲に入らない。
        start, _ = usage_service.current_month_range(
            datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
        )
        self.assertLess(datetime(2026, 10, 31, 14, 59, tzinfo=UTC), start)


class UsageRouterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=7, firebase_uid="usage-test-user", created_at=datetime.now(UTC)
        )
        # 本物のDBには接続しない。
        app.dependency_overrides[get_session] = lambda: MagicMock()
        self.client = TestClient(app)
        self.enterContext(
            patch.object(usage_repository, "count_usages", return_value=2)
        )
        self.enterContext(
            patch.object(
                usage_service.payment_service,
                "has_active_subscription",
                return_value=False,
            )
        )

    def test_returns_usage_in_the_api_design_shape(self):
        response = self.client.get("/v1/usage")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "can_analyze": False,
                "used_count": 2,
                "free_limit": 2,
                "blocked_reason": "plan_required",
            },
        )

    def test_requires_authentication(self):
        self.client.app.dependency_overrides.pop(get_current_user)

        response = self.client.get("/v1/usage")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
