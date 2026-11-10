from sqlalchemy import BigInteger, Column, Identity, String
from sqlmodel import Field, SQLModel


class Unit(SQLModel, table=True):
    __tablename__ = "units"

    id: int | None = Field(
        default=None, sa_column=Column(BigInteger, Identity(), primary_key=True)
    )
    code: str = Field(sa_column=Column(String(50), nullable=False, unique=True))
    name: str = Field(sa_column=Column(String(100), nullable=False, unique=True))
