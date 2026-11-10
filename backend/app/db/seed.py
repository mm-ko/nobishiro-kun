import sys

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.db.models import Unit
from app.db.session import DatabaseConfigurationError, get_engine

INITIAL_UNITS = (
    {"code": "division", "name": "わり算"},
    {"code": "addition_subtraction_written", "name": "たし算とひき算の筆算"},
)


def seed_units() -> None:
    with Session(get_engine()) as session:
        statement = insert(Unit).values(list(INITIAL_UNITS))
        session.execute(statement.on_conflict_do_nothing(index_elements=["code"]))
        session.commit()


if __name__ == "__main__":
    try:
        seed_units()
    except (DatabaseConfigurationError, SQLAlchemyError):
        sys.exit(
            "単元投入に失敗しました。DB設定・接続・テーブル作成状況を確認してください。"
        )
    print("単元マスタの投入が完了しました。既存の単元は変更していません。")
