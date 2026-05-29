"""Add PE, PS, PB, Debt/Equity, ROE columns to atlas.tv_metrics

Revision ID: 118
Revises: 117
Create Date: 2026-05-29
"""

from alembic import op

revision = "118"
down_revision = "117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.tv_metrics
            ADD COLUMN IF NOT EXISTS pe_ttm         NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS ps_current     NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS pb_fbs         NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS debt_to_equity NUMERIC(12,4),
            ADD COLUMN IF NOT EXISTS roe            NUMERIC(12,4)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE atlas.tv_metrics
            DROP COLUMN IF EXISTS pe_ttm,
            DROP COLUMN IF EXISTS ps_current,
            DROP COLUMN IF EXISTS pb_fbs,
            DROP COLUMN IF EXISTS debt_to_equity,
            DROP COLUMN IF EXISTS roe
    """)
