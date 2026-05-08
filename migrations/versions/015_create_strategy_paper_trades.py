"""create strategy_paper_trades

Revision ID: 015
Revises: 014
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_paper_trades (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            instrument_id TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            action TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            price NUMERIC(20,4) NOT NULL,
            weight_pct NUMERIC(10,4) NOT NULL,
            notional_value NUMERIC(20,4) NOT NULL,
            trade_date DATE NOT NULL,
            regime_at_trade TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_paper_trades_strategy_date
            ON atlas.strategy_paper_trades(strategy_id, trade_date DESC);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_paper_trades"))
