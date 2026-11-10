from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel

import app.db.models  # noqa: F401
from alembic import context
from app.db.session import DatabaseConfigurationError, get_engine

target_metadata = SQLModel.metadata


def run_migrations() -> None:
    engine = get_engine()
    if context.is_offline_mode():
        context.configure(
            url=engine.url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()


try:
    run_migrations()
except (DatabaseConfigurationError, SQLAlchemyError):
    raise SystemExit(
        "DB操作に失敗しました。DB設定・接続・適用済みリビジョンを確認してください。"
    ) from None
