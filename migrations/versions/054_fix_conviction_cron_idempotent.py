"""Make conviction mv pg_cron schedule idempotent.

Migration 039 called cron.schedule() without a preceding cron.unschedule().
Re-running that migration (or running it on a DB where a previous partial
migration left a schedule) would cause a unique-constraint error in pg_cron's
cron.job table because the job name 'atlas_mv_conviction' already exists.

This migration re-schedules safely by unscheduling first (ignoring 'not found'
errors), then scheduling with the correct UTC time (14:30 UTC = 20:00 IST).

Revision ID: 054
Revises: 053
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        DO $body$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
                -- Unschedule first so this block is safe to re-run.
                BEGIN
                    PERFORM cron.unschedule('atlas_mv_conviction');
                EXCEPTION WHEN OTHERS THEN NULL;
                END;
                PERFORM cron.schedule(
                    'atlas_mv_conviction',
                    '45 14 * * *',
                    'REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_top_conviction_daily'
                );
            ELSE
                RAISE NOTICE 'pg_cron not installed; skipping schedule (apply on EC2)';
            END IF;
        END
        $body$;
        """)
    )


def downgrade() -> None:
    op.execute(
        sa.text("""
        DO $body$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_cron') THEN
                BEGIN
                    PERFORM cron.unschedule('atlas_mv_conviction');
                EXCEPTION WHEN OTHERS THEN NULL;
                END;
            END IF;
        END
        $body$;
        """)
    )
