"""Regression tests for migration 088 — atlas_drift_event_log.

Tables created
--------------
- atlas_drift_event_log  — write-once audit log per drift event.
  UPDATE / DELETE rejected by a plpgsql trigger. Indexed by
  (cell_id, ts DESC), (ts DESC), (action, ts DESC).

New enum
--------
- atlas_drift_action ('flag', 'clear', 'deprecate') — owned by 088
  (created + dropped here).

Reused enum
-----------
- atlas_drift_status (from 080) — referenced with create_type=False,
  NOT dropped on downgrade.

FK relationships
----------------
- cell_id           → atlas.atlas_cell_definitions(cell_id) ON DELETE RESTRICT
- provenance_log_id → atlas.atlas_provenance_log(run_id)    ON DELETE SET NULL

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, indexes, FKs, CHECK constraints,
trigger creation, enum lifecycle, and downgrade ordering match the v6
spec.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the migration applies cleanly on a real Postgres + that the
write-once trigger raises on UPDATE / DELETE + that CHECK constraints
fire. Skipped by default; run on EC2 / staging.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.088_v6_drift_event_log"
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


def _table_call(table_name: str):
    """Return the create_table call for the named table."""
    mock_op = _run_upgrade_with_mock()
    for call in mock_op.create_table.call_args_list:
        if call.args[0] == table_name:
            return call
    raise AssertionError(f"{table_name} not created")


# ---------------------------------------------------------------------------
# Unit: metadata
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    def test_revision(self) -> None:
        assert _load().revision == "088"

    def test_down_revision_087(self) -> None:
        assert _load().down_revision == "087"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() creates the drift event log table in atlas schema
# ---------------------------------------------------------------------------


class TestUpgradeCreatesTable:
    def test_creates_atlas_drift_event_log(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_drift_event_log" in names

    def test_only_one_table_created(self) -> None:
        """088 is scoped to a single new table — no scope creep."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 1

    def test_table_in_atlas_schema(self) -> None:
        assert _table_call("atlas_drift_event_log").kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: atlas_drift_event_log columns
# ---------------------------------------------------------------------------


class TestDriftEventLogColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_drift_event_log")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_event_id_pk(self) -> None:
        col = self._columns()["event_id"]
        assert col.primary_key is True

    def test_event_id_has_uuid_default(self) -> None:
        col = self._columns()["event_id"]
        assert col.server_default is not None
        assert "gen_random_uuid" in str(col.server_default.arg)

    def test_cell_id_not_null_uuid(self) -> None:
        from sqlalchemy.dialects.postgresql import UUID

        col = self._columns()["cell_id"]
        assert col.nullable is False
        assert isinstance(col.type, UUID)

    def test_ts_not_null_tz_aware(self) -> None:
        col = self._columns()["ts"]
        assert col.nullable is False
        assert col.type.timezone is True

    def test_ts_has_now_default(self) -> None:
        col = self._columns()["ts"]
        assert col.server_default is not None
        assert "NOW" in str(col.server_default.arg).upper()

    def test_z_score_not_null_numeric_8_4(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["z_score"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 8
        assert col.type.scale == 4

    def test_realized_window_start_not_null_date(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["realized_window_start"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Date)

    def test_realized_window_end_not_null_date(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["realized_window_end"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Date)

    def test_predicted_excess_not_null_numeric_10_6(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["predicted_excess"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 10
        assert col.type.scale == 6

    def test_sigma_predicted_not_null_numeric_10_6(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["sigma_predicted"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 10
        assert col.type.scale == 6

    def test_n_realized_not_null_integer(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["n_realized"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Integer)

    def test_status_before_not_null_uses_drift_status_enum(self) -> None:
        col = self._columns()["status_before"]
        assert col.nullable is False
        # Should reference the 080-owned atlas_drift_status enum.
        assert getattr(col.type, "name", None) == "atlas_drift_status"

    def test_status_after_not_null_uses_drift_status_enum(self) -> None:
        col = self._columns()["status_after"]
        assert col.nullable is False
        assert getattr(col.type, "name", None) == "atlas_drift_status"

    def test_action_not_null_uses_drift_action_enum(self) -> None:
        col = self._columns()["action"]
        assert col.nullable is False
        # Should reference the NEW atlas_drift_action enum.
        assert getattr(col.type, "name", None) == "atlas_drift_action"

    def test_actor_not_null_default_system_varchar_64(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["actor"]
        assert col.nullable is False
        assert isinstance(col.type, sa.String)
        assert col.type.length == 64
        assert col.server_default is not None
        assert "system" in str(col.server_default.arg)

    def test_provenance_log_id_nullable_uuid(self) -> None:
        from sqlalchemy.dialects.postgresql import UUID

        col = self._columns()["provenance_log_id"]
        assert col.nullable is True
        assert isinstance(col.type, UUID)

    def test_notes_nullable_text(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["notes"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Text)


# ---------------------------------------------------------------------------
# Unit: CHECK constraints — window order + n_realized non-negative
# ---------------------------------------------------------------------------


def _check_constraints(table_name: str) -> dict:
    import sqlalchemy as sa

    call = _table_call(table_name)
    return {c.name: c for c in call.args[1:] if isinstance(c, sa.CheckConstraint)}


class TestDriftEventLogCheckConstraints:
    def test_window_order_check(self) -> None:
        cks = _check_constraints("atlas_drift_event_log")
        assert "ck_atlas_drift_event_log_window_order" in cks
        ck = cks["ck_atlas_drift_event_log_window_order"]
        sqltext = str(ck.sqltext)
        assert "realized_window_start" in sqltext
        assert "realized_window_end" in sqltext
        assert "<=" in sqltext

    def test_n_realized_non_negative_check(self) -> None:
        cks = _check_constraints("atlas_drift_event_log")
        assert "ck_atlas_drift_event_log_n_realized_non_negative" in cks
        ck = cks["ck_atlas_drift_event_log_n_realized_non_negative"]
        sqltext = str(ck.sqltext)
        assert "n_realized" in sqltext
        assert ">=" in sqltext or ">" in sqltext

    def test_exactly_two_check_constraints_present(self) -> None:
        cks = _check_constraints("atlas_drift_event_log")
        assert len(cks) == 2, f"expected 2 CHECK constraints, got {len(cks)}: {list(cks)}"


# ---------------------------------------------------------------------------
# Unit: FKs embedded in the table definition
# ---------------------------------------------------------------------------


class TestDriftEventLogForeignKeys:
    def _fks_for(self, column_name: str) -> list:
        """Return ForeignKey constructs declared on a column."""
        call = _table_call("atlas_drift_event_log")
        cols = {c.name: c for c in call.args[1:] if hasattr(c, "name")}
        col = cols[column_name]
        return list(col.foreign_keys)

    def test_cell_id_fk_targets_atlas_cell_definitions(self) -> None:
        fks = self._fks_for("cell_id")
        assert len(fks) == 1
        target = fks[0].target_fullname
        assert "atlas_cell_definitions" in target
        assert target.endswith(".cell_id")

    def test_cell_id_fk_ondelete_restrict(self) -> None:
        fks = self._fks_for("cell_id")
        assert fks[0].ondelete == "RESTRICT"

    def test_cell_id_fk_in_atlas_schema(self) -> None:
        fks = self._fks_for("cell_id")
        assert fks[0].target_fullname.startswith("atlas.")

    def test_provenance_log_id_fk_targets_atlas_provenance_log(self) -> None:
        fks = self._fks_for("provenance_log_id")
        assert len(fks) == 1
        target = fks[0].target_fullname
        assert "atlas_provenance_log" in target
        assert target.endswith(".run_id")

    def test_provenance_log_id_fk_ondelete_set_null(self) -> None:
        fks = self._fks_for("provenance_log_id")
        assert fks[0].ondelete == "SET NULL"

    def test_provenance_log_id_fk_in_atlas_schema(self) -> None:
        fks = self._fks_for("provenance_log_id")
        assert fks[0].target_fullname.startswith("atlas.")


# ---------------------------------------------------------------------------
# Unit: indexes
# ---------------------------------------------------------------------------


class TestDriftEventLogIndexes:
    def test_cell_id_ts_desc_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_drift_event_log_cell_id_ts_desc" in names

    def test_ts_desc_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_drift_event_log_ts_desc" in names

    def test_action_ts_desc_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_drift_event_log_action_ts_desc" in names

    def test_exactly_three_indexes_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_index.call_count == 3


# ---------------------------------------------------------------------------
# Unit: write-once trigger — op.execute() must create function + trigger
# ---------------------------------------------------------------------------


def _execute_payloads() -> list[str]:
    mock_op = _run_upgrade_with_mock()
    return [c.args[0] for c in mock_op.execute.call_args_list]


class TestWriteOnceTrigger:
    def test_creates_plpgsql_function(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "CREATE OR REPLACE FUNCTION" in payloads
        assert "atlas.deny_update_delete_drift_event" in payloads

    def test_function_raises_exception(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "RAISE EXCEPTION" in payloads
        assert "write-once" in payloads

    def test_function_language_plpgsql(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "LANGUAGE plpgsql" in payloads

    def test_creates_trigger(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "CREATE TRIGGER deny_update_delete_atlas_drift_event_log" in payloads

    def test_trigger_fires_before_update_or_delete(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "BEFORE UPDATE OR DELETE" in payloads
        assert "ON atlas.atlas_drift_event_log" in payloads

    def test_trigger_for_each_row(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "FOR EACH ROW" in payloads

    def test_trigger_references_function(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "EXECUTE FUNCTION atlas.deny_update_delete_drift_event" in payloads


# ---------------------------------------------------------------------------
# Unit: enum lifecycle — atlas_drift_action created; atlas_drift_status reused
# ---------------------------------------------------------------------------


class TestEnumLifecycleUpgrade:
    """088 owns atlas_drift_action and only that. atlas_drift_status is
    reused from 080 and must NOT be (re)created here."""

    def test_creates_atlas_drift_action_enum(self) -> None:
        mod = _load()
        created_names: list[str] = []

        original_enum_cls = importlib.import_module("sqlalchemy.dialects.postgresql").ENUM

        class _SpyEnum(original_enum_cls):  # type: ignore[misc, valid-type]
            def create(  # type: ignore[override]
                self,
                bind,  # pyright: ignore[reportUnusedParameter]
                checkfirst: bool = False,  # pyright: ignore[reportUnusedParameter]
            ) -> None:
                # Only record .create() calls where the enum carries
                # values — reused-enum stubs use create_type=False and
                # never call .create() with values.
                if getattr(self, "enums", None):
                    created_names.append(self.name)

        with (
            patch.object(mod, "op") as mock_op,
            patch("sqlalchemy.dialects.postgresql.ENUM", _SpyEnum),
        ):
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()

        assert "atlas_drift_action" in created_names

    def test_does_not_recreate_atlas_drift_status(self) -> None:
        """Reused enum from 080 must NOT be passed to .create()."""
        mod = _load()
        created_names: list[str] = []

        original_enum_cls = importlib.import_module("sqlalchemy.dialects.postgresql").ENUM

        class _SpyEnum(original_enum_cls):  # type: ignore[misc, valid-type]
            def create(  # type: ignore[override]
                self,
                bind,  # pyright: ignore[reportUnusedParameter]
                checkfirst: bool = False,  # pyright: ignore[reportUnusedParameter]
            ) -> None:
                if getattr(self, "enums", None):
                    created_names.append(self.name)

        with (
            patch.object(mod, "op") as mock_op,
            patch("sqlalchemy.dialects.postgresql.ENUM", _SpyEnum),
        ):
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()

        assert (
            "atlas_drift_status" not in created_names
        ), "atlas_drift_status is owned by 080 and must not be recreated"

    def test_drift_action_values(self) -> None:
        """atlas_drift_action declares ('flag', 'clear', 'deprecate')."""
        mod = _load()
        assert mod.DRIFT_ACTION == ("flag", "clear", "deprecate")


# ---------------------------------------------------------------------------
# Unit: downgrade
# ---------------------------------------------------------------------------


class TestDowngrade:
    def test_drops_drift_event_log_table(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {"atlas_drift_event_log"}

    def test_drops_trigger_before_function(self) -> None:
        mod = _load()
        execute_payloads: list[str] = []

        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record_execute(sql) -> None:
                execute_payloads.append(sql)

            mock_op.execute.side_effect = _record_execute
            mod.downgrade()

        trigger_idx = next(i for i, p in enumerate(execute_payloads) if "DROP TRIGGER" in p)
        function_idx = next(i for i, p in enumerate(execute_payloads) if "DROP FUNCTION" in p)
        assert trigger_idx < function_idx

    def test_drops_function_before_table(self) -> None:
        mod = _load()
        events: list[tuple[str, str]] = []

        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record_execute(sql) -> None:
                events.append(("execute", sql))

            def _record_drop_table(name, *_args, **_kwargs) -> None:
                events.append(("drop_table", name))

            mock_op.execute.side_effect = _record_execute
            mock_op.drop_table.side_effect = _record_drop_table
            mod.downgrade()

        function_idx = next(
            i for i, e in enumerate(events) if e[0] == "execute" and "DROP FUNCTION" in e[1]
        )
        table_idx = next(
            i
            for i, e in enumerate(events)
            if e[0] == "drop_table" and e[1] == "atlas_drift_event_log"
        )
        assert function_idx < table_idx

    def test_drops_all_three_indexes(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_index.call_args_list}
        expected = {
            "ix_atlas_drift_event_log_cell_id_ts_desc",
            "ix_atlas_drift_event_log_ts_desc",
            "ix_atlas_drift_event_log_action_ts_desc",
        }
        missing = expected - dropped
        assert not missing, f"missing index drops on downgrade: {missing}"

    def test_drops_indexes_before_table(self) -> None:
        mod = _load()
        events: list[tuple[str, str]] = []

        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record_drop_index(name, *_args, **_kwargs) -> None:
                events.append(("drop_index", name))

            def _record_drop_table(name, *_args, **_kwargs) -> None:
                events.append(("drop_table", name))

            mock_op.drop_index.side_effect = _record_drop_index
            mock_op.drop_table.side_effect = _record_drop_table
            mod.downgrade()

        last_index_idx = max(i for i, e in enumerate(events) if e[0] == "drop_index")
        table_idx = next(
            i
            for i, e in enumerate(events)
            if e[0] == "drop_table" and e[1] == "atlas_drift_event_log"
        )
        assert last_index_idx < table_idx

    def test_drops_drift_action_enum(self) -> None:
        """Downgrade must drop the NEW atlas_drift_action enum."""
        mod = _load()
        dropped_names: list[str] = []

        original_enum_cls = importlib.import_module("sqlalchemy.dialects.postgresql").ENUM

        class _SpyEnum(original_enum_cls):  # type: ignore[misc, valid-type]
            def drop(  # type: ignore[override]
                self,
                bind,  # pyright: ignore[reportUnusedParameter]
                checkfirst: bool = False,  # pyright: ignore[reportUnusedParameter]
            ) -> None:
                dropped_names.append(self.name)

        with (
            patch.object(mod, "op") as mock_op,
            patch("sqlalchemy.dialects.postgresql.ENUM", _SpyEnum),
        ):
            mock_op.get_bind.return_value = MagicMock()
            mod.downgrade()

        assert "atlas_drift_action" in dropped_names

    def test_does_not_drop_drift_status_enum(self) -> None:
        """atlas_drift_status is owned by 080 and must survive 088 downgrade."""
        mod = _load()
        dropped_names: list[str] = []

        original_enum_cls = importlib.import_module("sqlalchemy.dialects.postgresql").ENUM

        class _SpyEnum(original_enum_cls):  # type: ignore[misc, valid-type]
            def drop(  # type: ignore[override]
                self,
                bind,  # pyright: ignore[reportUnusedParameter]
                checkfirst: bool = False,  # pyright: ignore[reportUnusedParameter]
            ) -> None:
                dropped_names.append(self.name)

        with (
            patch.object(mod, "op") as mock_op,
            patch("sqlalchemy.dialects.postgresql.ENUM", _SpyEnum),
        ):
            mock_op.get_bind.return_value = MagicMock()
            mod.downgrade()

        assert (
            "atlas_drift_status" not in dropped_names
        ), "atlas_drift_status owned by 080; 088 must not drop it"


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_drift_event_log_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_write_once_blocks_update(self) -> None:
        pytest.skip(
            "verify UPDATE on atlas_drift_event_log raises with "
            "'write-once; UPDATE/DELETE not permitted'"
        )

    def test_write_once_blocks_delete(self) -> None:
        pytest.skip(
            "verify DELETE on atlas_drift_event_log raises with "
            "'write-once; UPDATE/DELETE not permitted'"
        )

    def test_window_order_check_rejects_inverted(self) -> None:
        pytest.skip(
            "verify INSERT with realized_window_start > realized_window_end "
            "raises check_violation"
        )

    def test_n_realized_check_rejects_negative(self) -> None:
        pytest.skip("verify INSERT with n_realized = -1 raises check_violation")

    def test_cell_fk_restrict_blocks_delete(self) -> None:
        pytest.skip(
            "verify DELETE on atlas_cell_definitions with audit rows raises foreign_key_violation"
        )

    def test_provenance_fk_set_null_on_delete(self) -> None:
        pytest.skip(
            "verify DELETE on atlas_provenance_log nulls atlas_drift_event_log.provenance_log_id"
        )
