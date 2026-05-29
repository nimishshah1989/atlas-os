"""Regression tests for migration 120 — mv_stock_list_v6 tombstone.

History: this revision exists because two files in migrations/versions/ both
declared revision="097" (097_v6_frontend_column_adds and 097_v6_mv_stock_list).
Alembic walked the duplicate graph with a warning; one of the two files ran
via alembic and the other's content was applied via MCP execute_sql
out-of-band. By 2026-05-29 every environment had mv_stock_list_v6 in place.

Migration 120 deduplicates the revision graph: the duplicate file is deleted
and a NO-OP upgrade is shipped in its place. downgrade() still drops the MV
+ unique index so full teardowns work.

These tests lock that contract.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

_MODULE = "migrations.versions.120_v6_mv_stock_list_tombstone"


def _import_module():
    return importlib.import_module(_MODULE)


def test_revision_and_down_revision_are_set():
    """Tombstone chains 120 -> 119 (head of the TV integration chain)."""
    mod = _import_module()
    assert mod.revision == "120"
    assert mod.down_revision == "119"
    assert mod.branch_labels is None
    assert mod.depends_on is None


def test_upgrade_is_a_noop_marker():
    """upgrade() must NOT issue CREATE MATERIALIZED VIEW — the MV already
    exists in every environment that walked the 097..119 chain."""
    mod = _import_module()
    mock_op = MagicMock()
    with patch.object(mod, "op", mock_op):
        mod.upgrade()
    assert mock_op.execute.call_count == 1
    sql = mock_op.execute.call_args_list[0].args[0]
    assert "marker_migration_120_applied" in sql
    assert "CREATE MATERIALIZED VIEW" not in sql.upper()


def test_downgrade_drops_unique_index_then_mv():
    """downgrade() preserves the original 097_v6_mv_stock_list teardown
    order so rolling back past 120 leaves a clean slate."""
    mod = _import_module()
    mock_op = MagicMock()
    with patch.object(mod, "op", mock_op):
        mod.downgrade()
    assert mock_op.execute.call_count == 2
    sql_calls = [call.args[0] for call in mock_op.execute.call_args_list]
    # Index dropped first, MV dropped second — dependency-safe order.
    assert "DROP INDEX" in sql_calls[0].upper()
    assert "mv_stock_list_v6" in sql_calls[0]
    assert "DROP MATERIALIZED VIEW" in sql_calls[1].upper()
    assert "mv_stock_list_v6" in sql_calls[1]


def test_downgrade_uses_idempotent_ddl():
    """Both drops use IF EXISTS so a partial rollback can be re-run safely."""
    mod = _import_module()
    mock_op = MagicMock()
    with patch.object(mod, "op", mock_op):
        mod.downgrade()
    for call in mock_op.execute.call_args_list:
        assert "IF EXISTS" in call.args[0].upper()
