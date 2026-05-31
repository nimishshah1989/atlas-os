"""Regression tests for migration 087 — atlas_provenance_log + retroactive FKs.

Tables created
--------------
- atlas_provenance_log  — write-once data-lineage log. UPDATE / DELETE
  rejected by a plpgsql trigger. Indexed by (ts DESC),
  (output_table, ts DESC), (run_type, ts DESC).

Retroactive FK additions
------------------------
- atlas_ledger.provenance_log_id              (created in 083)
- atlas_macro_features_daily.provenance_log_id (created in 086)

Both reference ``atlas.atlas_provenance_log.run_id`` ON DELETE SET NULL.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, indexes, FKs, CHECK constraints,
trigger creation, retroactive FK additions, and downgrade ordering match
the v6 spec.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the migration applies cleanly on a real Postgres + that the
write-once trigger raises on UPDATE / DELETE. Skipped by default; run
on EC2 / staging.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.087_v6_provenance_log"
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
        assert _load().revision == "087"

    def test_down_revision_086(self) -> None:
        assert _load().down_revision == "086"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() creates the provenance log table in atlas schema
# ---------------------------------------------------------------------------


class TestUpgradeCreatesTable:
    def test_creates_atlas_provenance_log(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_provenance_log" in names

    def test_only_one_table_created(self) -> None:
        """087 is scoped to a single new table — no scope creep."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 1

    def test_table_in_atlas_schema(self) -> None:
        assert _table_call("atlas_provenance_log").kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: atlas_provenance_log columns
# ---------------------------------------------------------------------------


class TestProvenanceLogColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_provenance_log")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_run_id_pk(self) -> None:
        col = self._columns()["run_id"]
        assert col.primary_key is True

    def test_run_id_has_uuid_default(self) -> None:
        col = self._columns()["run_id"]
        # server_default should reference gen_random_uuid()
        assert col.server_default is not None
        assert "gen_random_uuid" in str(col.server_default.arg)

    def test_ts_not_null_tz_aware(self) -> None:
        col = self._columns()["ts"]
        assert col.nullable is False
        assert col.type.timezone is True

    def test_ts_has_now_default(self) -> None:
        col = self._columns()["ts"]
        assert col.server_default is not None
        assert "NOW" in str(col.server_default.arg).upper()

    def test_input_dataset_sha256_char_64_not_null(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["input_dataset_sha256"]
        assert col.nullable is False
        assert isinstance(col.type, sa.CHAR)
        assert col.type.length == 64

    def test_universe_definition_sha256_char_64_not_null(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["universe_definition_sha256"]
        assert col.nullable is False
        assert isinstance(col.type, sa.CHAR)
        assert col.type.length == 64

    def test_code_commit_sha_not_null_varchar_40(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["code_commit_sha"]
        assert col.nullable is False
        assert isinstance(col.type, sa.String)
        assert col.type.length == 40

    def test_friction_params_row_ids_nullable_jsonb(self) -> None:
        from sqlalchemy.dialects.postgresql import JSONB

        col = self._columns()["friction_params_row_ids"]
        assert col.nullable is True
        assert isinstance(col.type, JSONB)

    def test_output_table_not_null_varchar_64(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["output_table"]
        assert col.nullable is False
        assert isinstance(col.type, sa.String)
        assert col.type.length == 64

    def test_output_row_range_not_null_jsonb(self) -> None:
        from sqlalchemy.dialects.postgresql import JSONB

        col = self._columns()["output_row_range"]
        assert col.nullable is False
        assert isinstance(col.type, JSONB)

    def test_run_type_not_null_varchar_32(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["run_type"]
        assert col.nullable is False
        assert isinstance(col.type, sa.String)
        assert col.type.length == 32

    def test_actor_not_null_default_system(self) -> None:
        col = self._columns()["actor"]
        assert col.nullable is False
        assert col.server_default is not None
        assert "system" in str(col.server_default.arg)

    def test_notes_nullable_text(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["notes"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Text)


# ---------------------------------------------------------------------------
# Unit: CHECK constraints — sha256 hex format + non-empty commit SHA
# ---------------------------------------------------------------------------


def _check_constraints(table_name: str) -> dict:
    import sqlalchemy as sa

    call = _table_call(table_name)
    return {c.name: c for c in call.args[1:] if isinstance(c, sa.CheckConstraint)}


class TestProvenanceLogCheckConstraints:
    def test_input_dataset_sha256_regex_check(self) -> None:
        cks = _check_constraints("atlas_provenance_log")
        assert "ck_atlas_provenance_log_input_dataset_sha256_hex" in cks
        ck = cks["ck_atlas_provenance_log_input_dataset_sha256_hex"]
        sqltext = str(ck.sqltext)
        assert "input_dataset_sha256" in sqltext
        assert "[a-f0-9]{64}" in sqltext

    def test_universe_definition_sha256_regex_check(self) -> None:
        cks = _check_constraints("atlas_provenance_log")
        assert "ck_atlas_provenance_log_universe_definition_sha256_hex" in cks
        ck = cks["ck_atlas_provenance_log_universe_definition_sha256_hex"]
        sqltext = str(ck.sqltext)
        assert "universe_definition_sha256" in sqltext
        assert "[a-f0-9]{64}" in sqltext

    def test_code_commit_sha_non_empty_check(self) -> None:
        cks = _check_constraints("atlas_provenance_log")
        assert "ck_atlas_provenance_log_code_commit_sha_non_empty" in cks
        ck = cks["ck_atlas_provenance_log_code_commit_sha_non_empty"]
        sqltext = str(ck.sqltext)
        assert "code_commit_sha" in sqltext
        assert "length" in sqltext.lower()

    def test_all_three_check_constraints_present(self) -> None:
        cks = _check_constraints("atlas_provenance_log")
        assert len(cks) == 3, f"expected 3 CHECK constraints, got {len(cks)}: {list(cks)}"


# ---------------------------------------------------------------------------
# Unit: indexes
# ---------------------------------------------------------------------------


class TestProvenanceLogIndexes:
    def test_ts_desc_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_provenance_log_ts_desc" in names

    def test_output_table_ts_desc_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_provenance_log_output_table_ts_desc" in names

    def test_run_type_ts_desc_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_provenance_log_run_type_ts_desc" in names

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
        assert "atlas.deny_update_delete_provenance" in payloads

    def test_function_raises_exception(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "RAISE EXCEPTION" in payloads
        assert "write-once" in payloads

    def test_function_language_plpgsql(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "LANGUAGE plpgsql" in payloads

    def test_creates_trigger(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "CREATE TRIGGER deny_update_delete_atlas_provenance_log" in payloads

    def test_trigger_fires_before_update_or_delete(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "BEFORE UPDATE OR DELETE" in payloads
        assert "ON atlas.atlas_provenance_log" in payloads

    def test_trigger_for_each_row(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "FOR EACH ROW" in payloads

    def test_trigger_references_function(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "EXECUTE FUNCTION atlas.deny_update_delete_provenance" in payloads


# ---------------------------------------------------------------------------
# Unit: retroactive FK additions
# ---------------------------------------------------------------------------


class TestRetroactiveFKAdditions:
    def _fk_calls(self) -> list:
        mock_op = _run_upgrade_with_mock()
        return list(mock_op.create_foreign_key.call_args_list)

    def test_two_retroactive_fks_added(self) -> None:
        """Exactly two existing tables have provenance_log_id today —
        atlas_ledger (083) and atlas_macro_features_daily (086)."""
        assert len(self._fk_calls()) == 2

    def test_atlas_ledger_fk_added(self) -> None:
        tables = {call.args[1] for call in self._fk_calls()}
        assert "atlas_ledger" in tables

    def test_atlas_macro_features_daily_fk_added(self) -> None:
        tables = {call.args[1] for call in self._fk_calls()}
        assert "atlas_macro_features_daily" in tables

    def test_all_fks_reference_atlas_provenance_log(self) -> None:
        for call in self._fk_calls():
            # Signature: (constraint_name, source_table, referent_table,
            #            local_cols, remote_cols, ...)
            referent = call.args[2]
            assert referent == "atlas_provenance_log", (
                f"FK referent should be atlas_provenance_log, got {referent}"
            )

    def test_all_fks_reference_run_id(self) -> None:
        for call in self._fk_calls():
            remote_cols = call.args[4]
            assert remote_cols == ["run_id"]

    def test_all_fks_target_provenance_log_id_column(self) -> None:
        for call in self._fk_calls():
            local_cols = call.args[3]
            assert local_cols == ["provenance_log_id"]

    def test_all_fks_use_set_null_ondelete(self) -> None:
        for call in self._fk_calls():
            assert call.kwargs.get("ondelete") == "SET NULL"

    def test_all_fks_use_atlas_schema_source_and_referent(self) -> None:
        for call in self._fk_calls():
            assert call.kwargs.get("source_schema") == "atlas"
            assert call.kwargs.get("referent_schema") == "atlas"

    def test_fk_names_follow_convention(self) -> None:
        """Convention: fk_<table>_<column>."""
        names = {call.args[0] for call in self._fk_calls()}
        assert "fk_atlas_ledger_provenance_log_id" in names
        assert "fk_atlas_macro_features_daily_provenance_log_id" in names


# ---------------------------------------------------------------------------
# Unit: enum reuse — 087 introduces no enums
# ---------------------------------------------------------------------------


class TestEnumReuse:
    """087 owns no enums — nothing should be created or dropped via ENUM."""

    def test_does_not_create_any_enum(self) -> None:
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

        assert created_names == [], (
            f"087 must not create any enums (introduces none); created: {created_names}"
        )


# ---------------------------------------------------------------------------
# Unit: downgrade
# ---------------------------------------------------------------------------


class TestDowngrade:
    def test_drops_provenance_log_table(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {"atlas_provenance_log"}

    def test_drops_retroactive_fks(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped_fk_names = {c.args[0] for c in mock_op.drop_constraint.call_args_list}
        assert "fk_atlas_ledger_provenance_log_id" in dropped_fk_names
        assert "fk_atlas_macro_features_daily_provenance_log_id" in dropped_fk_names

    def test_drops_fk_with_foreignkey_type(self) -> None:
        mock_op = _run_downgrade_with_mock()
        for call in mock_op.drop_constraint.call_args_list:
            assert call.kwargs.get("type_") == "foreignkey"

    def test_drops_fk_in_atlas_schema(self) -> None:
        mock_op = _run_downgrade_with_mock()
        for call in mock_op.drop_constraint.call_args_list:
            assert call.kwargs.get("schema") == "atlas"

    def test_drops_fks_before_trigger(self) -> None:
        """FKs reference the target table — must drop FKs first, then
        the trigger / function / table can go."""
        mod = _load()
        events: list[tuple[str, str]] = []

        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record_drop_constraint(name, *_args, **_kwargs) -> None:
                events.append(("drop_constraint", name))

            def _record_execute(sql) -> None:
                events.append(("execute", sql))

            def _record_drop_index(name, *_args, **_kwargs) -> None:
                events.append(("drop_index", name))

            def _record_drop_table(name, *_args, **_kwargs) -> None:
                events.append(("drop_table", name))

            mock_op.drop_constraint.side_effect = _record_drop_constraint
            mock_op.execute.side_effect = _record_execute
            mock_op.drop_index.side_effect = _record_drop_index
            mock_op.drop_table.side_effect = _record_drop_table

            mod.downgrade()

        # First two events should be the FK drops; trigger drop must
        # come AFTER FK drops.
        first_fk_idx = next(i for i, e in enumerate(events) if e[0] == "drop_constraint")
        trigger_drop_idx = next(
            i for i, e in enumerate(events) if e[0] == "execute" and "DROP TRIGGER" in e[1]
        )
        assert first_fk_idx < trigger_drop_idx

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
            if e[0] == "drop_table" and e[1] == "atlas_provenance_log"
        )
        assert function_idx < table_idx

    def test_drops_all_three_indexes(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_index.call_args_list}
        expected = {
            "ix_atlas_provenance_log_ts_desc",
            "ix_atlas_provenance_log_output_table_ts_desc",
            "ix_atlas_provenance_log_run_type_ts_desc",
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
            if e[0] == "drop_table" and e[1] == "atlas_provenance_log"
        )
        assert last_index_idx < table_idx

    def test_drops_no_enums(self) -> None:
        """087 owns no enums — downgrade must not drop any."""
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

        assert dropped_names == [], (
            f"087 owns no enums; downgrade must not drop any: {dropped_names}"
        )


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_provenance_log_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_write_once_blocks_update(self) -> None:
        pytest.skip(
            "verify UPDATE on atlas_provenance_log raises with "
            "'write-once; UPDATE/DELETE not permitted'"
        )

    def test_write_once_blocks_delete(self) -> None:
        pytest.skip(
            "verify DELETE on atlas_provenance_log raises with "
            "'write-once; UPDATE/DELETE not permitted'"
        )

    def test_sha256_check_rejects_non_hex(self) -> None:
        pytest.skip("verify INSERT with input_dataset_sha256 = 'not-hex' raises check_violation")

    def test_code_commit_sha_check_rejects_empty(self) -> None:
        pytest.skip("verify INSERT with code_commit_sha = '' raises check_violation")

    def test_fk_set_null_on_provenance_delete_for_ledger(self) -> None:
        pytest.skip(
            "verify DELETE on atlas_provenance_log row sets atlas_ledger.provenance_log_id NULL"
        )

    def test_fk_set_null_on_provenance_delete_for_macro_features(self) -> None:
        pytest.skip(
            "verify DELETE on atlas_provenance_log row sets "
            "atlas_macro_features_daily.provenance_log_id NULL"
        )
