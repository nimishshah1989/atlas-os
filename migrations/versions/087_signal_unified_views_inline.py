"""Hotfix: redefine sector/fund/etf signal_unified views to bypass empty v2 tables.

The Phase 2 aggregators were coded against table schemas that don't match
production (atlas_fund_holdings / atlas_etf_holdings don't exist;
atlas_universe_stocks has no market_cap_inr column). This migration:

- atlas_sector_signal_unified: compute the aggregation INLINE from
  atlas_stock_state_daily JOIN atlas_universe_stocks (equal weight, no
  market cap). No dependency on atlas_sector_state_v2.

- atlas_fund_signal_unified: fall back to atlas_fund_states_daily which
  has nav_state + composition_state + holdings_state + recommendation
  populated by the existing legacy nightly write. The new aggregator can
  populate atlas_fund_state_v2 later via a proper holdings ingestion;
  for the demo, surfacing the existing fund states through the view
  keeps the page populated.

- atlas_etf_signal_unified: fall back to atlas_etf_states_daily.

Revision ID: 087_views_inline
Revises: 086
Create Date: 2026-05-19
"""
from alembic import op


revision = "087_views_inline"
down_revision = "086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sector — bottom-up from atlas_stock_state_daily, equal weight by stock count.
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_sector_signal_unified AS
        WITH per_sector AS (
            SELECT
                u.sector,
                s.date,
                COUNT(*)                                        AS n_constituents,
                AVG(s.within_state_rank)::float8                AS mean_within_state_rank,
                SUM(CASE WHEN s.state IN ('stage_2a','stage_2b','stage_2c') THEN 1 ELSE 0 END)::float8
                  / NULLIF(COUNT(*), 0)                          AS pct_stage_2,
                SUM(CASE WHEN s.state = 'stage_3' THEN 1 ELSE 0 END)::float8
                  / NULLIF(COUNT(*), 0)                          AS pct_stage_3,
                SUM(CASE WHEN s.state = 'stage_4' THEN 1 ELSE 0 END)::float8
                  / NULLIF(COUNT(*), 0)                          AS pct_stage_4,
                MODE() WITHIN GROUP (ORDER BY s.state)            AS dominant_state
            FROM atlas.atlas_stock_state_daily s
            JOIN atlas.atlas_universe_stocks u USING (instrument_id)
            WHERE s.classifier_version = 'v2.0-validated'
              AND u.sector IS NOT NULL
            GROUP BY u.sector, s.date
        )
        SELECT
            sector,
            date,
            dominant_state                                       AS engine_state,
            (CASE WHEN n_constituents > 0
                  THEN GREATEST(pct_stage_2, pct_stage_3, pct_stage_4)
                  ELSE 0 END)::float8                            AS dominant_share,
            n_constituents,
            mean_within_state_rank,
            COALESCE(pct_stage_2, 0)::float8                     AS pct_stage_2,
            COALESCE(pct_stage_3, 0)::float8                     AS pct_stage_3,
            COALESCE(pct_stage_4, 0)::float8                     AS pct_stage_4,
            CASE
                WHEN COALESCE(pct_stage_2, 0) >= 0.50 THEN 'Overweight'
                WHEN COALESCE(pct_stage_4, 0) >= 0.50 THEN 'Avoid'
                WHEN COALESCE(pct_stage_3, 0) + COALESCE(pct_stage_4, 0) >= 0.50 THEN 'Underweight'
                ELSE 'Neutral'
            END                                                  AS sector_state
        FROM per_sector
    """)

    # Fund — surface the legacy fund states table directly. nav_state +
    # composition_state + holdings_state + recommendation all already populated.
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_fund_signal_unified AS
        SELECT
            mstar_id,
            date,
            composition_state,
            holdings_state,
            NULL::float8                AS pct_holdings_stage_2,
            NULL::float8                AS pct_holdings_stage_3,
            NULL::float8                AS pct_holdings_stage_4,
            NULL::float8                AS mean_within_state_rank,
            NULL::int                   AS n_holdings,
            nav_state,
            nav_state_as_of,
            recommendation
        FROM atlas.atlas_fund_states_daily
    """)

    # ETF — surface legacy ETF states table directly.
    op.execute("""
        CREATE OR REPLACE VIEW atlas.atlas_etf_signal_unified AS
        SELECT
            etf_ticker,
            date,
            rs_state                    AS engine_state,
            NULL::float8                AS dominant_share,
            NULL::int                   AS n_holdings,
            NULL::float8                AS mean_rs_rank_12m,
            NULL::float8                AS pct_stage_2,
            NULL::float8                AS pct_stage_3,
            NULL::float8                AS pct_stage_4
        FROM atlas.atlas_etf_states_daily
    """)


def downgrade() -> None:
    # Drop the inline hotfix views; running alembic upgrade 086 will recreate
    # the original versions from that migration.
    op.execute("DROP VIEW IF EXISTS atlas.atlas_etf_signal_unified")
    op.execute("DROP VIEW IF EXISTS atlas.atlas_fund_signal_unified")
    op.execute("DROP VIEW IF EXISTS atlas.atlas_sector_signal_unified")
