"""Add compute_run_id to us_atlas.atlas_stock_metrics_daily.

Aligns the metrics table with the states table (which already has compute_run_id
from migration 060) so both tables share the same audit UUID per pipeline run.

Revision ID: 062
Revises: 061
Create Date: 2026-05-13
"""

from alembic import op

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE us_atlas.atlas_stock_metrics_daily
            ADD COLUMN IF NOT EXISTS compute_run_id UUID
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE us_atlas.atlas_stock_metrics_daily
            DROP COLUMN IF EXISTS compute_run_id
    """)
