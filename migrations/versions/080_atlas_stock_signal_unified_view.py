"""atlas_stock_signal_unified view — derive legacy column names from state engine.

Revision ID: 080
Revises: 079
Create Date: 2026-05-19

This view is the single read surface for every frontend page during the
signal-consolidation burn-in window. It re-derives every legacy column name
(is_investable, rs_state, momentum_state, weinstein_gate_pass) from the
IC-validated state engine (atlas_stock_state_daily, classifier_version=v2.0-validated).

No table writes are changed by this migration — legacy tables continue writing
nightly. Consumers may read from either; this view ensures they read consistent
values. The cutover to state-engine-only nightly writes happens in Phase 8.
"""
from __future__ import annotations

from alembic import op

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_stock_signal_unified AS
        SELECT
            s.instrument_id,
            s.date,
            -- Truth from the new engine
            s.state                                                  AS engine_state,
            s.prior_state,
            s.state_since_date,
            s.dwell_days,
            s.dwell_percentile::float8                               AS dwell_percentile,
            s.urgency_score,
            s.within_state_rank::float8                              AS within_state_rank,
            s.rs_rank_12m::float8                                    AS rs_rank_12m,
            -- Derived legacy column names (every old consumer keeps working)
            NOT (s.state IN ('uninvestable', 'stage_4'))             AS is_investable,
            CASE
                WHEN s.rs_rank_12m >= 0.90 THEN 'Leader'
                WHEN s.rs_rank_12m >= 0.70 THEN 'Strong'
                WHEN s.rs_rank_12m >= 0.30 THEN 'Average'
                WHEN s.rs_rank_12m >= 0.10 THEN 'Weak'
                ELSE 'Laggard'
            END                                                       AS rs_state,
            CASE
                WHEN s.state IN ('stage_2a', 'stage_2b') THEN 'Accelerating'
                WHEN s.state = 'stage_2c'                THEN 'Improving'
                WHEN s.state = 'stage_3'                 THEN 'Deteriorating'
                WHEN s.state = 'stage_4'                 THEN 'Collapsing'
                ELSE 'Flat'
            END                                                       AS momentum_state,
            s.state IN ('stage_1', 'stage_2a', 'stage_2b', 'stage_2c') AS weinstein_gate_pass,
            -- Continuous Tier 4 surfaces
            s.close_vs_sma_50::float8                                AS close_vs_sma_50,
            s.close_vs_sma_150::float8                               AS close_vs_sma_150,
            s.close_vs_sma_200::float8                               AS close_vs_sma_200,
            s.sma_200_slope::float8                                  AS sma_200_slope,
            s.volume_ratio_50d::float8                               AS volume_ratio_50d,
            s.distribution_days,
            s.classifier_version
        FROM atlas.atlas_stock_state_daily s
        WHERE s.classifier_version = 'v2.0-validated'
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS atlas.atlas_stock_signal_unified")
