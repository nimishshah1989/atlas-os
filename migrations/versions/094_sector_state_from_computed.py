"""sector_state column on atlas_sector_state_v2 + update unified view.

Wave 4A Task 3: sector_state is now computed cross-sectionally by the
sector aggregation Python code (hybrid rank + breadth floor) and stored
as a column in atlas_sector_state_v2. The atlas_sector_signal_unified
view is updated to read that column directly instead of deriving
sector_state via an absolute CASE on pct_stage_2.

This removes the "all Neutral in thin-breadth markets" bug: in a market
where no sector clears pct_stage_2 >= 0.50, the old CASE returned Neutral
for every sector. The hybrid ranker always produces a spread.

Adds:
  atlas.atlas_sector_state_v2.sector_state  VARCHAR(12) NULLABLE
      (NULL until the next nightly compute run populates it; NOT NULL
       constraint is omitted intentionally — backfilling all history
       before adding the constraint is an EC2-side deferred step.)

Recreates:
  atlas.atlas_sector_signal_unified  — identical to migration 084 except
      sector_state is taken from the table column (COALESCE to 'Neutral'
      for any rows that pre-date the first hybrid-compute run).

Revision ID: 094_sector_state_from_computed
Revises: 093_portfolio_targets_holdings
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "094_sector_state_from_computed"
down_revision = "093_portfolio_targets_holdings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add sector_state column to the aggregate table.
    #    Nullable so existing rows (pre-Task3 compute) are not rejected.
    op.add_column(
        "atlas_sector_state_v2",
        sa.Column("sector_state", sa.String(12), nullable=True),
        schema="atlas",
    )

    # 2. Recreate the unified view so sector_state is read from the column.
    #    COALESCE to 'Neutral' for rows that pre-date the hybrid compute run.
    #
    #    IMPORTANT: The live view (as of migration 087's hotfix) has numeric(6,4)
    #    columns for dominant_share, mean_within_state_rank, pct_stage_2/3/4.
    #    The original 084 body cast those to ::float8, but Postgres rejected that
    #    replacement on EC2 because CREATE OR REPLACE VIEW cannot change existing
    #    column types.  We reproduce the LIVE column types exactly — no ::float8
    #    casts — so CREATE OR REPLACE succeeds.  The only change versus the live
    #    view is the sector_state expression: CASE replaced by COALESCE(column).
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_sector_signal_unified AS
        SELECT
            s.sector,
            s.date,
            s.dominant_state                                              AS engine_state,
            s.dominant_share,
            s.n_constituents,
            s.mean_within_state_rank,
            s.pct_stage_2,
            s.pct_stage_3,
            s.pct_stage_4,
            COALESCE(s.sector_state, 'Neutral')                           AS sector_state
        FROM atlas.atlas_sector_state_v2 s
    """)


def downgrade() -> None:
    # Restore the live view's original sector_state expression (the CASE on
    # pct_stage_2/3/4).  Column types are kept identical to the live view —
    # no ::float8 casts — so CREATE OR REPLACE succeeds on downgrade too.
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_sector_signal_unified AS
        SELECT
            s.sector,
            s.date,
            s.dominant_state                                              AS engine_state,
            s.dominant_share,
            s.n_constituents,
            s.mean_within_state_rank,
            s.pct_stage_2,
            s.pct_stage_3,
            s.pct_stage_4,
            CASE
                WHEN s.pct_stage_2 >= 0.50 THEN 'Overweight'
                WHEN s.pct_stage_4 >= 0.50 THEN 'Avoid'
                WHEN s.pct_stage_3 + s.pct_stage_4 >= 0.50 THEN 'Underweight'
                ELSE 'Neutral'
            END                                                           AS sector_state
        FROM atlas.atlas_sector_state_v2 s
    """)

    # Remove the sector_state column added by upgrade.
    op.drop_column("atlas_sector_state_v2", "sector_state", schema="atlas")
