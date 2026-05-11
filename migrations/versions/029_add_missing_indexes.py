"""Health audit: add missing FK indexes on atlas_universe_funds and atlas_universe_etfs

Revision ID: 029
Revises: 028
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # atlas_universe_funds.benchmark_code: missing FK index flagged in health audit.
    # Joins from fund metrics pipeline hit this column on every benchmark merge.
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_universe_funds_benchmark_code
        ON atlas.atlas_universe_funds (benchmark_code)
        """)
    )

    # atlas_universe_etfs.benchmark_code: same pattern — ETF metrics merge on this.
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_universe_etfs_benchmark_code
        ON atlas.atlas_universe_etfs (benchmark_code)
        """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.idx_universe_funds_benchmark_code"))
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.idx_universe_etfs_benchmark_code"))
