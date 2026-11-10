"""共通テーブルと分析記録の参照先を作成する。"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_common_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("firebase_uid", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "units",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
    )
    op.create_table(
        "analysis_usages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "analysis_request_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "counted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_analysis_usages_user_counted", "analysis_usages", ["user_id", "counted_at"]
    )
    op.create_table(
        "analysis_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            sa.BigInteger(),
            sa.ForeignKey("units.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "analysis_usage_id",
            sa.BigInteger(),
            sa.ForeignKey("analysis_usages.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("score_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "incorrect_question_numbers",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("analysis_result", postgresql.JSONB(), nullable=False),
        sa.Column("comment_title", sa.Text(), nullable=False),
        sa.Column("comment_body", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "score_rate >= 0 AND score_rate <= 100", name="ck_score_rate"
        ),
        sa.CheckConstraint("max_score > 0", name="ck_max_score"),
        sa.CheckConstraint("score >= 0 AND score <= max_score", name="ck_score"),
    )
    op.create_index(
        "ix_analysis_records_user_recorded",
        "analysis_records",
        ["user_id", "recorded_at"],
    )
    op.create_index(
        "ix_analysis_records_user_unit", "analysis_records", ["user_id", "unit_id"]
    )


def downgrade() -> None:
    op.drop_table("analysis_records")
    op.drop_table("analysis_usages")
    op.drop_table("units")
    op.drop_table("users")
