"""add state columns to fund tables

Revision ID: 011
Revises: 010
Create Date: 2026-05-08 00:00:10.000000

Schema gap fix: M4 classifies nav_state inside atlas_fund_metrics_daily
and composition_state / holdings_state inside atlas_fund_lens_monthly.
These columns were missing from the original 004 migration.

The state columns are also present (correctly) in atlas_fund_states_daily
(migration 005) — no change needed there.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_fund_metrics_daily
        ADD COLUMN IF NOT EXISTS nav_state VARCHAR(24)
    """))

    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_fund_lens_monthly
        ADD COLUMN IF NOT EXISTS composition_state VARCHAR(16),
        ADD COLUMN IF NOT EXISTS holdings_state    VARCHAR(20)
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_fund_metrics_daily
        DROP COLUMN IF EXISTS nav_state
    """))

    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_fund_lens_monthly
        DROP COLUMN IF EXISTS composition_state,
        DROP COLUMN IF EXISTS holdings_state
    """))
