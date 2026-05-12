"""SP08: KiteConnect Intraday Live State Engine — schema foundation.

Creates:
- pgcrypto extension (for encrypted KiteConnect token storage)
- atlas_stock_metrics_intraday: 1-min / 5-min OHLCV bars + derived intraday
  metrics (ema_20, ema_50, rs_vs_nifty). Retention: 7 days (5 trading days
  of intraday data is enough for live-state display; older rows are purged
  by the retention cron job).
- atlas_kite_session: stores the KiteConnect access token encrypted with
  pgp_sym_encrypt using KITE_TOKEN_ENCRYPTION_KEY from env. One active
  session at a time; login generates a new row and marks the old one closed.
- mv_rs_intraday: materialized view over the latest bar_time cross-section,
  computing intraday RS percentile rank. Refreshed every 15 min during
  market hours via pg_cron (09:30–15:30 IST = 04:00–10:00 UTC weekdays).

pg_cron jobs:
- atlas_intraday_mv_15min     — every 15 min, 04:00–09:45 UTC Mon-Fri
- atlas_intraday_mv_last_bar  — 10:00 UTC Mon-Fri (15:30 IST last bar)
- atlas_intraday_retention    — 11:15 UTC Mon-Fri (16:45 IST, post-market)

All schedules in UTC (RDS default). IST = UTC+5:30.

Revision ID: 042
Revises: 041
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None

# ------------------------------------------------------------------ #
# pg_cron job definitions                                             #
# ------------------------------------------------------------------ #
# Every 15 min from 04:00 to 09:45 UTC = 09:30 to 15:15 IST Mon-Fri.
# Covers bars at :00, :15, :30, :45 within each of hours 4-9.
_SCHEDULE_15MIN = "0,15,30,45 4-9 * * 1-5"

# Single final-bar refresh: 10:00 UTC = 15:30 IST
_SCHEDULE_LAST_BAR = "0 10 * * 1-5"

# Retention cleanup: 11:15 UTC = 16:45 IST (well after market close)
_SCHEDULE_RETENTION = "15 11 * * 1-5"

_MV_REFRESH_CMD = (
    "REFRESH MATERIALIZED VIEW atlas.mv_rs_intraday"
)
_RETENTION_CMD = (
    "DELETE FROM atlas.atlas_stock_metrics_intraday "
    "WHERE bar_time < NOW() - INTERVAL '7 days'"
)

_JOBS = [
    ("atlas_intraday_mv_15min",    _SCHEDULE_15MIN,    _MV_REFRESH_CMD),
    ("atlas_intraday_mv_last_bar", _SCHEDULE_LAST_BAR, _MV_REFRESH_CMD),
    ("atlas_intraday_retention",   _SCHEDULE_RETENTION, _RETENTION_CMD),
]


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 0. pgcrypto extension                                               #
    # ------------------------------------------------------------------ #
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    # ------------------------------------------------------------------ #
    # 1. atlas_stock_metrics_intraday                                     #
    # ------------------------------------------------------------------ #
    # Stores per-instrument OHLCV bars at 1-min or 5-min resolution.
    # ema_20 / ema_50 / rs_vs_nifty are computed by the ingest pipeline
    # and written alongside the bar. gap_filled = TRUE marks bars that
    # were synthesised to cover connectivity gaps (no new tick data).
    # UNIQUE (instrument_id, bar_time) prevents duplicate inserts on
    # reconnection.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_stock_metrics_intraday (
            id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            instrument_id   UUID        NOT NULL,
            bar_time        TIMESTAMPTZ NOT NULL,
            open            NUMERIC(12,4),
            high            NUMERIC(12,4),
            low             NUMERIC(12,4),
            close           NUMERIC(12,4) NOT NULL,
            volume          BIGINT,
            tick_count      INTEGER,
            ema_20          NUMERIC(12,6),
            ema_50          NUMERIC(12,6),
            rs_vs_nifty     NUMERIC(10,6),
            gap_filled      BOOLEAN DEFAULT FALSE,
            created_at      TIMESTAMPTZ DEFAULT NOW(),
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (instrument_id, bar_time)
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_asmi_bar_time
        ON atlas.atlas_stock_metrics_intraday (bar_time DESC)
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_asmi_inst_bar
        ON atlas.atlas_stock_metrics_intraday (instrument_id, bar_time DESC)
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_asmi_gap
        ON atlas.atlas_stock_metrics_intraday (gap_filled)
        WHERE gap_filled = TRUE
    """))

    # ------------------------------------------------------------------ #
    # 2. atlas_kite_session                                               #
    # ------------------------------------------------------------------ #
    # Stores the KiteConnect access_token encrypted with pgp_sym_encrypt.
    # The application layer calls:
    #   pgp_sym_encrypt(token::text, current_setting('app.kite_enc_key'))
    # on INSERT, and pgp_sym_decrypt on SELECT. Only one 'active' session
    # is expected at any time; the login flow closes prior sessions by
    # updating session_type = 'closed'.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS atlas.atlas_kite_session (
            id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            access_token_enc    TEXT        NOT NULL,
            session_type        TEXT        NOT NULL DEFAULT 'active',
            login_time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at          TIMESTAMPTZ NOT NULL,
            created_at          TIMESTAMPTZ DEFAULT NOW(),
            updated_at          TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT chk_kite_session_type
                CHECK (session_type IN ('active', 'closed'))
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_aks_session_type
        ON atlas.atlas_kite_session (session_type, login_time DESC)
    """))

    # ------------------------------------------------------------------ #
    # 3. mv_rs_intraday materialized view                                 #
    # ------------------------------------------------------------------ #
    # Latest-bar cross-section with intraday RS percentile rank.
    # Filtered to the single most-recent bar_time so the view is always
    # a point-in-time snapshot suitable for a live-state screen.
    # UNIQUE INDEX on instrument_id allows REFRESH CONCURRENTLY.
    # Created WITH NO DATA — first populate happens via the pg_cron job
    # or manual REFRESH after the first bars are ingested.
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
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_rs_intraday_inst
        ON atlas.mv_rs_intraday (instrument_id)
    """))

    # ------------------------------------------------------------------ #
    # 4. pg_cron extension (idempotent; NOTICE only on failure)           #
    # ------------------------------------------------------------------ #
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_available_extensions WHERE name = 'pg_cron'
            ) THEN
                BEGIN
                    EXECUTE 'CREATE EXTENSION IF NOT EXISTS pg_cron';
                    RAISE NOTICE 'pg_cron: extension installed or already present';
                EXCEPTION WHEN insufficient_privilege THEN
                    RAISE NOTICE 'pg_cron: available but installation requires superuser. '
                                 'Manual REFRESH required until pg_cron is enabled by DBA.';
                WHEN OTHERS THEN
                    RAISE NOTICE 'pg_cron: install failed (%). Manual REFRESH required.', SQLERRM;
                END;
            ELSE
                RAISE NOTICE 'pg_cron: extension not available on this Postgres instance. '
                             'Manual REFRESH required until pg_cron is enabled.';
            END IF;
        END
        $$
    """))

    # ------------------------------------------------------------------ #
    # 5. pg_cron jobs — 15-min MV refresh + daily retention              #
    # ------------------------------------------------------------------ #
    # job_name, schedule, and command are all module-level constants.
    # No user input flows into these f-strings.
    for job_name, schedule, command in _JOBS:
        op.execute(sa.text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'
                ) THEN
                    -- Unschedule first for idempotent re-run safety
                    PERFORM cron.unschedule(j.jobid)
                    FROM cron.job j
                    WHERE j.jobname = '{job_name}';

                    PERFORM cron.schedule(
                        '{job_name}',
                        '{schedule}',
                        $cmd${command}$cmd$
                    );
                    RAISE NOTICE 'pg_cron: scheduled job %', '{job_name}';
                ELSE
                    RAISE NOTICE 'pg_cron not available — skipping schedule for %', '{job_name}';
                END IF;
            END
            $$
        """))  # noqa: S608 -- job_name, schedule, command are module-level constants; no user input


def downgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Unschedule pg_cron jobs                                          #
    # ------------------------------------------------------------------ #
    for job_name, _, _ in _JOBS:
        op.execute(sa.text(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
                    PERFORM cron.unschedule(j.jobid)
                    FROM cron.job j
                    WHERE j.jobname = '{job_name}';
                END IF;
            END
            $$
        """))  # noqa: S608 -- job_name is a module-level constant; no user input

    # ------------------------------------------------------------------ #
    # 2. Drop materialized view                                           #
    # ------------------------------------------------------------------ #
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_rs_intraday"))

    # ------------------------------------------------------------------ #
    # 3. Drop tables (reverse creation order)                             #
    # ------------------------------------------------------------------ #
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_kite_session"))
    op.execute(sa.text("DROP TABLE IF EXISTS atlas.atlas_stock_metrics_intraday"))
