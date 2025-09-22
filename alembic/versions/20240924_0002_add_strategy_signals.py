"""add strategy signal history table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20240924_0002"
down_revision = "20240922_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False, index=True),
        sa.Column("signal_type", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("strength", sa.Numeric(10, 4), nullable=False),
        sa.Column("rsi", sa.Numeric(10, 4), nullable=True),
        sa.Column("atr", sa.Numeric(24, 8), nullable=True),
        sa.Column("volume_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("risk_amount", sa.Numeric(24, 8), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_strategy_signals_symbol_created_at",
        "strategy_signals",
        ["symbol", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_signals_symbol_created_at", table_name="strategy_signals")
    op.drop_table("strategy_signals")
