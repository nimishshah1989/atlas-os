"""Regression tests for migration 083 — atlas_ledger + atlas_ledger_public view.

Tables + objects created:
- atlas_ledger (live realized excess + drift Z per signal_call)
- atlas_ledger_public VIEW (read-only ACL surface for atlas_agent_readonly)
- Conditional GRANT SELECT on the view to the agent role

Per CONTEXT.md "atlas_agent_readonly ACL" + "Drift detector parameters":
the view hides `drift_z` + `status` so LLM agents cannot surface internal
monitoring signals (e.g. "this cell is showing Z=2.7 drift") in user briefs.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, indexes, FK, view DDL, conditional
GRANT, and downgrade ordering match the v6 spec.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the migration applies cleanly on a real Postgres + that the view
schema matches the spec and the agent role can read the view but not the
base table. Skipped by default; run on EC2 / staging.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.083_v6_ledger"
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


def _ledger_call():
    """Return the create_table call for atlas_ledger."""
    mock_op = _run_upgrade_with_mock()
    for call in mock_op.create_table.call_args_list:
        if call.args[0] == "atlas_ledger":
            return call
    raise AssertionError("atlas_ledger not created")


def _executed_sql() -> list[str]:
    """Return all SQL strings passed to op.execute() during upgrade."""
    mock_op = _run_upgrade_with_mock()
    return [
        c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
        for c in mock_op.execute.call_args_list
    ]


# ---------------------------------------------------------------------------
# Unit: metadata
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    def test_revision(self) -> None:
        assert _load().revision == "083"

    def test_down_revision_082(self) -> None:
        """Per task spec: down_revision = "082" since 081 is a separate
        issue and may land out of order. Chain may be re-linearized
        when 081 lands.
        """
        assert _load().down_revision == "082"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() creates atlas_ledger
# ---------------------------------------------------------------------------


class TestUpgradeCreatesLedger:
    def test_creates_ledger_table(self) -> None:
        mock_op = _run_upgrade_with_mock()
        table_names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_ledger" in table_names

    def test_only_one_table_created(self) -> None:
        """Migration 083 is scoped to one table + one view — no scope creep."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 1

    def test_ledger_in_atlas_schema(self) -> None:
        call = _ledger_call()
        assert call.kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: column inventory
# ---------------------------------------------------------------------------


class TestLedgerColumns:
    def _column_names(self) -> list[str]:
        call = _ledger_call()
        return [c.name for c in call.args[1:] if hasattr(c, "name")]

    def test_has_signal_call_id_pk(self) -> None:
        assert "signal_call_id" in self._column_names()

    def test_has_realized_excess(self) -> None:
        assert "realized_excess" in self._column_names()

    def test_has_realized_at(self) -> None:
        assert "realized_at" in self._column_names()

    def test_has_drift_z(self) -> None:
        """drift_z is the internal-monitoring Z-score; present on base table
        but hidden from the agent view.
        """
        assert "drift_z" in self._column_names()

    def test_has_status(self) -> None:
        """status is the drift detector verdict; present on base table but
        hidden from the agent view.
        """
        assert "status" in self._column_names()

    def test_has_provenance_log_id(self) -> None:
        """FK target ships later; nullable + no FK constraint for now."""
        assert "provenance_log_id" in self._column_names()

    def test_has_created_at(self) -> None:
        assert "created_at" in self._column_names()

    def test_has_updated_at(self) -> None:
        assert "updated_at" in self._column_names()


# ---------------------------------------------------------------------------
# Unit: column nullability / primary key
# ---------------------------------------------------------------------------


class TestLedgerColumnRules:
    def _columns(self) -> dict:
        call = _ledger_call()
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_signal_call_id_is_primary_key(self) -> None:
        col = self._columns()["signal_call_id"]
        assert col.primary_key is True

    def test_realized_excess_not_null(self) -> None:
        col = self._columns()["realized_excess"]
        assert col.nullable is False

    def test_realized_at_not_null(self) -> None:
        col = self._columns()["realized_at"]
        assert col.nullable is False

    def test_drift_z_nullable(self) -> None:
        """Freshly-inserted rows have no Z until the next nightly detector
        run — column must be nullable.
        """
        col = self._columns()["drift_z"]
        assert col.nullable is True

    def test_status_not_null(self) -> None:
        col = self._columns()["status"]
        assert col.nullable is False

    def test_provenance_log_id_nullable(self) -> None:
        """FK target ships in a later issue; nullable for now."""
        col = self._columns()["provenance_log_id"]
        assert col.nullable is True

    def test_created_at_not_null(self) -> None:
        col = self._columns()["created_at"]
        assert col.nullable is False

    def test_updated_at_not_null(self) -> None:
        col = self._columns()["updated_at"]
        assert col.nullable is False


# ---------------------------------------------------------------------------
# Unit: column types — Numeric not Float for money; tz-aware datetimes
# ---------------------------------------------------------------------------


class TestLedgerColumnTypes:
    def _columns(self) -> dict:
        call = _ledger_call()
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_realized_excess_is_numeric(self) -> None:
        """Financial domain rule: Numeric, not Float."""
        import sqlalchemy as sa

        col = self._columns()["realized_excess"]
        assert isinstance(col.type, sa.Numeric)

    def test_drift_z_is_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["drift_z"]
        assert isinstance(col.type, sa.Numeric)

    def test_realized_at_is_tz_aware(self) -> None:
        col = self._columns()["realized_at"]
        assert col.type.timezone is True

    def test_created_at_is_tz_aware(self) -> None:
        col = self._columns()["created_at"]
        assert col.type.timezone is True

    def test_updated_at_is_tz_aware(self) -> None:
        col = self._columns()["updated_at"]
        assert col.type.timezone is True


# ---------------------------------------------------------------------------
# Unit: foreign keys
# ---------------------------------------------------------------------------


class TestForeignKeys:
    def _fks(self) -> list:
        """Return all ForeignKey objects on the ledger table columns."""
        call = _ledger_call()
        fks = []
        for c in call.args[1:]:
            if not hasattr(c, "foreign_keys"):
                continue
            for fk in c.foreign_keys:
                fks.append((c.name, fk))
        return fks

    def test_signal_call_id_fk_to_signal_calls_with_restrict(self) -> None:
        """ON DELETE RESTRICT — never silently lose realized history when
        a signal_call row is deleted upstream.
        """
        fks = self._fks()
        sc_fks = [fk for col, fk in fks if col == "signal_call_id"]
        assert len(sc_fks) == 1, "expected one FK on signal_call_id"
        fk = sc_fks[0]
        assert "atlas_signal_calls" in fk.target_fullname
        assert "signal_call_id" in fk.target_fullname
        assert fk.ondelete == "RESTRICT"

    def test_no_fk_on_provenance_log_id(self) -> None:
        """provenance_log_id is nullable and has NO FK constraint — the
        target table (atlas_provenance_log) ships in a later issue.
        """
        fks = self._fks()
        prov_fks = [fk for col, fk in fks if col == "provenance_log_id"]
        assert len(prov_fks) == 0, "provenance_log_id must not have an FK yet"


# ---------------------------------------------------------------------------
# Unit: indexes
# ---------------------------------------------------------------------------


class TestIndexes:
    def test_realized_at_index_for_window_queries(self) -> None:
        """Drift detector aggregates over rolling N-day windows on
        realized_at — index supports the range scan.
        """
        mock_op = _run_upgrade_with_mock()
        index_names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_ledger_realized_at" in index_names

    def test_status_index_for_drift_lookups(self) -> None:
        """Admin UI + drift detector cron query 'all drift_warn cells' —
        index on status column supports those filters.
        """
        mock_op = _run_upgrade_with_mock()
        index_names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_ledger_status" in index_names


# ---------------------------------------------------------------------------
# Unit: atlas_ledger_public view DDL
# ---------------------------------------------------------------------------


class TestLedgerPublicView:
    def test_creates_view(self) -> None:
        """View must be created via op.execute('CREATE VIEW ...')."""
        sql_list = _executed_sql()
        found = any(
            "CREATE VIEW" in sql.upper() and "atlas.atlas_ledger_public" in sql for sql in sql_list
        )
        assert found, "atlas_ledger_public view not created"

    def test_view_exposes_signal_call_id(self) -> None:
        sql_list = _executed_sql()
        view_sql = next(
            sql
            for sql in sql_list
            if "atlas.atlas_ledger_public" in sql and "CREATE VIEW" in sql.upper()
        )
        assert "signal_call_id" in view_sql

    def test_view_exposes_realized_excess(self) -> None:
        sql_list = _executed_sql()
        view_sql = next(
            sql
            for sql in sql_list
            if "atlas.atlas_ledger_public" in sql and "CREATE VIEW" in sql.upper()
        )
        assert "realized_excess" in view_sql

    def test_view_exposes_realized_at(self) -> None:
        sql_list = _executed_sql()
        view_sql = next(
            sql
            for sql in sql_list
            if "atlas.atlas_ledger_public" in sql and "CREATE VIEW" in sql.upper()
        )
        assert "realized_at" in view_sql

    def test_view_hides_drift_z(self) -> None:
        """drift_z must NOT appear in the view SELECT — per CONTEXT.md
        agent ACL, internal monitoring is hidden from LLM agents.
        """
        sql_list = _executed_sql()
        view_sql = next(
            sql
            for sql in sql_list
            if "atlas.atlas_ledger_public" in sql and "CREATE VIEW" in sql.upper()
        )
        assert "drift_z" not in view_sql

    def test_view_hides_status(self) -> None:
        """status must NOT appear in the view SELECT — per CONTEXT.md
        agent ACL, drift verdict is hidden from LLM agents.
        """
        sql_list = _executed_sql()
        view_sql = next(
            sql
            for sql in sql_list
            if "atlas.atlas_ledger_public" in sql and "CREATE VIEW" in sql.upper()
        )
        assert "status" not in view_sql

    def test_view_selects_from_atlas_ledger(self) -> None:
        sql_list = _executed_sql()
        view_sql = next(
            sql
            for sql in sql_list
            if "atlas.atlas_ledger_public" in sql and "CREATE VIEW" in sql.upper()
        )
        assert "FROM atlas.atlas_ledger" in view_sql


# ---------------------------------------------------------------------------
# Unit: conditional GRANT (idempotent across environments)
# ---------------------------------------------------------------------------


class TestConditionalGrant:
    def test_grant_is_conditional_via_do_block(self) -> None:
        """GRANT must be wrapped in a DO $$ ... $$ block that checks for the
        atlas_agent_readonly role — the migration must survive environments
        where the role isn't yet provisioned.
        """
        sql_list = _executed_sql()
        do_block = next(
            (
                sql
                for sql in sql_list
                if "DO $$" in sql and "atlas_agent_readonly" in sql and "GRANT" in sql.upper()
            ),
            None,
        )
        assert do_block is not None, "conditional GRANT DO block not found"
        # The conditional must reference pg_roles existence check.
        assert "pg_roles" in do_block
        assert "atlas_agent_readonly" in do_block

    def test_grant_targets_view_not_base_table(self) -> None:
        """ACL surface boundary: GRANT must be on the view, NEVER on the
        base atlas_ledger table.
        """
        sql_list = _executed_sql()
        grant_sql = " ".join(
            sql for sql in sql_list if "GRANT" in sql.upper() and "atlas_agent_readonly" in sql
        )
        assert "atlas_ledger_public" in grant_sql
        # Ensure no GRANT statement targets the bare base table. The exact
        # base-table identifier (with no _public suffix) must not appear in
        # any GRANT context. Check by inspecting each grant-bearing SQL.
        for sql in sql_list:
            if "GRANT" not in sql.upper() or "atlas_agent_readonly" not in sql:
                continue
            # Allow `atlas_ledger_public` but reject naked `atlas_ledger TO`.
            # The grant target text in our DO block is the view fullname.
            assert "atlas.atlas_ledger TO" not in sql
            assert "atlas.atlas_ledger " not in sql.replace(
                "atlas.atlas_ledger_public", ""
            ) or "TO atlas_agent_readonly" not in sql.replace("atlas.atlas_ledger_public", "")

    def test_no_unconditional_grant_statement(self) -> None:
        """No bare 'GRANT SELECT ON ... TO atlas_agent_readonly' outside of
        a DO block — that would fail in environments without the role.
        """
        sql_list = _executed_sql()
        for sql in sql_list:
            upper = sql.upper()
            if upper.strip().startswith("GRANT") and "atlas_agent_readonly" in sql:
                pytest.fail(f"unconditional GRANT statement found: {sql!r}")


# ---------------------------------------------------------------------------
# Unit: downgrade reverses upgrade
# ---------------------------------------------------------------------------


class TestDowngrade:
    def test_drops_ledger_table(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {"atlas_ledger"}

    def test_drops_view_before_table(self) -> None:
        """DROP VIEW must come before DROP TABLE — Postgres rejects
        dropping a table that has dependent views.
        """
        mod = _load()
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

        # Locate the drop_table position.
        table_drop_idx = next((i for i, (m, _) in enumerate(recorded) if m == "drop_table"), None)
        assert table_drop_idx is not None, "drop_table not called"

        # Find the execute() call that drops the view; must be before the table drop.
        view_drop_idx = next(
            (
                i
                for i, (m, payload) in enumerate(recorded)
                if m == "execute"
                and "atlas_ledger_public" in payload
                and "DROP VIEW" in payload.upper()
            ),
            None,
        )
        assert view_drop_idx is not None, "DROP VIEW for atlas_ledger_public not found"
        assert view_drop_idx < table_drop_idx, "DROP VIEW must come before DROP TABLE"

    def test_drops_indexes_before_table(self) -> None:
        """drop_index calls must come before drop_table for logical clarity."""
        mod = _load()
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

        table_drop_idx = next(i for i, (m, _) in enumerate(recorded) if m == "drop_table")
        index_drops_before = [
            i for i, (m, _) in enumerate(recorded[:table_drop_idx]) if m == "drop_index"
        ]
        assert len(index_drops_before) >= 2, (
            f"expected >=2 index drops before drop_table; got {recorded}"
        )

    def test_revoke_is_conditional(self) -> None:
        """REVOKE must be wrapped in a DO block — survives missing role."""
        mock_op = _run_downgrade_with_mock()
        executed = [
            c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
            for c in mock_op.execute.call_args_list
        ]
        revoke_block = next(
            (sql for sql in executed if "REVOKE" in sql.upper() and "DO $$" in sql),
            None,
        )
        assert revoke_block is not None, "conditional REVOKE DO block not found"
        assert "pg_roles" in revoke_block
        assert "atlas_agent_readonly" in revoke_block

    def test_does_not_drop_atlas_drift_status_enum(self) -> None:
        """The atlas_drift_status enum is owned by migration 080 — 083 must
        NOT drop it on downgrade.
        """
        mock_op = _run_downgrade_with_mock()
        bind = mock_op.get_bind.return_value
        for call in bind.mock_calls:
            assert "atlas_drift_status" not in str(call), (
                "downgrade must not drop the atlas_drift_status enum"
            )
        # Also verify no executed SQL drops the enum.
        executed = [
            c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
            for c in mock_op.execute.call_args_list
        ]
        for sql in executed:
            assert "atlas_drift_status" not in sql or "DROP TYPE" not in sql.upper(), (
                "downgrade must not DROP TYPE atlas_drift_status"
            )


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_ledger_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_ledger_public_view_exists(self) -> None:
        pytest.skip("verify view exists in atlas schema on live DB")

    def test_agent_role_cannot_select_base_table(self) -> None:
        pytest.skip("verify atlas_agent_readonly is denied on atlas_ledger base table")

    def test_agent_role_can_select_view(self) -> None:
        pytest.skip("verify atlas_agent_readonly can SELECT atlas_ledger_public view")
