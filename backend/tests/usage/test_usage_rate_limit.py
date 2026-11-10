import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from pymemcache.exceptions import MemcacheUnexpectedCloseError

from app.core.config import settings
from app.features.usage import cache as usage_cache
from app.features.usage import service as usage_service
from app.features.usage.service import RateLimitTarget
from app.shared.exceptions import AppError

NOW = datetime(2026, 10, 25, 5, 30, 15, tzinfo=UTC)


class CheckRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.counts = {}

        def increment(key, expire_seconds):
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        self.increment = self.enterContext(
            patch.object(usage_cache, "increment_counter", side_effect=increment)
        )

    def test_allows_three_calls_a_minute_and_rejects_the_fourth(self):
        for _ in range(3):
            usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        with self.assertRaises(AppError) as raised:
            usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.code, "RATE_LIMIT_EXCEEDED")
        # 05:30:15 なので、次の「分」まで45秒。
        self.assertEqual(raised.exception.headers, {"Retry-After": "45"})

    def test_counts_by_user_target_and_minute(self):
        usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        self.increment.assert_called_once_with("7:analysis_a:202610250530", 120)

    def test_allows_again_in_the_next_minute(self):
        for _ in range(3):
            usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        usage_service.check_rate_limit(
            7, RateLimitTarget.STAGE_A, NOW.replace(minute=31, second=0)
        )

    def test_reading_and_analysis_are_counted_separately(self):
        for _ in range(3):
            usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        # 読み取りを3回したあとでも、分析は別に数えるため通る。
        usage_service.check_rate_limit(7, RateLimitTarget.STAGE_B, NOW)

    def test_other_users_are_counted_separately(self):
        for _ in range(3):
            usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        usage_service.check_rate_limit(8, RateLimitTarget.STAGE_A, NOW)

    def test_allows_and_logs_when_memcached_is_unavailable(self):
        self.increment.side_effect = usage_cache.CacheUnavailableError()

        with self.assertLogs("app.features.usage.service", "WARNING") as logs:
            for _ in range(5):
                usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        self.assertIn("レート制限をせずに通しました", logs.output[0])
        # ユーザーやキーの値はログに残さない。
        self.assertNotIn("7:analysis_a", "".join(logs.output))


class IncrementCounterTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(usage_cache, "_client", None))
        self.enterContext(patch.object(settings, "memcached_host", "memcached"))
        self.enterContext(patch.object(settings, "memcached_port", 11211))
        self.client_class = self.enterContext(patch.object(usage_cache, "PooledClient"))
        self.client = self.client_class.return_value

    def test_creates_counter_with_expiry_and_returns_new_count(self):
        self.client.incr.return_value = 2

        count = usage_cache.increment_counter("7:analysis_a:202610250530", 120)

        self.assertEqual(count, 2)
        # 作成の応答を待ってから数える。
        self.client.add.assert_called_once_with(
            "7:analysis_a:202610250530", b"0", expire=120, noreply=False
        )
        self.client.incr.assert_called_once_with("7:analysis_a:202610250530", 1)
        _, kwargs = self.client_class.call_args
        self.assertEqual(
            (kwargs["connect_timeout"], kwargs["timeout"]),
            (usage_cache.CONNECT_TIMEOUT_SECONDS, usage_cache.TIMEOUT_SECONDS),
        )

    def test_reports_unavailable_when_counter_is_missing(self):
        # 数えられなかったのに1回目として通すと、上限を超えて実行できてしまう。
        self.client.incr.return_value = None

        with self.assertRaises(usage_cache.CacheUnavailableError):
            usage_cache.increment_counter("key", 120)

    def test_reports_unavailable_when_connection_fails(self):
        for error in (
            ConnectionRefusedError(),
            TimeoutError(),
            MemcacheUnexpectedCloseError(),
        ):
            with self.subTest(error=type(error).__name__):
                self.client.add.side_effect = error

                with self.assertRaises(usage_cache.CacheUnavailableError):
                    usage_cache.increment_counter("key", 120)

    def test_reports_unavailable_when_not_configured(self):
        with patch.object(settings, "memcached_host", None):
            with self.assertRaises(usage_cache.CacheUnavailableError):
                usage_cache.increment_counter("key", 120)
        self.client_class.assert_not_called()


class ReorderingMemcache:
    """A stand-in for Memcached reached over several pooled connections.

    An add sent without waiting for the reply (noreply) can arrive after an incr
    sent on another connection. An add that waits for the reply is applied at once.
    """

    def __init__(self):
        self.store = {}
        self.pending_adds = []

    def add(self, key, value, expire=0, noreply=None):
        if noreply is False:
            return self._apply_add(key, value)
        self.pending_adds.append((key, value))
        return True

    def incr(self, key, value, noreply=False):
        count = None
        if key in self.store:
            self.store[key] += value
            count = self.store[key]
        # 応答を待たなかった add は、この incr のあとに届く。
        for pending_key, pending_value in self.pending_adds:
            self._apply_add(pending_key, pending_value)
        self.pending_adds.clear()
        return count

    def _apply_add(self, key, value):
        if key in self.store:
            return False
        self.store[key] = int(value)
        return True


class PooledConnectionsTests(unittest.TestCase):
    """Counts must not be missed across pooled connections (PR #150 review)."""

    def setUp(self):
        self.memcache = ReorderingMemcache()
        self.enterContext(patch.object(usage_cache, "_client", None))
        self.enterContext(patch.object(settings, "memcached_host", "memcached"))
        self.enterContext(patch.object(settings, "memcached_port", 11211))
        self.enterContext(
            patch.object(usage_cache, "PooledClient", return_value=self.memcache)
        )

    def test_every_call_is_counted(self):
        counts = [usage_cache.increment_counter("key", 120) for _ in range(5)]

        # 応答を待たない add だと [1, 1, 2, 3, 4] になり、4回通ってしまう。
        self.assertEqual(counts, [1, 2, 3, 4, 5])

    def test_fourth_call_in_a_minute_is_rejected(self):
        for _ in range(3):
            usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        with self.assertRaises(AppError) as raised:
            usage_service.check_rate_limit(7, RateLimitTarget.STAGE_A, NOW)

        self.assertEqual(raised.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
