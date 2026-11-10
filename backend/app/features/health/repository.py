import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.db.session import DatabaseConfigurationError, get_engine

logger = logging.getLogger(__name__)


def is_database_available() -> bool:
    try:
        with Session(get_engine()) as session:
            return session.execute(text("SELECT 1")).scalar_one() == 1
    except (DatabaseConfigurationError, SQLAlchemyError) as exc:
        logger.warning("DB health check failed: %s", type(exc).__name__)
        return False
