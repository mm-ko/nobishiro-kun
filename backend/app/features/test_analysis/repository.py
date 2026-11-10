"""Database access for the test analysis flow."""

from sqlmodel import Session, select

from app.db.models import Unit


def list_units(session: Session) -> list[Unit]:
    return list(session.exec(select(Unit).order_by(Unit.code)).all())
