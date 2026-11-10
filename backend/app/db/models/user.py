from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Identity, String, func
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(
        default=None, sa_column=Column(BigInteger, Identity(), primary_key=True)
    )
    firebase_uid: str = Field(
        sa_column=Column(String(128), nullable=False, unique=True)
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        ),
    )
