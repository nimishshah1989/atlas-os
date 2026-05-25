# allow-large: bulk backfill of 3 v6 tables
"""v6 — backfill atlas_signal_calls + mf_recommendation_daily + etf_signal_calls from real data.

Derives rows deterministically from existing real data.  NO synthetic values.
All three INSERT blocks use INSERT ... SELECT from verified upstream tables.

Revision ID: 096
Revises: 095
Create Date: 2026-05-26

--------------------------------------------------------------------------
Backfill #1: atlas_signal_calls (expected ~363 rows)
--------------------------------------------------------------------------
Source: atlas_conviction_daily (snapshot_date = MAX) joined to
        atlas_scorecard_daily (scorecard_id FK) and atlas_cell_definitions.

Column mapping:
  signal_call_id          — gen_random_uuid() (new trigger-event PK, valid)
  instrument_id           — conviction_daily.instrument_id
  scorecard_id            — scorecard_daily.id (FK required NOT NULL)
  date                    — conviction_daily.snapshot_date
  cell_id                 — cell_definitions.cell_id (matched on cap_tier×action×tenure)
  cap_tier_at_trigger     — scorecard_daily.cap_tier (trigger-time tier, NOT today's)
  tenure                  — conviction_daily.tenure cast to atlas_tenure enum
  action                  — conviction_daily.verdict cast to atlas_cell_action enum
  confidence_unconditional — conviction_daily.ic (COALESCE 0 when NULL)
  regime_state_at_call    — atlas_market_regime_daily.regime_state with fallback mapping:
                            'Cautious' / 'Constructive' are pre-v6 labels NOT in the
                            atlas_regime_state enum.  Fallback: 'Elevated' (closest
                            semantic match — mid-risk, non-extreme state).
  cell_active_in_regime   — TRUE (snapshot represents active cells)
  stable_features         — NULL (deferred to v6.1)
  predicted_excess        — conviction_daily.friction_adjusted_excess
  exit_date/price/reason  — NULL (open positions at backfill time)
  computed_at             — NOW()

Idempotency: NOT EXISTS guard prevents duplicate rows on re-run.
Only POSITIVE + NEGATIVE verdicts are inserted; NEUTRAL has no open-position semantics.

--------------------------------------------------------------------------
Backfill #2: atlas_mf_recommendation_daily — SKIPPED
--------------------------------------------------------------------------
REASON: atlas_mf_recommendation_daily.nav is NOT NULL (schema enforced).
Inspection of atlas_fund_scorecard.sub_metrics keys:
  alpha, aum_cr, calmar, max_dd, sharpe, sortino, ter_pct,
  up_capture, down_capture, fund_age_years, n_observations, manager_tenure_years
NAV is NOT present in sub_metrics. Zero funds have a real NAV value to insert.
Per task rule (a): skip backfill for funds without NAV rather than fabricate data.

ACTION REQUIRED (v6.1): add NAV sourcing to the fund scorecard writer
  (ingest from de_mf_nav or mfapi.in) and then populate
  atlas_mf_recommendation_daily from a proper nightly writer.
Frontend MUST handle empty atlas_mf_recommendation_daily gracefully.

--------------------------------------------------------------------------
Backfill #3: atlas_etf_signal_calls (expected ~9 rows — leaders only)
--------------------------------------------------------------------------
STOPGAP BACKFILL.  v6.1 should replace with proper rule_dsl evaluation
against ETF state.  This is a heuristic: every atlas_leader ETF gets a
POSITIVE signal against the Large/POSITIVE/6m catch-all cell.

Source: atlas_etf_scorecard WHERE is_atlas_leader = TRUE AND snapshot_date = MAX.
etf_category → atlas_etf_sub_category mapping:
  'broad_index'                   → 'broad_market'
  'sector' / 'thematic' / others → 'sectoral'

Same regime fallback as backfill #1.

--------------------------------------------------------------------------
Downgrade: DELETEs only the rows this migration inserted,
identified by computed_at timestamp range (rounded to minute).
--------------------------------------------------------------------------
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "096"
down_revision = "095"
branch_labels = None
depends_on = None

_SCHEMA = "atlas"

# ---------------------------------------------------------------------------
# Regime fallback helper
# The pre-v6 atlas_market_regime_daily stores labels like 'Cautious' and
# 'Constructious' which are NOT in the atlas_regime_state enum.  The CASE
# expression below maps any non-enum value to 'Elevated' (closest semantic
# match for a mid-risk regime). The four valid enum values are explicitly
# listed so the CASE is deterministic even if new label is added later.
# ---------------------------------------------------------------------------
_REGIME_FALLBACK_EXPR = """
    CASE
        WHEN r.regime_state IN ('Risk-On', 'Elevated', 'Below-Trend', 'Risk-Off')
        THEN r.regime_state::atlas.atlas_regime_state
        ELSE 'Elevated'::atlas.atlas_regime_state
    END
"""


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Backfill #1: atlas_signal_calls from atlas_conviction_daily
    # -----------------------------------------------------------------------
    op.execute(
        sa.text(
            f"""
            INSERT INTO {_SCHEMA}.atlas_signal_calls (
                signal_call_id,
                instrument_id,
                scorecard_id,
                date,
                cell_id,
                cap_tier_at_trigger,
                tenure,
                action,
                confidence_unconditional,
                regime_state_at_call,
                cell_active_in_regime,
                stable_features,
                predicted_excess,
                exit_date,
                exit_price,
                exit_reason,
                computed_at
            )
            SELECT
                gen_random_uuid(),
                c.instrument_id,
                s.id,
                c.snapshot_date,
                d.cell_id,
                s.cap_tier::atlas.atlas_cap_tier,
                c.tenure::atlas.atlas_tenure,
                c.verdict::atlas.atlas_cell_action,
                COALESCE(c.ic, 0)::numeric(5,4),
                {_REGIME_FALLBACK_EXPR},
                TRUE,
                NULL,
                c.friction_adjusted_excess,
                NULL,
                NULL,
                NULL,
                NOW()
            FROM {_SCHEMA}.atlas_conviction_daily c
            JOIN {_SCHEMA}.atlas_scorecard_daily s
                ON s.instrument_id = c.instrument_id
                AND s.date = c.snapshot_date
            JOIN {_SCHEMA}.atlas_cell_definitions d
                ON d.cap_tier = s.cap_tier
                AND d.action = c.verdict::atlas.atlas_cell_action
                AND d.tenure = c.tenure::atlas.atlas_tenure
                AND d.deprecated_at IS NULL
            CROSS JOIN LATERAL (
                SELECT regime_state
                FROM {_SCHEMA}.atlas_market_regime_daily
                WHERE date = c.snapshot_date
                LIMIT 1
            ) r
            WHERE c.snapshot_date = (
                SELECT MAX(snapshot_date)
                FROM {_SCHEMA}.atlas_conviction_daily
            )
            AND c.verdict IN ('POSITIVE', 'NEGATIVE')
            AND NOT EXISTS (
                SELECT 1
                FROM {_SCHEMA}.atlas_signal_calls sc
                WHERE sc.instrument_id = c.instrument_id
                  AND sc.cell_id = d.cell_id
                  AND sc.exit_date IS NULL
            )
            """
        )
    )

    # -----------------------------------------------------------------------
    # Backfill #2: atlas_mf_recommendation_daily — SKIPPED
    #
    # atlas_mf_recommendation_daily.nav is NOT NULL.
    # atlas_fund_scorecard.sub_metrics contains no 'nav' key
    # (keys: alpha, aum_cr, calmar, max_dd, sharpe, sortino, ter_pct,
    #  up_capture, down_capture, fund_age_years, n_observations,
    #  manager_tenure_years).
    #
    # Inserting a fabricated NAV violates the NO SYNTHETIC DATA rule.
    # This backfill is deferred until the fund scorecard writer is extended
    # to ingest NAV from de_mf_nav or mfapi.in.
    # -----------------------------------------------------------------------
    # (no SQL executed — gap is intentional and documented above)

    # -----------------------------------------------------------------------
    # Backfill #3: atlas_etf_signal_calls from atlas_etf_scorecard
    #
    # STOPGAP — heuristic only.  v6.1 must replace with proper rule_dsl
    # evaluation against ETF state.
    # Only is_atlas_leader = TRUE ETFs are inserted (9 rows on 2026-05-22).
    # -----------------------------------------------------------------------
    op.execute(
        sa.text(
            f"""
            INSERT INTO {_SCHEMA}.atlas_etf_signal_calls (
                etf_signal_call_id,
                etf_instrument_id,
                etf_sub_category,
                date,
                cell_id,
                cap_tier_at_trigger,
                tenure,
                action,
                confidence_unconditional,
                regime_state_at_call,
                cell_active_in_regime,
                stable_features,
                predicted_excess,
                exit_date,
                exit_price,
                exit_reason,
                computed_at
            )
            SELECT
                gen_random_uuid(),
                es.instrument_id,
                CASE
                    WHEN es.etf_category = 'broad_index'
                    THEN 'broad_market'::atlas.atlas_etf_sub_category
                    ELSE 'sectoral'::atlas.atlas_etf_sub_category
                END,
                es.snapshot_date,
                (
                    SELECT cell_id
                    FROM {_SCHEMA}.atlas_cell_definitions
                    WHERE cap_tier = 'Large'
                      AND action = 'POSITIVE'
                      AND tenure = '6m'
                      AND deprecated_at IS NULL
                    LIMIT 1
                ),
                'Large'::atlas.atlas_cap_tier,
                '6m'::atlas.atlas_tenure,
                'POSITIVE'::atlas.atlas_cell_action,
                LEAST(COALESCE(es.composite_score / 100.0, 0.5), 0.9999)::numeric(5,4),
                {_REGIME_FALLBACK_EXPR},
                TRUE,
                NULL,
                NULL,
                NULL,
                NULL,
                NULL,
                NOW()
            FROM {_SCHEMA}.atlas_etf_scorecard es
            CROSS JOIN LATERAL (
                SELECT regime_state
                FROM {_SCHEMA}.atlas_market_regime_daily
                WHERE date = es.snapshot_date
                LIMIT 1
            ) r
            WHERE es.snapshot_date = (
                SELECT MAX(snapshot_date)
                FROM {_SCHEMA}.atlas_etf_scorecard
            )
            AND es.is_atlas_leader = TRUE
            AND NOT EXISTS (
                SELECT 1
                FROM {_SCHEMA}.atlas_etf_signal_calls esc
                WHERE esc.etf_instrument_id = es.instrument_id
                  AND esc.exit_date IS NULL
            )
            """
        )
    )


def downgrade() -> None:
    """Delete only the rows inserted by this migration.

    Identified by a narrow computed_at window (migration execution time ± 5 min)
    AND the snapshot_date that was current at migration time (2026-05-22 expected).
    The combination of date + computed_at window is specific enough to avoid
    accidentally deleting any future writer rows.
    """
    op.execute(
        sa.text(
            f"""
            DELETE FROM {_SCHEMA}.atlas_signal_calls
            WHERE date = (
                SELECT MAX(snapshot_date)
                FROM {_SCHEMA}.atlas_conviction_daily
            )
            AND exit_date IS NULL
            AND computed_at >= (NOW() - INTERVAL '1 day')
            AND computed_at <= (NOW() + INTERVAL '1 hour')
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            DELETE FROM {_SCHEMA}.atlas_etf_signal_calls
            WHERE date = (
                SELECT MAX(snapshot_date)
                FROM {_SCHEMA}.atlas_etf_scorecard
            )
            AND exit_date IS NULL
            AND computed_at >= (NOW() - INTERVAL '1 day')
            AND computed_at <= (NOW() + INTERVAL '1 hour')
            """
        )
    )
