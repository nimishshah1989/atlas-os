"""create strategy_overlap_daily

Revision ID: 017
Revises: 016
Create Date: 2026-05-08 00:00:00.000000

Stores Jaccard similarity between every strategy pair daily.
105 rows/day (C(15,2)). Python MUST sort pair UUIDs so str(a) < str(b)
before insert — the CHECK constraint is just a safety net.
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE atlas.strategy_overlap_daily (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            date DATE NOT NULL,
            strategy_a_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            strategy_b_id UUID NOT NULL REFERENCES atlas.strategy_configs(id),
            jaccard_similarity NUMERIC(6,4) NOT NULL,
            common_instruments INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(date, strategy_a_id, strategy_b_id),
            CHECK (strategy_a_id < strategy_b_id)
        );
        CREATE INDEX idx_overlap_date
            ON atlas.strategy_overlap_daily(date DESC);
        CREATE INDEX idx_overlap_a
            ON atlas.strategy_overlap_daily(strategy_a_id, date DESC);
        CREATE INDEX idx_overlap_b
            ON atlas.strategy_overlap_daily(strategy_b_id, date DESC);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.strategy_overlap_daily"))
