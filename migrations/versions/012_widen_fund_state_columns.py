"""widen fund state varchar columns

Revision ID: 012
Revises: 011
Create Date: 2026-05-08 14:30:00.000000

Schema bug fix: nav_state VARCHAR(20), composition_state VARCHAR(16), and
holdings_state VARCHAR(20) in atlas_fund_states_daily are all too short to
hold the value 'DISLOCATION_SUSPENDED' (21 chars). Widen all three to
VARCHAR(32) for headroom.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_fund_states_daily
            ALTER COLUMN nav_state          TYPE VARCHAR(32),
            ALTER COLUMN composition_state  TYPE VARCHAR(32),
            ALTER COLUMN holdings_state     TYPE VARCHAR(32)
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE atlas.atlas_fund_states_daily
            ALTER COLUMN nav_state          TYPE VARCHAR(20),
            ALTER COLUMN composition_state  TYPE VARCHAR(16),
            ALTER COLUMN holdings_state     TYPE VARCHAR(20)
    """))
