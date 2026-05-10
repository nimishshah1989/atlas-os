"""Sprint 3: add (sector,date) index on stock_states + bottomup_ret_1w on sector_metrics

Revision ID: 027
Revises: 026
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa

revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Performance: BreadthWaterfall queries filter by sector first, then date.
    # Existing idx_stock_states_sector is (date, sector) — sector is non-leading.
    # New index with sector as leading column is ~10x faster for sector-specific queries.
    op.execute(sa.text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_states_sector_date
        ON atlas.atlas_stock_states_daily (sector, date)
    """))

    # Add bottomup_ret_1w column — computed by sectors.py but not yet persisted.
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_sector_metrics_daily
        ADD COLUMN IF NOT EXISTS bottomup_ret_1w NUMERIC(10,4)
    """))


def downgrade() -> None:
    op.execute(sa.text(
        "DROP INDEX CONCURRENTLY IF EXISTS atlas.idx_stock_states_sector_date"
    ))
    op.execute(sa.text(
        "ALTER TABLE atlas.atlas_sector_metrics_daily DROP COLUMN IF EXISTS bottomup_ret_1w"
    ))
