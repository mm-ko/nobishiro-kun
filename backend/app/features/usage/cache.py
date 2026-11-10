"""Memcached counters for short-term rate limiting (#24)."""

import threading

from pymemcache.client.base import PooledClient
from pymemcache.exceptions import MemcacheError

from app.core.config import settings

# Memcachedが止まっていても、分析を待たせないよう短く打ち切る。
CONNECT_TIMEOUT_SECONDS = 0.5
TIMEOUT_SECONDS = 0.5

_client: PooledClient | None = None
_client_lock = threading.Lock()


class CacheUnavailableError(Exception):
    """Raised when Memcached is not configured or cannot be reached."""


def increment_counter(key: str, expire_seconds: int) -> int:
    """Add one to the counter for the key and return the new count."""
    try:
        client = _get_client()
        # 最初の呼び出しだけ 0 で作る。すでにあれば何もしない。
        # PooledClient は操作ごとに接続を借り直すため、応答を待たないと、
        # 別の接続の incr が作成より先に届き、数え漏れが起きる（PR #150 のレビュー）。
        client.add(key, b"0", expire=expire_seconds, noreply=False)
        count = client.incr(key, 1)
    except (MemcacheError, OSError) as exc:
        raise CacheUnavailableError("Memcached is unavailable.") from exc
    if count is None:
        # 作成の直後に消えたなど、数えられなかった。1回目として通すと
        # 数えないまま通してしまうため、接続できないときと同じ扱いにする。
        raise CacheUnavailableError("Memcached counter was not found.")
    return count


def _get_client() -> PooledClient:
    global _client

    # FastAPIは def のエンドポイントを別スレッドで動かすため、スレッドで共有できる
    # PooledClient を1つだけ作って使い回す。
    with _client_lock:
        if _client is None:
            if not settings.memcached_host or not settings.memcached_port:
                raise CacheUnavailableError("Memcached is not configured.")
            _client = PooledClient(
                (settings.memcached_host, settings.memcached_port),
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                timeout=TIMEOUT_SECONDS,
            )
        return _client
