"""create strategy_paper_performance

Revision ID: 016
Revises: 015
Create Date: 2026-05-08

"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_paper_performance (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            date DATE NOT NULL,
            total_value NUMERIC(20,4) NOT NULL,
            daily_return NUMERIC(10,6) NOT NULL,
            benchmark_nifty500_return NUMERIC(10,6),
            benchmark_naive_atlas_return NUMERIC(10,6),
            regime TEXT NOT NULL,
            positions_count INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(strategy_id, date)
        );
        CREATE INDEX idx_paper_perf_strategy_date
            ON atlas.strategy_paper_performance(strategy_id, date DESC);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_paper_performance"))
