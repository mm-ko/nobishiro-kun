"""月額プランの契約と、処理済みのStripe通知を記録するテーブルを作成する。"""

import sqlalchemy as sa

from alembic import op

revision = "0002_payment_tables"
down_revision = "0001_common_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "stripe_subscription_id", sa.String(255), nullable=False, unique=True
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "current_period_start IS NULL OR current_period_end IS NULL"
            " OR current_period_end > current_period_start",
            name="ck_subscriptions_period",
        ),
    )
    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("event_id", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("stripe_webhook_events")
    op.drop_table("subscriptions")
