"""Add partial unique index to prevent duplicate active pipeline runs.

A queued-or-running run per milestone is enforced at the application layer in
internal_recompute.py, but a DB-level partial unique index is belt-and-suspenders
for concurrent requests that slip past the application check simultaneously.

The index covers only rows where status IN ('queued', 'running'), so completed
runs (success, failed) are excluded and allow re-running the same milestone
on any future day.

Revision ID: 044
Revises: 043
Create Date: 2026-05-12
"""

import sqlalchemy as sa
from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uidx_pipeline_one_active_per_milestone
        ON atlas.atlas_pipeline_runs (milestone)
        WHERE status IN ('queued', 'running')
        """)
    )


def downgrade() -> None:
    op.execute(
        sa.text("""
        DROP INDEX IF EXISTS atlas.uidx_pipeline_one_active_per_milestone
        """)
    )
