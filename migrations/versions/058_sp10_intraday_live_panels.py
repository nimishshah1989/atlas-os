"""SP10: Intraday Live Panels schema foundation.

Creates:
- atlas.atlas_nifty_intraday: 1-min / 5-min OHLCV bars for NIFTY 50 index.
  Includes return_since_open (return from open to current bar).
  Retention: 7 days (via pg_cron).

- Adds return_since_open NUMERIC(10,6) column to atlas.atlas_stock_metrics_intraday
  to track per-stock intraday return from market open to each bar.

- Recreates atlas.mv_rs_intraday materialized view to include return_since_open
  in the SELECT list (for rendering intraday return in live panels).

- pg_cron job:
  - atlas_nifty_intraday_retention: Mon-Fri at 11:15 UTC (16:45 IST),
    deletes rows older than 7 days.

Revision ID: 058
Revises: 057
Create Date: 2026-05-13
"""

import sqlalchemy as sa
from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. atlas_nifty_intraday table                                       #
    # ------------------------------------------------------------------ #
    # Stores 1-min / 5-min OHLCV bars for NIFTY 50 index.
    # bar_time is PRIMARY KEY (one NIFTY bar per timestamp).
    # return_since_open = (close - open) / open (computed by ingest pipeline).
    # updated_at tracks the last refresh timestamp.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_nifty_intraday (
            bar_time           TIMESTAMPTZ  PRIMARY KEY,
            open               NUMERIC(12,4) NOT NULL,
            high               NUMERIC(12,4) NOT NULL,
            low                NUMERIC(12,4) NOT NULL,
            close              NUMERIC(12,4) NOT NULL,
            return_since_open  NUMERIC(10,6),
            updated_at         TIMESTAMPTZ   DEFAULT NOW()
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_ani_bar_time
        ON atlas.atlas_nifty_intraday (bar_time DESC)
    """))

    # ------------------------------------------------------------------ #
    # 2. Add return_since_open column to atlas_stock_metrics_intraday     #
    # ------------------------------------------------------------------ #
    # Per-stock intraday return from market open to each bar.
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_stock_metrics_intraday
        ADD COLUMN IF NOT EXISTS return_since_open NUMERIC(10,6)
    """))

    # ------------------------------------------------------------------ #
    # 3. Recreate mv_rs_intraday with return_since_open                  #
    # ------------------------------------------------------------------ #
    # Drop the old UNIQUE INDEX first (allows re-creation)
    op.execute(sa.text("""
        DROP INDEX IF EXISTS atlas.uidx_mv_rs_intraday_inst
    """))

    # Drop the old materialized view
    op.execute(sa.text("""
        DROP MATERIALIZED VIEW IF EXISTS atlas.mv_rs_intraday
    """))

    # Recreate with return_since_open added to SELECT list
    op.execute(sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_rs_intraday AS
        SELECT
            i.instrument_id,
            i.bar_time,
            i.close,
            i.ema_20,
            i.ema_50,
            i.rs_vs_nifty,
            i.return_since_open,
            PERCENT_RANK() OVER (
                PARTITION BY i.bar_time
                ORDER BY i.rs_vs_nifty NULLS LAST
            ) AS rs_pctile_intraday,
            u.symbol,
            u.sector,
            u.tier
        FROM atlas.atlas_stock_metrics_intraday i
        JOIN atlas.atlas_universe_stocks u
          ON u.instrument_id = i.instrument_id
         AND u.effective_to IS NULL
        WHERE i.bar_time = (
            SELECT MAX(bar_time)
            FROM atlas.atlas_stock_metrics_intraday
        )
        WITH NO DATA
    """))

    op.execute(sa.text("""
        CREATE UNIQUE INDEX uidx_mv_rs_intraday_inst
        ON atlas.mv_rs_intraday (instrument_id)
    """))

    # ------------------------------------------------------------------ #
    # 4. pg_cron job for NIFTY intraday retention                         #
    # ------------------------------------------------------------------ #
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'
            ) THEN
                -- Unschedule first for idempotent re-run safety
                PERFORM cron.unschedule(j.jobid)
                FROM cron.job j
                WHERE j.jobname = 'atlas_nifty_intraday_retention';

                PERFORM cron.schedule(
                    'atlas_nifty_intraday_retention',
                    '15 11 * * 1-5',
                    $cmd$DELETE FROM atlas.atlas_nifty_intraday WHERE bar_time < NOW() - INTERVAL '7 days'$cmd$
                );
                RAISE NOTICE 'pg_cron: scheduled job atlas_nifty_intraday_retention';
            ELSE
                RAISE NOTICE 'pg_cron not available — skipping schedule for atlas_nifty_intraday_retention';
            END IF;
        END
        $$
    """))  # noqa: S608 -- job_name, schedule, command are module-level constants; no user input


def downgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Unschedule pg_cron job                                           #
    # ------------------------------------------------------------------ #
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
                PERFORM cron.unschedule(j.jobid)
                FROM cron.job j
                WHERE j.jobname = 'atlas_nifty_intraday_retention';
            END IF;
        END
        $$
    """))  # noqa: S608 -- job_name is a module-level constant; no user input

    # ------------------------------------------------------------------ #
    # 2. Drop atlas_nifty_intraday table                                  #
    # ------------------------------------------------------------------ #
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_nifty_intraday"))

    # ------------------------------------------------------------------ #
    # 3. Restore original mv_rs_intraday (WITHOUT return_since_open)      #
    # ------------------------------------------------------------------ #
    # Drop the UNIQUE INDEX first
    op.execute(sa.text("""
        DROP INDEX IF EXISTS atlas.uidx_mv_rs_intraday_inst
    """))

    # Drop the updated materialized view
    op.execute(sa.text("""
        DROP MATERIALIZED VIEW IF EXISTS atlas.mv_rs_intraday
    """))

    # Recreate with original SELECT (no return_since_open)
    op.execute(sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_rs_intraday AS
        SELECT
            i.instrument_id,
            i.bar_time,
            i.close,
            i.ema_20,
            i.ema_50,
            i.rs_vs_nifty,
            PERCENT_RANK() OVER (
                PARTITION BY i.bar_time
                ORDER BY i.rs_vs_nifty NULLS LAST
            ) AS rs_pctile_intraday,
            u.symbol,
            u.sector,
            u.tier
        FROM atlas.atlas_stock_metrics_intraday i
        JOIN atlas.atlas_universe_stocks u
          ON u.instrument_id = i.instrument_id
         AND u.effective_to IS NULL
        WHERE i.bar_time = (
            SELECT MAX(bar_time)
            FROM atlas.atlas_stock_metrics_intraday
        )
        WITH NO DATA
    """))

    op.execute(sa.text("""
        CREATE UNIQUE INDEX uidx_mv_rs_intraday_inst
        ON atlas.mv_rs_intraday (instrument_id)
    """))

    # ------------------------------------------------------------------ #
    # 4. Drop return_since_open column from atlas_stock_metrics_intraday  #
    # ------------------------------------------------------------------ #
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_stock_metrics_intraday
        DROP COLUMN IF EXISTS return_since_open
    """))
