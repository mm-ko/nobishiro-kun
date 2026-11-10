"""Database access for app users."""

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.db.models import User


def get_user_by_firebase_uid(session: Session, firebase_uid: str) -> User | None:
    return session.exec(select(User).where(User.firebase_uid == firebase_uid)).first()


def insert_user_if_absent(session: Session, firebase_uid: str) -> bool:
    """Insert the user unless it already exists. Return True if a row was added."""
    # ログイン直後に画面から2回呼ばれても、重複エラーにならないよう、
    # 「なければ追加」をDBに1回で頼む。
    statement = (
        insert(User)
        .values(firebase_uid=firebase_uid)
        .on_conflict_do_nothing(index_elements=["firebase_uid"])
        .returning(User.id)
    )
    return session.execute(statement).scalar_one_or_none() is not None
