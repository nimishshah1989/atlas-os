"""atlas_etf_signal_unified view — ETF aggregate state read surface.

Reads from atlas_etf_state_v2 (created in migration 083). Returns one row
per (etf_ticker, date) with dominant state and weighted RS metrics.

Until atlas_etf_state_v2 is populated by the nightly aggregator, this view
returns 0 rows safely (empty table, no error).

Revision ID: 086
Revises: 085
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_etf_signal_unified AS
        SELECT
            e.etf_ticker,
            e.date,
            e.dominant_state             AS engine_state,
            e.dominant_share::float8     AS dominant_share,
            e.n_holdings,
            e.mean_rs_rank_12m::float8   AS mean_rs_rank_12m,
            e.pct_stage_2::float8        AS pct_stage_2,
            e.pct_stage_3::float8        AS pct_stage_3,
            e.pct_stage_4::float8        AS pct_stage_4
        FROM atlas.atlas_etf_state_v2 e
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS atlas.atlas_etf_signal_unified")
