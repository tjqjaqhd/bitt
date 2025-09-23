"""초기 테이블 생성"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20240922_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False, unique=True),
        sa.Column("korean_name", sa.String(length=100), nullable=True),
        sa.Column("english_name", sa.String(length=100), nullable=True),
        sa.Column("warning_level", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("fee", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_trades_order_id", "trades", ["order_id"])
    op.create_index("ix_trades_symbol", "trades", ["symbol"])
    op.create_index("ix_trades_symbol_time", "trades", ["symbol", "executed_at"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False, unique=True),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("avg_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "pnl_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False, unique=True),
        sa.Column("realized_pnl", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("unrealized_pnl", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("total_equity", sa.Numeric(24, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("return_rate", sa.Numeric(10, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "order_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("order_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("order_history")
    op.drop_table("configs")
    op.drop_table("pnl_daily")
    op.drop_table("positions")
    op.drop_index("ix_trades_symbol_time", table_name="trades")
    op.drop_index("ix_trades_symbol", table_name="trades")
    op.drop_index("ix_trades_order_id", table_name="trades")
    op.drop_table("trades")
    op.drop_table("markets")
