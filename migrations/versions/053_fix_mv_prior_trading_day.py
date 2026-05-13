"""Fix mv_breakout_candidates and mv_deterioration_watch to use prior trading day.

The original views used `d - 1` (calendar day subtraction) to identify
"yesterday's" state. This breaks on Mondays: the previous calendar day is
Sunday, which has no trading data in atlas_stock_states_daily, so the yesterday
CTE returns zero rows — all Monday state transitions appear as new entrants
rather than transitions.

Fix: replace `d - 1` with a proper prior-trading-day lookup that finds the
maximum date in atlas_stock_states_daily that is strictly less than the latest
date. This is correct over weekends, holidays, and any other market closure.

Revision ID: 053
Revises: 052
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None

# The fixed MV SQL uses a prior_trading CTE instead of `d - 1`.
_BREAKOUT_SQL = """
CREATE MATERIALIZED VIEW atlas.mv_breakout_candidates AS
WITH latest AS (
    SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
),
prior_trading AS (
    SELECT MAX(date) AS d
    FROM atlas.atlas_stock_states_daily
    WHERE date < (SELECT d FROM latest)
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
    WHERE date = (SELECT d FROM prior_trading)
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
"""

_DETERIORATION_SQL = """
CREATE MATERIALIZED VIEW atlas.mv_deterioration_watch AS
WITH latest AS (
    SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
),
prior_trading AS (
    SELECT MAX(date) AS d
    FROM atlas.atlas_stock_states_daily
    WHERE date < (SELECT d FROM latest)
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
    WHERE date = (SELECT d FROM prior_trading)
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
"""


def upgrade() -> None:
    # Drop and recreate both views with the corrected prior-trading-day logic.
    # Indexes are recreated below; pg_cron refresh job (migration 036) is
    # unaffected because it refreshes by name, not by definition.
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_breakout_candidates"))
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_deterioration_watch"))

    op.execute(sa.text(_BREAKOUT_SQL))
    op.execute(
        sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_breakout_candidates_pk
        ON atlas.mv_breakout_candidates (instrument_id, date)
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_breakout_candidates_sector
        ON atlas.mv_breakout_candidates (sector, rs_pctile_3m DESC)
        """)
    )

    op.execute(sa.text(_DETERIORATION_SQL))
    op.execute(
        sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_deterioration_watch_pk
        ON atlas.mv_deterioration_watch (instrument_id, date)
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_deterioration_watch_sector
        ON atlas.mv_deterioration_watch (sector, rs_pctile_3m DESC)
        """)
    )

    # Populate immediately so the views are not empty after migration.
    op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_breakout_candidates"))
    op.execute(sa.text("REFRESH MATERIALIZED VIEW atlas.mv_deterioration_watch"))


def downgrade() -> None:
    # Restore the original d-1 calendar-day logic (migration 035 definitions).
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_breakout_candidates"))
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_deterioration_watch"))

    op.execute(
        sa.text("""
        CREATE MATERIALIZED VIEW atlas.mv_breakout_candidates AS
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
        """)
    )
    op.execute(
        sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_breakout_candidates_pk
        ON atlas.mv_breakout_candidates (instrument_id, date)
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_breakout_candidates_sector
        ON atlas.mv_breakout_candidates (sector, rs_pctile_3m DESC)
        """)
    )

    op.execute(
        sa.text("""
        CREATE MATERIALIZED VIEW atlas.mv_deterioration_watch AS
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
        """)
    )
    op.execute(
        sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_deterioration_watch_pk
        ON atlas.mv_deterioration_watch (instrument_id, date)
        """)
    )
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_deterioration_watch_sector
        ON atlas.mv_deterioration_watch (sector, rs_pctile_3m DESC)
        """)
    )
