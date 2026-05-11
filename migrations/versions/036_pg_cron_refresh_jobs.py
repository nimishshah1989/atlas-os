"""SP02: install pg_cron and register nightly refresh jobs for all five MVs.

Schedule: 30 14 * * * UTC = 20:00 IST, after the nightly Atlas pipeline
which completes by ~20:00 IST. Uses REFRESH MATERIALIZED VIEW CONCURRENTLY
so reads are never blocked.

If pg_cron is not available (local dev Postgres without extension), the
migration succeeds with a warning logged via RAISE NOTICE. This is non-fatal
— views can be refreshed manually.

Refresh order matters:
  1. mv_current_market_regime   (no deps)
  2. mv_sector_rotation_state   (reads atlas_sector_metrics_daily — depends
                                 on nightly sectors.py which populates rs_velocity)
  3. mv_rs_leaders_daily        (no deps beyond stock tables)
  4. mv_breakout_candidates     (no deps)
  5. mv_deterioration_watch     (no deps)

Each job is named uniquely so it can be identified in cron.job and unscheduled
in downgrade without affecting other jobs.

Revision ID: 036
Revises: 035
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None

# Cron expression: minute=30, hour=14 UTC (20:00 IST), every day.
_SCHEDULE = "30 14 * * *"

_JOBS = [
    ("atlas_mv_regime",
     "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_current_market_regime"),
    ("atlas_mv_rotation",
     "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_rotation_state"),
    ("atlas_mv_rs_leaders",
     "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_rs_leaders_daily"),
    ("atlas_mv_breakouts",
     "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_breakout_candidates"),
    ("atlas_mv_deterioration",
     "REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_deterioration_watch"),
]


def upgrade() -> None:
    # Install pg_cron — idempotent; no-op if already installed.
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

    # Schedule each view — only if pg_cron is now installed.
    # job_name and command are module-level constants — no user input flows
    # into the f-string, so no SQL injection vector exists here.
    for job_name, command in _JOBS:
        op.execute(sa.text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'
                ) THEN
                    -- Unschedule first (idempotent re-run safety)
                    PERFORM cron.unschedule(j.jobid)
                    FROM cron.job j
                    WHERE j.jobname = '{job_name}';

                    PERFORM cron.schedule(
                        '{job_name}',
                        '{_SCHEDULE}',
                        $cmd${command}$cmd$
                    );
                    RAISE NOTICE 'pg_cron: scheduled job %', '{job_name}';
                ELSE
                    RAISE NOTICE 'pg_cron not available — skipping schedule for %', '{job_name}';
                END IF;
            END
            $$
        """))  # noqa: S608 -- job_name + command are module-level constants; no user input


def downgrade() -> None:
    for job_name, _ in _JOBS:
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
