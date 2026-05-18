"""atlas_fund_signal_unified view — fund composition + nav state read surface.

Reads from atlas_fund_state_v2 (created in migration 082) and LEFT JOINs to
atlas_fund_states_daily for nav_state + nav_state_as_of. The LEFT JOIN means
funds without a legacy nav_state entry still appear (nav columns = NULL).

The recommendation column derives the 3-way Avoid/Recommended/Hold signal
from composition_state, holdings_state, and nav_state in one place, so no
frontend code needs to re-implement the lookup table.

Revision ID: 085
Revises: 084
Create Date: 2026-05-19
"""
from __future__ import annotations

from alembic import op

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_fund_signal_unified AS
        SELECT
            fv.mstar_id,
            fv.date,
            fv.composition_state,
            fv.holdings_state,
            fv.pct_holdings_stage_2::float8      AS pct_holdings_stage_2,
            fv.pct_holdings_stage_3::float8      AS pct_holdings_stage_3,
            fv.pct_holdings_stage_4::float8      AS pct_holdings_stage_4,
            fv.mean_within_state_rank::float8    AS mean_within_state_rank,
            fv.n_holdings,
            nav.nav_state,
            nav.nav_state_as_of,
            CASE
                WHEN nav.nav_state = 'DISLOCATION_SUSPENDED'  THEN 'Avoid'
                WHEN fv.composition_state = 'Deteriorating'
                     OR fv.holdings_state  = 'Weak-Holdings'  THEN 'Avoid'
                WHEN fv.composition_state = 'Aligned'
                     AND fv.holdings_state = 'Strong-Holdings'
                     AND nav.nav_state IN ('Leader NAV','Strong NAV') THEN 'Recommended'
                ELSE 'Hold'
            END AS recommendation
        FROM atlas.atlas_fund_state_v2 fv
        LEFT JOIN atlas.atlas_fund_states_daily nav
          ON nav.mstar_id = fv.mstar_id
         AND nav.date     = fv.date
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS atlas.atlas_fund_signal_unified")
