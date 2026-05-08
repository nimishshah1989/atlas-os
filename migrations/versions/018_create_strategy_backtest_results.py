"""create strategy_backtest_results

Revision ID: 018
Revises: 017
Create Date: 2026-05-08 00:00:00.000000

custom_portfolio_id has no FK here — FK is added in migration 020
after atlas.strategy_fm_custom_portfolios is created.
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_backtest_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID REFERENCES atlas.strategy_configs(id),
            custom_portfolio_id UUID,
            backtest_type TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            sharpe_ratio NUMERIC(10,4),
            max_drawdown NUMERIC(10,4),
            total_return NUMERIC(10,4),
            alpha_vs_nifty500 NUMERIC(10,4),
            alpha_vs_naive_atlas NUMERIC(10,4),
            walk_forward_oos_sharpe NUMERIC(10,4),
            regime_breakdown JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_backtest_strategy
            ON atlas.strategy_backtest_results(strategy_id)
            WHERE strategy_id IS NOT NULL;
        CREATE INDEX idx_backtest_custom
            ON atlas.strategy_backtest_results(custom_portfolio_id)
            WHERE custom_portfolio_id IS NOT NULL;
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_backtest_results"))
