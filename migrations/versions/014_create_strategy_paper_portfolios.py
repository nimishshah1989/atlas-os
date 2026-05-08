"""create strategy_paper_portfolios

Revision ID: 014
Revises: 013
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_paper_portfolios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            instrument_id TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            weight_pct NUMERIC(10,4) NOT NULL,
            entry_date DATE NOT NULL,
            entry_signal_type TEXT NOT NULL,
            notional_value NUMERIC(20,4) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(strategy_id, instrument_id)
        );
        CREATE INDEX idx_paper_portfolios_strategy
            ON atlas.strategy_paper_portfolios(strategy_id);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_paper_portfolios"))
