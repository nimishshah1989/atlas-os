"""Reconciliation marker: alembic stamped to 087 after schema applied via direct SQL.

This migration is a no-op. It exists to prove the migration pipeline is healthy
after the alembic_version table was reconciled with the actual DB state via
``alembic stamp 087_views_inline``.

Revision ID: 088_alembic_marker
Revises: 087_views_inline
Create Date: 2026-05-19
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "088_alembic_marker"
down_revision = "087_views_inline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: reconciliation marker only.
    op.execute("SELECT 1")


def downgrade() -> None:
    # No-op: nothing to undo.
    pass
