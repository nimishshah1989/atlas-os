"""atlas_sector_signal_unified view — bottom-up sector state read surface.

Reads from atlas_sector_state_v2 (created in migration 081). Returns one row
per (sector, date) with derived sector_state label for frontend consumers.

Until atlas_sector_state_v2 is populated by the nightly aggregator, this view
returns 0 rows safely (empty table, no error).

Revision ID: 084
Revises: 083
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_sector_signal_unified AS
        SELECT
            s.sector,
            s.date,
            s.dominant_state                                              AS engine_state,
            s.dominant_share::float8                                      AS dominant_share,
            s.n_constituents,
            s.mean_within_state_rank::float8                              AS mean_within_state_rank,
            s.pct_stage_2::float8                                         AS pct_stage_2,
            s.pct_stage_3::float8                                         AS pct_stage_3,
            s.pct_stage_4::float8                                         AS pct_stage_4,
            CASE
                WHEN s.pct_stage_2 >= 0.50 THEN 'Overweight'
                WHEN s.pct_stage_4 >= 0.50 THEN 'Avoid'
                WHEN s.pct_stage_3 + s.pct_stage_4 >= 0.50 THEN 'Underweight'
                ELSE 'Neutral'
            END                                                           AS sector_state
        FROM atlas.atlas_sector_state_v2 s
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS atlas.atlas_sector_signal_unified")
