"""SP02: create five materialized views for sub-3ms frontend reads.

Views:
- mv_rs_leaders_daily       — top RS stocks per timeframe with names/sectors
- mv_sector_rotation_state  — sector RS level + RS velocity + RRG quadrant
- mv_current_market_regime  — latest regime row with deployment multiplier
- mv_breakout_candidates    — stocks transitioning into Strong or Leader today
- mv_deterioration_watch    — stocks transitioning OUT of Strong/Leader today

All views use UNIQUE INDEXes so REFRESH CONCURRENTLY works without read locks.
Created WITH NO DATA; populated at end of migration via first REFRESH.

Note on column substitutions (verified live against current schema):
- ``atlas_stock_metrics_daily`` does NOT have ``rs_6m_nifty500`` — only
  ``rs_1w_nifty500``, ``rs_1m_nifty500``, ``rs_3m_nifty500``. The leaders
  view uses ``ret_6m`` (6-month total return) as the 6-month signal column.

Revision ID: 035
Revises: 034
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. mv_rs_leaders_daily                                             #
    # ------------------------------------------------------------------ #
    # Top RS stocks for latest date joined with names from
    # atlas_universe_stocks. One row per (instrument_id, date) filtered
    # to rs_state in {Leader, Strong} with liquidity + history gates passed.
    op.execute(sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_rs_leaders_daily AS
        SELECT
            m.instrument_id,
            m.date,
            u.symbol,
            u.company_name,
            u.sector,
            u.tier,
            m.rs_pctile_3m::numeric(10,4)   AS rs_pctile_3m,
            m.rs_pctile_1m::numeric(10,4)   AS rs_pctile_1m,
            m.rs_3m_nifty500::numeric(10,4) AS rs_3m_nifty500,
            m.ret_6m::numeric(10,4)         AS ret_6m,
            s.rs_state,
            s.momentum_state,
            s.state_since_date
        FROM atlas.atlas_stock_metrics_daily m
        JOIN atlas.atlas_universe_stocks u
          ON u.instrument_id = m.instrument_id
        JOIN atlas.atlas_stock_states_daily s
          ON s.instrument_id = m.instrument_id
         AND s.date           = m.date
        WHERE m.date = (
            SELECT MAX(date)
            FROM atlas.atlas_stock_metrics_daily
        )
          AND s.rs_state IN ('Leader', 'Strong')
          AND s.liquidity_gate_pass = TRUE
          AND s.history_gate_pass   = TRUE
        ORDER BY m.rs_pctile_3m DESC NULLS LAST
        WITH NO DATA
    """))

    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_rs_leaders_daily_pk
        ON atlas.mv_rs_leaders_daily (instrument_id, date)
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_rs_leaders_daily_sector
        ON atlas.mv_rs_leaders_daily (sector, rs_pctile_3m DESC)
    """))

    # ------------------------------------------------------------------ #
    # 2. mv_sector_rotation_state                                        #
    # ------------------------------------------------------------------ #
    # One row per sector for the latest date. Includes RS level, RS
    # velocity, sector_state, and RRG quadrant assignment.
    # Quadrant logic (per master plan SP02):
    #   Leading   = rs_pctile >= 50 AND rs_velocity >= 0
    #   Weakening = rs_pctile >= 50 AND rs_velocity <  0
    #   Improving = rs_pctile <  50 AND rs_velocity >= 0
    #   Lagging   = rs_pctile <  50 AND rs_velocity <  0
    # RS percentile is computed cross-sectionally (PERCENT_RANK) on
    # bottomup_rs_3m_nifty500 for the latest date.
    op.execute(sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_sector_rotation_state AS
        WITH latest AS (
            SELECT MAX(date) AS d FROM atlas.atlas_sector_metrics_daily
        ),
        latest_metrics AS (
            SELECT
                m.sector_name,
                m.date,
                m.bottomup_rs_3m_nifty500,
                m.rs_velocity,
                m.constituent_count,
                PERCENT_RANK() OVER (
                    ORDER BY m.bottomup_rs_3m_nifty500 NULLS LAST
                ) AS rs_pctile_cross_sector
            FROM atlas.atlas_sector_metrics_daily m
            WHERE m.date = (SELECT d FROM latest)
        ),
        latest_states AS (
            SELECT sector_name, sector_state, bottomup_rs_state,
                   bottomup_momentum_state, participation_rs_pct
            FROM atlas.atlas_sector_states_daily
            WHERE date = (SELECT d FROM latest)
        )
        SELECT
            lm.sector_name,
            lm.date,
            lm.bottomup_rs_3m_nifty500::numeric(10, 4) AS rs_level,
            lm.rs_velocity::numeric(10, 6)              AS rs_velocity,
            lm.rs_pctile_cross_sector::numeric(10, 4)   AS rs_pctile_cross_sector,
            lm.constituent_count,
            ls.sector_state,
            ls.bottomup_rs_state,
            ls.bottomup_momentum_state,
            ls.participation_rs_pct::numeric(10, 4)     AS participation_rs_pct,
            CASE
                WHEN lm.rs_pctile_cross_sector >= 0.5
                 AND COALESCE(lm.rs_velocity, 0) >= 0   THEN 'Leading'
                WHEN lm.rs_pctile_cross_sector >= 0.5
                 AND lm.rs_velocity             <  0    THEN 'Weakening'
                WHEN lm.rs_pctile_cross_sector  < 0.5
                 AND COALESCE(lm.rs_velocity, 0) >= 0   THEN 'Improving'
                ELSE                                         'Lagging'
            END AS rrg_quadrant
        FROM latest_metrics lm
        LEFT JOIN latest_states ls ON ls.sector_name = lm.sector_name
        ORDER BY lm.rs_pctile_cross_sector DESC NULLS LAST
        WITH NO DATA
    """))

    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_sector_rotation_pk
        ON atlas.mv_sector_rotation_state (sector_name, date)
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_sector_rotation_quadrant
        ON atlas.mv_sector_rotation_state (rrg_quadrant)
    """))

    # ------------------------------------------------------------------ #
    # 3. mv_current_market_regime                                        #
    # ------------------------------------------------------------------ #
    # Single row: the latest market regime with all key columns. Frontend
    # reads this instead of SELECT MAX(date) + JOIN on regime table.
    op.execute(sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_current_market_regime AS
        SELECT
            r.date,
            r.regime_state,
            r.deployment_multiplier::numeric(10, 4)    AS deployment_multiplier,
            r.dislocation_active,
            r.dislocation_started,
            r.nifty500_close::numeric(12, 2)           AS nifty500_close,
            r.nifty500_above_ema_50,
            r.nifty500_above_ema_200,
            r.pct_above_ema_50::numeric(10, 4)         AS pct_above_ema_50,
            r.pct_above_ema_200::numeric(10, 4)        AS pct_above_ema_200,
            r.pct_in_strong_states::numeric(10, 4)     AS pct_in_strong_states,
            r.india_vix::numeric(10, 4)                AS india_vix,
            r.advances_count,
            r.declines_count,
            r.net_new_highs,
            r.ad_ratio::numeric(10, 4)                 AS ad_ratio,
            r.mcclellan_oscillator::numeric(10, 4)     AS mcclellan_oscillator
        FROM atlas.atlas_market_regime_daily r
        WHERE r.date = (SELECT MAX(date) FROM atlas.atlas_market_regime_daily)
        WITH NO DATA
    """))

    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_current_regime_date
        ON atlas.mv_current_market_regime (date)
    """))

    # ------------------------------------------------------------------ #
    # 4. mv_breakout_candidates                                          #
    # ------------------------------------------------------------------ #
    # Stocks that transitioned INTO 'Strong' or 'Leader' on the latest date
    # (i.e. rs_state today IN ('Strong','Leader') AND rs_state yesterday was
    # NOT in that set). Filters out illiquid and history-insufficient rows.
    op.execute(sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_breakout_candidates AS
        WITH latest AS (
            SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
        ),
        today AS (
            SELECT instrument_id, rs_state, momentum_state, sector,
                   state_since_date, date
            FROM atlas.atlas_stock_states_daily
            WHERE date = (SELECT d FROM latest)
              AND rs_state IN ('Strong', 'Leader')
              AND liquidity_gate_pass = TRUE
              AND history_gate_pass   = TRUE
        ),
        yesterday AS (
            SELECT instrument_id, rs_state
            FROM atlas.atlas_stock_states_daily
            WHERE date = (SELECT d - 1 FROM latest)
        )
        SELECT
            t.instrument_id,
            t.date,
            u.symbol,
            u.company_name,
            u.sector,
            u.tier,
            t.rs_state          AS new_rs_state,
            y.rs_state          AS prior_rs_state,
            t.momentum_state,
            t.state_since_date,
            m.rs_pctile_3m::numeric(10, 4)   AS rs_pctile_3m,
            m.rs_3m_nifty500::numeric(10, 4) AS rs_3m_nifty500
        FROM today t
        LEFT JOIN yesterday y
          ON y.instrument_id = t.instrument_id
        JOIN atlas.atlas_universe_stocks u
          ON u.instrument_id = t.instrument_id
        LEFT JOIN atlas.atlas_stock_metrics_daily m
          ON m.instrument_id = t.instrument_id
         AND m.date           = t.date
        WHERE y.rs_state IS NULL
           OR y.rs_state NOT IN ('Strong', 'Leader')
        ORDER BY m.rs_pctile_3m DESC NULLS LAST
        WITH NO DATA
    """))

    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_breakout_candidates_pk
        ON atlas.mv_breakout_candidates (instrument_id, date)
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_breakout_candidates_sector
        ON atlas.mv_breakout_candidates (sector, rs_pctile_3m DESC)
    """))

    # ------------------------------------------------------------------ #
    # 5. mv_deterioration_watch                                          #
    # ------------------------------------------------------------------ #
    # Stocks that were 'Strong' or 'Leader' yesterday and are no longer
    # today (rs_state changed out of those tiers). Early-warning list.
    op.execute(sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_deterioration_watch AS
        WITH latest AS (
            SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
        ),
        today AS (
            SELECT instrument_id, rs_state, momentum_state, sector,
                   state_since_date, date
            FROM atlas.atlas_stock_states_daily
            WHERE date = (SELECT d FROM latest)
              AND rs_state NOT IN ('Strong', 'Leader',
                                   'ILLIQUID', 'INSUFFICIENT_HISTORY')
        ),
        yesterday AS (
            SELECT instrument_id, rs_state
            FROM atlas.atlas_stock_states_daily
            WHERE date = (SELECT d - 1 FROM latest)
              AND rs_state IN ('Strong', 'Leader')
        )
        SELECT
            t.instrument_id,
            t.date,
            u.symbol,
            u.company_name,
            u.sector,
            u.tier,
            y.rs_state          AS prior_rs_state,
            t.rs_state          AS new_rs_state,
            t.momentum_state,
            t.state_since_date,
            m.rs_pctile_3m::numeric(10, 4)   AS rs_pctile_3m,
            m.rs_3m_nifty500::numeric(10, 4) AS rs_3m_nifty500
        FROM today t
        JOIN yesterday y
          ON y.instrument_id = t.instrument_id
        JOIN atlas.atlas_universe_stocks u
          ON u.instrument_id = t.instrument_id
        LEFT JOIN atlas.atlas_stock_metrics_daily m
          ON m.instrument_id = t.instrument_id
         AND m.date           = t.date
        ORDER BY m.rs_pctile_3m DESC NULLS LAST
        WITH NO DATA
    """))

    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_deterioration_watch_pk
        ON atlas.mv_deterioration_watch (instrument_id, date)
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_deterioration_watch_sector
        ON atlas.mv_deterioration_watch (sector, rs_pctile_3m DESC)
    """))

    # ------------------------------------------------------------------ #
    # First populate of all five views                                   #
    # ------------------------------------------------------------------ #
    # Runs synchronously in the migration so views are immediately usable.
    # Subsequent refreshes go via pg_cron (migration 036).
    op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_current_market_regime"))
    op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_sector_rotation_state"))
    op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_rs_leaders_daily"))
    op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_breakout_candidates"))
    op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_deterioration_watch"))


def downgrade() -> None:
    for view in [
        "mv_deterioration_watch",
        "mv_breakout_candidates",
        "mv_current_market_regime",
        "mv_sector_rotation_state",
        "mv_rs_leaders_daily",
    ]:
        op.execute(sa.text(f"DROP MATERIALIZED VIEW IF EXISTS atlas.{view}"))
