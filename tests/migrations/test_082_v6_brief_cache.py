"""Regression tests for migration 082 — atlas_brief_cache.

Tables created:
- atlas_brief_cache (E2 — per-instrument LLM brief storage with TTL +
  invalidation per CONTEXT.md "Brief cache invalidation" section)

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, indexes, FKs, and unique
constraints match the v6 spec.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the migration applies cleanly on a real Postgres + that the
schema matches the spec. Skipped by default; run on EC2 / staging.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.082_v6_brief_cache"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


def _run_upgrade_with_mock() -> MagicMock:
    """Run upgrade() with op mocked; return the mock for assertions."""
    mod = _load()
    with patch.object(mod, "op") as mock_op:
        mock_op.get_bind.return_value = MagicMock()
        mod.upgrade()
    return mock_op


def _run_downgrade_with_mock() -> MagicMock:
    mod = _load()
    with patch.object(mod, "op") as mock_op:
        mock_op.get_bind.return_value = MagicMock()
        mod.downgrade()
    return mock_op


def _brief_cache_call():
    """Return the create_table call for atlas_brief_cache."""
    mock_op = _run_upgrade_with_mock()
    for call in mock_op.create_table.call_args_list:
        if call.args[0] == "atlas_brief_cache":
            return call
    raise AssertionError("atlas_brief_cache not created")


# ---------------------------------------------------------------------------
# Unit: metadata
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    def test_revision(self) -> None:
        assert _load().revision == "082"

    def test_down_revision_080(self) -> None:
        """Per task spec: down_revision = "080" since 081 is a separate
        issue and may land out of order. Chain may be re-linearized
        when 081 lands.
        """
        assert _load().down_revision == "080"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() creates atlas_brief_cache
# ---------------------------------------------------------------------------


class TestUpgradeCreatesBriefCache:
    def test_creates_brief_cache_table(self) -> None:
        mock_op = _run_upgrade_with_mock()
        table_names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_brief_cache" in table_names

    def test_only_one_table_created(self) -> None:
        """Migration 082 is scoped to one table — no scope creep."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 1

    def test_brief_cache_in_atlas_schema(self) -> None:
        call = _brief_cache_call()
        assert call.kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: column inventory
# ---------------------------------------------------------------------------


class TestBriefCacheColumns:
    def _column_names(self) -> list[str]:
        call = _brief_cache_call()
        return [c.name for c in call.args[1:] if hasattr(c, "name")]

    def test_has_pk_id(self) -> None:
        assert "id" in self._column_names()

    def test_has_instrument_id(self) -> None:
        assert "instrument_id" in self._column_names()

    def test_has_date(self) -> None:
        assert "date" in self._column_names()

    def test_has_action(self) -> None:
        assert "action" in self._column_names()

    def test_has_cell_id(self) -> None:
        assert "cell_id" in self._column_names()

    def test_has_signal_call_id(self) -> None:
        assert "signal_call_id" in self._column_names()

    def test_has_brief_text(self) -> None:
        assert "brief_text" in self._column_names()

    def test_has_generated_at(self) -> None:
        assert "generated_at" in self._column_names()

    def test_has_valid_until_for_ttl(self) -> None:
        """24h TTL contract: valid_until is set by writer to
        generated_at + interval '24 hours'.
        """
        assert "valid_until" in self._column_names()

    def test_has_invalidated_at(self) -> None:
        assert "invalidated_at" in self._column_names()

    def test_has_invalidated_by_corp_action_id(self) -> None:
        """Links to de_corporate_actions when invalidation cause is a
        corp action (per CONTEXT.md brief cache invalidation section).
        """
        assert "invalidated_by_corp_action_id" in self._column_names()

    def test_has_created_at(self) -> None:
        assert "created_at" in self._column_names()


# ---------------------------------------------------------------------------
# Unit: column nullability / types
# ---------------------------------------------------------------------------


class TestBriefCacheColumnRules:
    def _columns(self) -> dict:
        call = _brief_cache_call()
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_brief_text_not_null(self) -> None:
        col = self._columns()["brief_text"]
        assert col.nullable is False

    def test_valid_until_not_null(self) -> None:
        col = self._columns()["valid_until"]
        assert col.nullable is False

    def test_invalidated_at_nullable(self) -> None:
        col = self._columns()["invalidated_at"]
        assert col.nullable is True

    def test_invalidated_by_corp_action_id_nullable(self) -> None:
        col = self._columns()["invalidated_by_corp_action_id"]
        assert col.nullable is True

    def test_signal_call_id_nullable(self) -> None:
        """Brief may pre-exist without a specific signal_call (task spec)."""
        col = self._columns()["signal_call_id"]
        assert col.nullable is True

    def test_instrument_id_not_null(self) -> None:
        col = self._columns()["instrument_id"]
        assert col.nullable is False

    def test_cell_id_not_null(self) -> None:
        col = self._columns()["cell_id"]
        assert col.nullable is False


# ---------------------------------------------------------------------------
# Unit: composite UNIQUE invalidation key
# ---------------------------------------------------------------------------


class TestCompositeUniqueKey:
    def test_unique_on_iid_date_action_cell(self) -> None:
        """Per CONTEXT.md brief cache section: one cached brief per
        (instrument_id, date, action, cell_id) tuple.
        """
        import sqlalchemy as sa

        call = _brief_cache_call()
        unique_constraints = [c for c in call.args[1:] if isinstance(c, sa.UniqueConstraint)]
        assert len(unique_constraints) == 1, "expected exactly one UNIQUE constraint"
        uq = unique_constraints[0]
        # Constraint hasn't been bound to a table yet (we're inspecting the
        # call args), so use the pending colargs attribute.
        col_names = list(uq._pending_colargs)
        assert col_names == ["instrument_id", "date", "action", "cell_id"]


# ---------------------------------------------------------------------------
# Unit: foreign keys
# ---------------------------------------------------------------------------


class TestForeignKeys:
    def _fks(self) -> list:
        """Return all ForeignKey objects on the brief_cache table columns."""
        call = _brief_cache_call()
        fks = []
        for c in call.args[1:]:
            if not hasattr(c, "foreign_keys"):
                continue
            for fk in c.foreign_keys:
                fks.append((c.name, fk))
        return fks

    def test_cell_id_fk_to_cell_definitions_with_restrict(self) -> None:
        fks = self._fks()
        cell_fks = [fk for col, fk in fks if col == "cell_id"]
        assert len(cell_fks) == 1, "expected one FK on cell_id"
        fk = cell_fks[0]
        # FK isn't yet bound to a parent table, so target_fullname is the
        # only safe string accessor.
        assert "atlas_cell_definitions" in fk.target_fullname
        assert "cell_id" in fk.target_fullname
        assert fk.ondelete == "RESTRICT"

    def test_signal_call_id_fk_to_signal_calls_with_cascade(self) -> None:
        fks = self._fks()
        sc_fks = [fk for col, fk in fks if col == "signal_call_id"]
        assert len(sc_fks) == 1, "expected one FK on signal_call_id"
        fk = sc_fks[0]
        assert "atlas_signal_calls" in fk.target_fullname
        assert "signal_call_id" in fk.target_fullname
        assert fk.ondelete == "CASCADE"


# ---------------------------------------------------------------------------
# Unit: indexes
# ---------------------------------------------------------------------------


class TestIndexes:
    def test_valid_until_index_for_ttl_cleanup(self) -> None:
        """TTL cleanup cron uses ix on valid_until to find expired rows."""
        mock_op = _run_upgrade_with_mock()
        index_names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_brief_cache_valid_until" in index_names

    def test_signal_call_id_index_for_invalidation(self) -> None:
        """Invalidation queries look up briefs by signal_call_id when a
        call exits/flips.
        """
        mock_op = _run_upgrade_with_mock()
        index_names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_brief_cache_signal_call_id" in index_names

    def test_partial_index_on_active_briefs(self) -> None:
        """Read-path partial index WHERE invalidated_at IS NULL keeps the
        hot path compact as invalidated rows accumulate.
        """
        mock_op = _run_upgrade_with_mock()
        executed_sql = [
            c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
            for c in mock_op.execute.call_args_list
        ]
        found = any(
            "ix_atlas_brief_cache_active" in sql and "WHERE invalidated_at IS NULL" in sql
            for sql in executed_sql
        )
        assert found, "partial active-briefs index not created"


# ---------------------------------------------------------------------------
# Unit: downgrade reverses upgrade
# ---------------------------------------------------------------------------


class TestDowngrade:
    def test_drops_brief_cache_table(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {"atlas_brief_cache"}

    def test_drops_indexes_before_table(self) -> None:
        """drop_index calls must come before drop_table — Alembic doesn't
        strictly require it but the explicit order keeps logical clarity.
        """
        mod = _load()
        # Record the call order across multiple op methods.
        recorded: list[tuple[str, str]] = []
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record(method_name):
                def _fn(*args, **kwargs):
                    name = args[0] if args else kwargs.get("name", "")
                    recorded.append((method_name, str(name)))
                    return MagicMock()

                return _fn

            mock_op.drop_index.side_effect = _record("drop_index")
            mock_op.drop_table.side_effect = _record("drop_table")
            mock_op.execute.side_effect = _record("execute")
            mod.downgrade()

        # Find index of drop_table and confirm it comes after the drop_index calls.
        table_drop_idx = next(i for i, (m, _) in enumerate(recorded) if m == "drop_table")
        index_ops_before = [
            i
            for i, (m, _) in enumerate(recorded[:table_drop_idx])
            if m in ("drop_index", "execute")
        ]
        # Expect partial index drop via execute + two regular index drops.
        assert (
            len(index_ops_before) >= 3
        ), f"expected >=3 index drops before drop_table; got {recorded}"

    def test_does_not_drop_atlas_cell_action_enum(self) -> None:
        """The atlas_cell_action enum is owned by migration 080 — 082 must
        NOT drop it on downgrade.
        """
        mock_op = _run_downgrade_with_mock()
        # No enum drops should appear (the postgresql.ENUM().drop pattern
        # used in 080 goes through bind.execute, not op.drop_*).
        # Sanity check: confirm we did NOT touch any enum-related call.
        bind = mock_op.get_bind.return_value
        # If we had attempted to drop the enum, bind would have been called.
        # We didn't — confirm by checking bind has no drop-related calls.
        for call in bind.mock_calls:
            assert "atlas_cell_action" not in str(
                call
            ), "downgrade must not drop the atlas_cell_action enum"


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_brief_cache_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_composite_unique_constraint(self) -> None:
        pytest.skip("verify (instrument_id, date, action, cell_id) UNIQUE on live DB")
