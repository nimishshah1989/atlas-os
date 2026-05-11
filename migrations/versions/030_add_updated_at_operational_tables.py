"""Health audit: add updated_at to atlas_run_log and atlas_pipeline_runs;
add created_at to atlas_pipeline_runs.

Both tables have genuine UPDATE paths (status transitions) but were missing
updated_at, violating the global DB convention. Atlas convention requires every
table to have created_at + updated_at (both tz-aware).

Columns added with DEFAULT NOW() so existing rows get a non-null timestamp.

Revision ID: 030
Revises: 029
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # atlas_run_log: already has created_at; add updated_at.
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_run_log
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    """))

    # atlas_pipeline_runs: missing both created_at and updated_at.
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_pipeline_runs
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    """))
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_pipeline_runs
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_run_log
        DROP COLUMN IF EXISTS updated_at
    """))
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_pipeline_runs
        DROP COLUMN IF EXISTS created_at
    """))
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_pipeline_runs
        DROP COLUMN IF EXISTS updated_at
    """))
