"""Health audit: add 'queued' to chk_pipeline_runs_status constraint.

The backtest trigger endpoint (POST /api/strategies/{id}/backtest) was
inserting status='running' rows without spawning a subprocess. A 'running'
row that never transitions permanently blocks the 30-min concurrency guard.

Fix: the endpoint now inserts status='queued'. The status constraint is
extended to permit 'queued' as a valid initial state (accepted but not yet
picked up by a worker). The concurrency guard checks both 'running' and
'queued' so double-submission is still prevented.

Postgres does not support ALTER CONSTRAINT on CHECK constraints — drop and
re-add is the required pattern.

Revision ID: 031
Revises: 030
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_pipeline_runs
        DROP CONSTRAINT IF EXISTS chk_pipeline_runs_status
    """))
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_pipeline_runs
        ADD CONSTRAINT chk_pipeline_runs_status
        CHECK (status IN ('queued', 'running', 'success', 'failed'))
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_pipeline_runs
        DROP CONSTRAINT IF EXISTS chk_pipeline_runs_status
    """))
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_pipeline_runs
        ADD CONSTRAINT chk_pipeline_runs_status
        CHECK (status IN ('running', 'success', 'failed'))
    """))
