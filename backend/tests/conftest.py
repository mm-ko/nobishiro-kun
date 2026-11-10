import socket
from threading import local

import psycopg
import pytest


def pytest_configure(config: pytest.Config) -> None:
    # テストのimport前に設定し、手元の鍵・接続先をSettingsへ取り込ませない。
    patcher = pytest.MonkeyPatch()
    config.add_cleanup(patcher.undo)
    for name in (
        "DATABASE_URL",
        "FIREBASE_PROJECT_ID",
        "FIREBASE_CREDENTIALS_PATH",
        "FRONTEND_ORIGIN",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "OPENROUTER_TIMEOUT_SECONDS",
        "MEMCACHED_HOST",
        "MEMCACHED_PORT",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_ID",
        "STRIPE_SUCCESS_URL",
        "STRIPE_CANCEL_URL",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        patcher.setenv(name, "")
    patcher.setenv("APP_ENV", "production")
    patcher.setenv("DEV_FIXED_USER_ENABLED", "false")
    patcher.setenv("IMAGE_MAX_BYTES", str(10 * 1024 * 1024))
    patcher.setenv("IMAGE_TOTAL_MAX_BYTES", str(20 * 1024 * 1024))

    def block_network(*args: object, **kwargs: object) -> None:
        pytest.fail(
            "Real network access is disabled. Mock external services.", pytrace=False
        )

    async def block_async_network(*args: object, **kwargs: object) -> None:
        block_network()

    # psycopg[binary]の通信はC側で行われ、Pythonのsocket差し替えを通らない。
    patcher.setattr(psycopg, "connect", block_network)
    patcher.setattr(psycopg.Connection, "connect", classmethod(block_network))
    patcher.setattr(
        psycopg.AsyncConnection, "connect", classmethod(block_async_network)
    )

    socketpair_state = local()
    original_connect = socket.socket.connect
    original_socketpair = socket.socketpair

    def guarded_connect(connection: socket.socket, address: object) -> None:
        if (
            getattr(socketpair_state, "creating", False)
            and isinstance(address, tuple)
            and address[0] in ("127.0.0.1", "::1")
        ):
            return original_connect(connection, address)
        block_network()

    def local_socketpair(*args: object, **kwargs: object) -> tuple:
        # Windowsのasyncio/TestClientはsocketpair内部でloopback接続を作る。
        socketpair_state.creating = True
        try:
            return original_socketpair(*args, **kwargs)
        finally:
            socketpair_state.creating = False

    patcher.setattr(socket, "socketpair", local_socketpair)
    patcher.setattr(socket.socket, "connect", guarded_connect)
    for name in ("connect_ex", "sendto"):
        patcher.setattr(socket.socket, name, block_network)
    if hasattr(socket.socket, "sendmsg"):
        patcher.setattr(socket.socket, "sendmsg", block_network)
    for name in (
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
    ):
        patcher.setattr(socket, name, block_network)
