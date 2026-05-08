"""create strategy_fm_custom_portfolios + backfill FK on backtest_results

Revision ID: 020
Revises: 019
Create Date: 2026-05-08 00:00:00.000000

Creates the FM custom portfolio table, then adds the FK from
strategy_backtest_results.custom_portfolio_id -> this table.
FK is added via op.create_foreign_key() after the referent table exists.
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_fm_custom_portfolios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            instruments JSONB NOT NULL,
            backtest_id UUID REFERENCES atlas.strategy_backtest_results(id),
            paper_trading_active BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (paper_trading_active = FALSE OR backtest_id IS NOT NULL)
        )
    """))
    # Add FK from backtest_results.custom_portfolio_id -> this table
    op.create_foreign_key(
        "fk_backtest_custom_portfolio",
        "strategy_backtest_results",
        "strategy_fm_custom_portfolios",
        ["custom_portfolio_id"],
        ["id"],
        source_schema="atlas",
        referent_schema="atlas",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_backtest_custom_portfolio",
        "strategy_backtest_results",
        schema="atlas",
        type_="foreignkey",
    )
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_fm_custom_portfolios"))
