"""Fix atlas_fund_signal_unified recommendation vocabulary.

The view previously emitted Recommended / Hold / Avoid.
The frontend uses Recommended / Hold / Reduce / Exit throughout
(FundIntelligencePanel distribution, RecommendationChip, FundDecisionHistory,
FundGlossary, buildSingleFundCommentary). "Avoid" is not in any of those
surfaces so it was rendered as raw text and never counted in distribution bars.

This migration remaps:
  DISLOCATION_SUSPENDED -> Exit      (worst case: full dislocation)
  Deteriorating composition OR
    Weak-Holdings                  -> Reduce   (one or more lenses failing)
  All others                       -> Hold / Recommended (unchanged)

Revision ID: 091_fund_recommendation_enum_fix
Revises: 090_legacy_validation_kind
Create Date: 2026-05-20
"""

from alembic import op

revision = "091_fund_recommendation_enum_fix"
down_revision = "090_legacy_validation_kind"
branch_labels = None
depends_on = None


_UPGRADE_VIEW = """
CREATE OR REPLACE VIEW atlas.atlas_fund_signal_unified AS
SELECT
    v.mstar_id,
    v.date,
    v.composition_state,
    v.holdings_state,
    v.pct_holdings_stage_2,
    v.pct_holdings_stage_3,
    v.pct_holdings_stage_4,
    v.mean_within_state_rank,
    v.n_holdings,
    d.nav_state,
    d.nav_state_as_of,
    CASE
        WHEN d.nav_state = 'DISLOCATION_SUSPENDED'           THEN 'Exit'
        WHEN v.composition_state = 'Deteriorating'
          OR v.holdings_state    = 'Weak-Holdings'           THEN 'Reduce'
        WHEN v.composition_state = 'Aligned'
         AND v.holdings_state    = 'Strong-Holdings'
         AND d.nav_state IN ('Leader NAV', 'Strong NAV')     THEN 'Recommended'
        ELSE 'Hold'
    END AS recommendation
FROM atlas.atlas_fund_state_v2 v
LEFT JOIN atlas.atlas_fund_states_daily d
       ON d.mstar_id = v.mstar_id
      AND d.date     = v.date
"""

# Downgrade restores the old Avoid vocabulary.
_DOWNGRADE_VIEW = """
CREATE OR REPLACE VIEW atlas.atlas_fund_signal_unified AS
SELECT
    v.mstar_id,
    v.date,
    v.composition_state,
    v.holdings_state,
    v.pct_holdings_stage_2,
    v.pct_holdings_stage_3,
    v.pct_holdings_stage_4,
    v.mean_within_state_rank,
    v.n_holdings,
    d.nav_state,
    d.nav_state_as_of,
    CASE
        WHEN d.nav_state = 'DISLOCATION_SUSPENDED'           THEN 'Avoid'
        WHEN v.composition_state = 'Deteriorating'
          OR v.holdings_state    = 'Weak-Holdings'           THEN 'Avoid'
        WHEN v.composition_state = 'Aligned'
         AND v.holdings_state    = 'Strong-Holdings'
         AND d.nav_state IN ('Leader NAV', 'Strong NAV')     THEN 'Recommended'
        ELSE 'Hold'
    END AS recommendation
FROM atlas.atlas_fund_state_v2 v
LEFT JOIN atlas.atlas_fund_states_daily d
       ON d.mstar_id = v.mstar_id
      AND d.date     = v.date
"""


def upgrade() -> None:
    op.execute(_UPGRADE_VIEW)


def downgrade() -> None:
    op.execute(_DOWNGRADE_VIEW)
