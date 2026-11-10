from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError
from sqlmodel import Session, create_engine

from app.core.config import settings


class DatabaseConfigurationError(RuntimeError):
    """DB設定が未指定、または対応していない形式である。"""


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    if not settings.database_url:
        raise DatabaseConfigurationError("DATABASE_URL is required.")
    try:
        url = make_url(settings.database_url)
    except (ArgumentError, ValueError):
        raise DatabaseConfigurationError("Invalid DATABASE_URL format.") from None
    if url.drivername != "postgresql+psycopg":
        raise DatabaseConfigurationError("DATABASE_URL must use postgresql+psycopg.")
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
