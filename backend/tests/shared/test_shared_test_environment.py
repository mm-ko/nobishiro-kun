import asyncio
import socket
from unittest.mock import Mock

import httpx
import psycopg
import pytest
from sqlalchemy import create_engine

from app.core.config import settings


def test_external_service_settings_are_not_inherited() -> None:
    assert settings.app_env == "production"
    assert settings.dev_fixed_user_enabled is False
    for name in (
        "database_url",
        "firebase_credentials_path",
        "openrouter_api_key",
        "memcached_host",
        "stripe_secret_key",
        "stripe_webhook_secret",
    ):
        assert getattr(settings, name) is None


@pytest.mark.parametrize("host", ["192.0.2.1", "127.0.0.1", "::1"])
@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_real_socket_connections_are_blocked(host: str, method: str) -> None:
    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    with socket.socket(family) as connection:
        with pytest.raises(pytest.fail.Exception, match="Real network access"):
            getattr(connection, method)((host, 443))


def test_dns_and_datagram_network_access_are_blocked() -> None:
    with pytest.raises(pytest.fail.Exception, match="Real network access"):
        socket.getaddrinfo("openrouter.test", 443)
    with socket.socket(type=socket.SOCK_DGRAM) as connection:
        with pytest.raises(pytest.fail.Exception, match="Real network access"):
            connection.sendto(b"dummy", ("192.0.2.1", 443))


def test_real_http_request_is_blocked() -> None:
    with httpx.Client(trust_env=False) as client:
        with pytest.raises(pytest.fail.Exception, match="Real network access"):
            client.get("https://openrouter.test", timeout=1)


@pytest.mark.parametrize("entrypoint", ["module", "class"])
def test_postgresql_connections_are_blocked_before_native_driver(
    monkeypatch: pytest.MonkeyPatch, entrypoint: str
) -> None:
    native_connect = Mock(side_effect=AssertionError("Native driver was reached."))
    monkeypatch.setattr(psycopg.Connection, "_connect_gen", native_connect)
    connect = psycopg.connect if entrypoint == "module" else psycopg.Connection.connect

    with pytest.raises(pytest.fail.Exception, match="Real network access"):
        connect(hostaddr="127.0.0.1", connect_timeout=1)

    native_connect.assert_not_called()


def test_async_postgresql_connection_is_blocked_before_native_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native_connect = Mock(side_effect=AssertionError("Native driver was reached."))
    monkeypatch.setattr(psycopg.AsyncConnection, "_connect_gen", native_connect)

    with pytest.raises(pytest.fail.Exception, match="Real network access"):
        asyncio.run(
            psycopg.AsyncConnection.connect(hostaddr="127.0.0.1"),
            loop_factory=asyncio.SelectorEventLoop,
        )

    native_connect.assert_not_called()


def test_sqlalchemy_postgresql_connection_is_blocked_before_native_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native_connect = Mock(side_effect=AssertionError("Native driver was reached."))
    monkeypatch.setattr(psycopg.Connection, "_connect_gen", native_connect)
    engine = create_engine(
        "postgresql+psycopg://", connect_args={"hostaddr": "127.0.0.1"}
    )
    try:
        with pytest.raises(pytest.fail.Exception, match="Real network access"):
            with engine.connect():
                pytest.fail("Unexpected PostgreSQL connection.")
    finally:
        engine.dispose()

    native_connect.assert_not_called()


def test_socketpair_for_in_process_test_clients_still_works() -> None:
    sender, receiver = socket.socketpair()
    with sender, receiver:
        sender.sendall(b"dummy")
        assert receiver.recv(5) == b"dummy"
