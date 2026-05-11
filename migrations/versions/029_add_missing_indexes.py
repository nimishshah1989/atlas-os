"""Health audit: add missing FK index on atlas_universe_funds.benchmark_code

atlas_universe_etfs uses linked_index (not benchmark_code) for benchmark
lookups — no index needed there.

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
    # atlas_universe_funds.benchmark_code: missing index flagged in health audit.
    # Fund metrics pipeline joins on this column for every benchmark merge.
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_universe_funds_benchmark_code
        ON atlas.atlas_universe_funds (benchmark_code)
        """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS atlas.idx_universe_funds_benchmark_code"))
