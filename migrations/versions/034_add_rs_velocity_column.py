"""SP02: add rs_velocity column to atlas_sector_metrics_daily.

rs_velocity = rate of change of bottomup_rs_3m_nifty500 over a 4-week
(28 calendar day) rolling window. Computed nightly by atlas/compute/sectors.py
after the existing bottom-up aggregation. NULL until the next pipeline run.

Window length is tunable via atlas_thresholds key 'rs_velocity_window_days'
(default 28). Precision NUMERIC(10, 6) matches other ratio columns in this table.

Revision ID: 034
Revises: 033
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_sector_metrics_daily
        ADD COLUMN IF NOT EXISTS rs_velocity NUMERIC(10, 6)
    """))

    # Index for the materialized view mv_sector_rotation_state which filters
    # on velocity sign — partial index on non-NULL rows only.
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_sector_metrics_rs_velocity
        ON atlas.atlas_sector_metrics_daily (sector_name, date DESC)
        WHERE rs_velocity IS NOT NULL
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        DROP INDEX IF EXISTS atlas.idx_sector_metrics_rs_velocity
    """))
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_sector_metrics_daily
        DROP COLUMN IF EXISTS rs_velocity
    """))
