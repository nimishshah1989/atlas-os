"""create atlas schema

Revision ID: 001
Revises:
Create Date: 2026-05-06 00:00:00.000000

Per ``docs/02_DATABASE_SCHEMA.md`` Section 1: the ``atlas`` schema is owned
by Atlas and is the only schema atlas writes to. ``public`` (where JIP
Data Core's ``de_*`` tables live) is read-only.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent — env.py also creates the schema before recording version.
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS atlas"))
    op.execute(
        sa.text(
            "COMMENT ON SCHEMA atlas IS "
            "'Atlas — Adaptive Technical Lens for Asset States. v0 build.'"
        )
    )


def downgrade() -> None:
    # Drop only if completely empty. Refuse if any atlas_* tables exist —
    # those should be dropped by their own migrations first.
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "  IF EXISTS (SELECT 1 FROM information_schema.tables "
            "             WHERE table_schema = 'atlas') THEN "
            "    RAISE EXCEPTION 'atlas schema is not empty; "
            "drop dependent migrations first'; "
            "  END IF; "
            "  EXECUTE 'DROP SCHEMA atlas CASCADE'; "
            "END $$;"
        )
    )
