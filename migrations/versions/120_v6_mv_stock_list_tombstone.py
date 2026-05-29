"""v6 — mv_stock_list_v6 tombstone (resolves duplicate revision 097).

Background
----------
Two files in this directory previously claimed revision = "097":

  - 097_v6_frontend_column_adds.py   (canonical 097 — column adds + 2 tables)
  - 097_v6_mv_stock_list.py          (duplicate — created atlas.mv_stock_list_v6)

The duplicate slipped in via commit de8b659 ("forge: mv-india-pulse —
... + fix 097 stock list migration") which was meant to renumber the
mv_stock_list migration but left both files at revision "097". Alembic
walked the graph anyway (with a "Revision 097 is present more than once"
warning) and applied one of them; the other's content was applied to
production via MCP execute_sql out-of-band. By 2026-05-29, Supabase
production was at alembic_version=112 with mv_stock_list_v6 present.

This migration deduplicates the revision graph by:
  1. Deleting the old 097_v6_mv_stock_list.py file
  2. Adding this new revision 120 that is a NO-OP upgrade (the MV
     already exists in every environment that ran through the chain).
  3. Preserving the original drop logic in downgrade() so a full
     teardown still works.

For the actual CREATE MATERIALIZED VIEW body, see the deleted file in
git history at commit e546e2e0:migrations/versions/097_v6_mv_stock_list.py
or the design spec at docs/superpowers/specs/2026-05-26-v6-stocks-mvs-design.md.

Revision ID: 120
Revises: 119
Create Date: 2026-05-29 IST
"""

from __future__ import annotations

from alembic import op

revision = "120"
down_revision = "119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op. atlas.mv_stock_list_v6 already exists in every environment
    that has executed the 097..119 chain (created by the original
    097_v6_mv_stock_list.py before that file was removed)."""
    op.execute("SELECT 1 AS marker_migration_120_applied")


def downgrade() -> None:
    """Drop unique index then MV in dependency-safe order. Mirrors the
    teardown that the original 097_v6_mv_stock_list.py would have done."""
    op.execute("DROP INDEX IF EXISTS atlas.mv_stock_list_v6_iid_uidx")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_list_v6 CASCADE")
