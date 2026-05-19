"""Replace hot-fix unified views with real v2-table-backed views.

The three unified views previously read from legacy state tables as a hot-fix.
This migration redefines them to read from the populated v2 aggregate tables:
  - atlas_sector_signal_unified  <- atlas_sector_state_v2
  - atlas_fund_signal_unified    <- atlas_fund_state_v2 + atlas_fund_states_daily (nav_state)
  - atlas_etf_signal_unified     <- atlas_etf_state_v2 + atlas_etf_states_daily (rs_state)

Pre-requisite: atlas_sector_state_v2, atlas_fund_state_v2, atlas_etf_state_v2
must have at least one day of data. The populate_aggregate_tables_v2.py script
seeds 2026-05-18 before this migration runs.

Revision ID: 089_aggregate_views_real
Revises: 088_alembic_marker
Create Date: 2026-05-19
"""

from alembic import op

revision = "089_aggregate_views_real"
down_revision = "088_alembic_marker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sector: read from v2 table; add sector_state classification.
    op.execute("DROP VIEW IF EXISTS atlas.atlas_sector_signal_unified")
    op.execute(
        """
        CREATE VIEW atlas.atlas_sector_signal_unified AS
        SELECT
            sector,
            date,
            dominant_state              AS engine_state,
            dominant_share,
            n_constituents,
            mean_within_state_rank,
            pct_stage_2,
            pct_stage_3,
            pct_stage_4,
            CASE
                WHEN pct_stage_2 >= 0.50 THEN 'Overweight'
                WHEN pct_stage_4 >= 0.50 THEN 'Avoid'
                WHEN (pct_stage_3 + pct_stage_4) >= 0.50 THEN 'Underweight'
                ELSE 'Neutral'
            END AS sector_state
        FROM atlas.atlas_sector_state_v2
        """
    )

    # Fund: join v2 table (composition/holdings) with fund_states_daily (nav_state).
    # nav_state is a fund-internal NAV-vs-category computation not replicated in v2.
    op.execute("DROP VIEW IF EXISTS atlas.atlas_fund_signal_unified")
    op.execute(
        """
        CREATE VIEW atlas.atlas_fund_signal_unified AS
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
                WHEN d.nav_state = 'DISLOCATION_SUSPENDED'       THEN 'Avoid'
                WHEN v.composition_state = 'Deteriorating'
                  OR v.holdings_state    = 'Weak-Holdings'        THEN 'Avoid'
                WHEN v.composition_state = 'Aligned'
                 AND v.holdings_state    = 'Strong-Holdings'
                 AND d.nav_state IN ('Leader NAV', 'Strong NAV')  THEN 'Recommended'
                ELSE 'Hold'
            END AS recommendation
        FROM atlas.atlas_fund_state_v2 v
        LEFT JOIN atlas.atlas_fund_states_daily d
               ON d.mstar_id = v.mstar_id
              AND d.date     = v.date
        """
    )

    # ETF: join v2 table with etf_states_daily for legacy rs_state.
    op.execute("DROP VIEW IF EXISTS atlas.atlas_etf_signal_unified")
    op.execute(
        """
        CREATE VIEW atlas.atlas_etf_signal_unified AS
        SELECT
            v.etf_ticker,
            v.date,
            v.dominant_state            AS engine_state,
            v.dominant_share,
            v.n_holdings,
            v.mean_rs_rank_12m,
            NULL::double precision      AS mean_within_state_rank,
            v.pct_stage_2,
            v.pct_stage_3,
            v.pct_stage_4
        FROM atlas.atlas_etf_state_v2 v
        """
    )


def downgrade() -> None:
    # Restore the hot-fix views that read from legacy tables.
    op.execute("DROP VIEW IF EXISTS atlas.atlas_sector_signal_unified")
    op.execute(
        """
        CREATE VIEW atlas.atlas_sector_signal_unified AS
        WITH per_sector AS (
            SELECT u.sector, s.date,
                   count(*) AS n_constituents,
                   avg(s.within_state_rank)::double precision AS mean_within_state_rank,
                   (sum(CASE WHEN s.state IN ('stage_2a','stage_2b','stage_2c') THEN 1 ELSE 0 END)::double precision
                    / NULLIF(count(*),0)::double precision) AS pct_stage_2,
                   (sum(CASE WHEN s.state = 'stage_3' THEN 1 ELSE 0 END)::double precision
                    / NULLIF(count(*),0)::double precision) AS pct_stage_3,
                   (sum(CASE WHEN s.state = 'stage_4' THEN 1 ELSE 0 END)::double precision
                    / NULLIF(count(*),0)::double precision) AS pct_stage_4,
                   mode() WITHIN GROUP (ORDER BY s.state) AS dominant_state
            FROM atlas.atlas_stock_state_daily s
            JOIN atlas.atlas_universe_stocks u USING (instrument_id)
            WHERE s.classifier_version = 'v2.0-validated'
              AND u.sector IS NOT NULL
            GROUP BY u.sector, s.date
        )
        SELECT sector, date, dominant_state AS engine_state,
               GREATEST(COALESCE(pct_stage_2,0), COALESCE(pct_stage_3,0), COALESCE(pct_stage_4,0)) AS dominant_share,
               n_constituents, mean_within_state_rank,
               COALESCE(pct_stage_2,0) AS pct_stage_2,
               COALESCE(pct_stage_3,0) AS pct_stage_3,
               COALESCE(pct_stage_4,0) AS pct_stage_4,
               CASE WHEN COALESCE(pct_stage_2,0) >= 0.50 THEN 'Overweight'
                    WHEN COALESCE(pct_stage_4,0) >= 0.50 THEN 'Avoid'
                    WHEN COALESCE(pct_stage_3,0)+COALESCE(pct_stage_4,0) >= 0.50 THEN 'Underweight'
                    ELSE 'Neutral' END AS sector_state
        FROM per_sector
        """
    )

    op.execute("DROP VIEW IF EXISTS atlas.atlas_fund_signal_unified")
    op.execute(
        """
        CREATE VIEW atlas.atlas_fund_signal_unified AS
        SELECT mstar_id, date, composition_state, holdings_state,
               NULL::double precision AS pct_holdings_stage_2,
               NULL::double precision AS pct_holdings_stage_3,
               NULL::double precision AS pct_holdings_stage_4,
               NULL::double precision AS mean_within_state_rank,
               NULL::integer AS n_holdings,
               nav_state, nav_state_as_of,
               CASE WHEN nav_state = 'DISLOCATION_SUSPENDED' THEN 'Avoid'
                    WHEN composition_state = 'Deteriorating' OR holdings_state = 'Weak-Holdings' THEN 'Avoid'
                    WHEN composition_state = 'Aligned' AND holdings_state = 'Strong-Holdings'
                     AND nav_state IN ('Leader NAV','Strong NAV') THEN 'Recommended'
                    ELSE 'Hold' END AS recommendation
        FROM atlas.atlas_fund_states_daily
        """
    )

    op.execute("DROP VIEW IF EXISTS atlas.atlas_etf_signal_unified")
    op.execute(
        """
        CREATE VIEW atlas.atlas_etf_signal_unified AS
        SELECT ticker AS etf_ticker, date, rs_state AS engine_state,
               NULL::double precision AS dominant_share,
               NULL::integer AS n_holdings,
               CASE rs_state WHEN 'Leader' THEN 0.95 WHEN 'Strong' THEN 0.80
                             WHEN 'Consolidating' THEN 0.60 WHEN 'Emerging' THEN 0.55
                             WHEN 'Average' THEN 0.50 WHEN 'Weak' THEN 0.20
                             WHEN 'Laggard' THEN 0.05 ELSE NULL END::double precision AS mean_rs_rank_12m,
               NULL::double precision AS mean_within_state_rank,
               CASE WHEN momentum_state IN ('Accelerating','Improving') THEN 0.7 ELSE NULL END::double precision AS pct_stage_2,
               CASE WHEN momentum_state = 'Deteriorating' THEN 0.5 ELSE NULL END::double precision AS pct_stage_3,
               CASE WHEN momentum_state = 'Collapsing' THEN 0.7 ELSE NULL END::double precision AS pct_stage_4
        FROM atlas.atlas_etf_states_daily
        """
    )
