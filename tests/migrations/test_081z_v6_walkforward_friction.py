# allow-large: full regression coverage for a single migration that creates
# two tables, two enums, four CHECK constraints, three triggers, ten indexes,
# a retroactive FK, twelve friction seed rows, and seven regime threshold
# seed rows — plus matching downgrade ordering assertions. Splitting by
# concern (columns / FKs / triggers / seeds / downgrade) would lose the
# "one migration, one test file" mapping that makes regressions discoverable.
"""Regression tests for migration 081_z — walkforward_runs + friction_params + regime seeds.

Tables created
--------------
- atlas_cell_walkforward_runs  — write-once audit row per walk-forward
  sweep. UPDATE allowed only for the running -> terminal status
  transition; DELETE and post-terminal mutation rejected by a plpgsql
  trigger. Indexed by (tenure, cell_id, run_started_at DESC),
  (cell_id, status), and (provenance_log_id).

- atlas_friction_params        — append-only per-tier × per-component
  table. UPDATE only mutates effective_until / notes; DELETE rejected.

New enums (owned + dropped by 081_z)
------------------------------------
- atlas_walkforward_status  ('running', 'completed', 'failed', 'aborted')
- atlas_friction_component  ('bid_ask', 'impact', 'brokerage', 'slippage')

Reused enums (create_type=False, NOT dropped on downgrade)
----------------------------------------------------------
- atlas_tenure       (from 080)
- atlas_cap_tier     (from 080)

FK relationships
----------------
- atlas_cell_walkforward_runs.provenance_log_id
    -> atlas.atlas_provenance_log(run_id) ON DELETE SET NULL.
- atlas_cell_definitions.walkforward_run_id (retroactive)
    -> atlas.atlas_cell_walkforward_runs(run_id) ON DELETE SET NULL.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, indexes, FKs, CHECK constraints,
trigger creation, enum lifecycle, retroactive FK, and downgrade ordering
match the v6 spec. Also verify the seed payloads.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Skipped by default; run on EC2 / staging.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.081z_v6_walkforward_friction"
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
        assert _load().revision == "081_z"

    def test_down_revision_089(self) -> None:
        """081_z lands AFTER 089 in the chain (082-089 already shipped)."""
        assert _load().down_revision == "089"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() creates the two tables in atlas schema
# ---------------------------------------------------------------------------


class TestUpgradeCreatesTables:
    def test_creates_atlas_cell_walkforward_runs(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_cell_walkforward_runs" in names

    def test_creates_atlas_friction_params(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_friction_params" in names

    def test_creates_exactly_two_tables(self) -> None:
        """081_z is scoped to two new tables — no scope creep."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 2

    def test_walkforward_runs_in_atlas_schema(self) -> None:
        assert _table_call("atlas_cell_walkforward_runs").kwargs.get("schema") == "atlas"

    def test_friction_params_in_atlas_schema(self) -> None:
        assert _table_call("atlas_friction_params").kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: atlas_cell_walkforward_runs columns
# ---------------------------------------------------------------------------


class TestWalkforwardRunsColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_cell_walkforward_runs")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_run_id_pk_uuid_default(self) -> None:
        col = self._columns()["run_id"]
        assert col.primary_key is True
        assert col.server_default is not None
        assert "gen_random_uuid" in str(col.server_default.arg)

    def test_run_started_at_not_null_tz_aware_now_default(self) -> None:
        col = self._columns()["run_started_at"]
        assert col.nullable is False
        assert col.type.timezone is True
        assert col.server_default is not None
        assert "NOW" in str(col.server_default.arg).upper()

    def test_run_completed_at_nullable_tz_aware(self) -> None:
        col = self._columns()["run_completed_at"]
        assert col.nullable is True
        assert col.type.timezone is True

    def test_universe_snapshot_id_not_null_uuid(self) -> None:
        from sqlalchemy.dialects.postgresql import UUID

        col = self._columns()["universe_snapshot_id"]
        assert col.nullable is False
        assert isinstance(col.type, UUID)

    def test_tenure_not_null_uses_tenure_enum(self) -> None:
        col = self._columns()["tenure"]
        assert col.nullable is False
        assert getattr(col.type, "name", None) == "atlas_tenure"

    def test_cell_id_nullable_uuid(self) -> None:
        """Nullable because a run may DISCOVER a new cell."""
        from sqlalchemy.dialects.postgresql import UUID

        col = self._columns()["cell_id"]
        assert col.nullable is True
        assert isinstance(col.type, UUID)

    def test_window_train_start_not_null_date(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["window_train_start"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Date)

    def test_window_train_end_not_null_date(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["window_train_end"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Date)

    def test_window_test_start_not_null_date(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["window_test_start"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Date)

    def test_window_test_end_not_null_date(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["window_test_end"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Date)

    def test_tp_rate_nullable_numeric_5_4(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["tp_rate"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 5
        assert col.type.scale == 4

    def test_tn_rate_nullable_numeric_5_4(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["tn_rate"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 5
        assert col.type.scale == 4

    def test_n_observations_not_null_integer(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["n_observations"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Integer)

    def test_stable_features_nullable_jsonb(self) -> None:
        from sqlalchemy.dialects.postgresql import JSONB

        col = self._columns()["stable_features"]
        assert col.nullable is True
        assert isinstance(col.type, JSONB)

    def test_methodology_lock_ref_not_null_varchar_64(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["methodology_lock_ref"]
        assert col.nullable is False
        assert isinstance(col.type, sa.String)
        assert col.type.length == 64

    def test_provenance_log_id_nullable_uuid(self) -> None:
        from sqlalchemy.dialects.postgresql import UUID

        col = self._columns()["provenance_log_id"]
        assert col.nullable is True
        assert isinstance(col.type, UUID)

    def test_status_not_null_uses_walkforward_status_enum(self) -> None:
        col = self._columns()["status"]
        assert col.nullable is False
        assert getattr(col.type, "name", None) == "atlas_walkforward_status"

    def test_percentile_columns_present_and_numeric_10_6(self) -> None:
        import sqlalchemy as sa

        cols = self._columns()
        for name in (
            "percentile_10",
            "percentile_25",
            "percentile_50",
            "percentile_75",
            "percentile_90",
            "median_excess",
            "mean_excess",
            "friction_adjusted_excess",
        ):
            col = cols[name]
            assert col.nullable is True, f"{name} should be nullable"
            assert isinstance(col.type, sa.Numeric)
            assert col.type.precision == 10
            assert col.type.scale == 6

    def test_notes_nullable_text(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["notes"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Text)


# ---------------------------------------------------------------------------
# Unit: atlas_friction_params columns
# ---------------------------------------------------------------------------


class TestFrictionParamsColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_friction_params")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_id_pk_uuid_default(self) -> None:
        col = self._columns()["id"]
        assert col.primary_key is True
        assert col.server_default is not None
        assert "gen_random_uuid" in str(col.server_default.arg)

    def test_cap_tier_not_null_uses_cap_tier_enum(self) -> None:
        col = self._columns()["cap_tier"]
        assert col.nullable is False
        assert getattr(col.type, "name", None) == "atlas_cap_tier"

    def test_component_not_null_uses_friction_component_enum(self) -> None:
        col = self._columns()["component"]
        assert col.nullable is False
        assert getattr(col.type, "name", None) == "atlas_friction_component"

    def test_value_not_null_numeric_8_6(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["value"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 8
        assert col.type.scale == 6

    def test_effective_from_not_null_date(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["effective_from"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Date)

    def test_effective_until_nullable_date(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["effective_until"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Date)

    def test_created_at_not_null_tz_aware_now(self) -> None:
        col = self._columns()["created_at"]
        assert col.nullable is False
        assert col.type.timezone is True
        assert "NOW" in str(col.server_default.arg).upper()


# ---------------------------------------------------------------------------
# Unit: CHECK constraints on both tables
# ---------------------------------------------------------------------------


def _check_constraints(table_name: str) -> dict:
    import sqlalchemy as sa

    call = _table_call(table_name)
    return {c.name: c for c in call.args[1:] if isinstance(c, sa.CheckConstraint)}


class TestWalkforwardRunsCheckConstraints:
    def test_window_order_check(self) -> None:
        cks = _check_constraints("atlas_cell_walkforward_runs")
        assert "ck_atlas_cell_walkforward_runs_window_order" in cks
        sqltext = str(cks["ck_atlas_cell_walkforward_runs_window_order"].sqltext)
        assert "window_train_end" in sqltext
        assert "window_test_start" in sqltext
        assert "<=" in sqltext

    def test_n_observations_non_negative_check(self) -> None:
        cks = _check_constraints("atlas_cell_walkforward_runs")
        assert "ck_atlas_cell_walkforward_runs_n_observations_non_negative" in cks
        sqltext = str(cks["ck_atlas_cell_walkforward_runs_n_observations_non_negative"].sqltext)
        assert "n_observations" in sqltext

    def test_tp_rate_range_check(self) -> None:
        cks = _check_constraints("atlas_cell_walkforward_runs")
        assert "ck_atlas_cell_walkforward_runs_tp_rate_range" in cks
        sqltext = str(cks["ck_atlas_cell_walkforward_runs_tp_rate_range"].sqltext)
        assert "tp_rate" in sqltext

    def test_tn_rate_range_check(self) -> None:
        cks = _check_constraints("atlas_cell_walkforward_runs")
        assert "ck_atlas_cell_walkforward_runs_tn_rate_range" in cks
        sqltext = str(cks["ck_atlas_cell_walkforward_runs_tn_rate_range"].sqltext)
        assert "tn_rate" in sqltext


class TestFrictionParamsCheckConstraints:
    def test_value_non_negative_check(self) -> None:
        cks = _check_constraints("atlas_friction_params")
        assert "ck_atlas_friction_params_value_non_negative" in cks
        sqltext = str(cks["ck_atlas_friction_params_value_non_negative"].sqltext)
        assert "value" in sqltext

    def test_effective_range_check(self) -> None:
        cks = _check_constraints("atlas_friction_params")
        assert "ck_atlas_friction_params_effective_range" in cks
        sqltext = str(cks["ck_atlas_friction_params_effective_range"].sqltext)
        assert "effective_until" in sqltext
        assert "effective_from" in sqltext


# ---------------------------------------------------------------------------
# Unit: UNIQUE constraint on atlas_friction_params
# ---------------------------------------------------------------------------


class TestFrictionParamsUniqueConstraint:
    def test_unique_tier_component_from(self) -> None:
        import sqlalchemy as sa

        call = _table_call("atlas_friction_params")
        uniques = [c for c in call.args[1:] if isinstance(c, sa.UniqueConstraint)]
        names = {u.name for u in uniques}
        assert "uq_atlas_friction_params_tier_component_from" in names

    def test_unique_covers_three_columns(self) -> None:
        import sqlalchemy as sa

        call = _table_call("atlas_friction_params")
        uniques = [c for c in call.args[1:] if isinstance(c, sa.UniqueConstraint)]
        target = next(
            u for u in uniques if u.name == "uq_atlas_friction_params_tier_component_from"
        )
        # UniqueConstraint declared with column-name strings stores them
        # in _pending_colargs until the constraint is bound to a Table;
        # in the unit context (no Table bind) we inspect that attribute.
        cols = set(target._pending_colargs)
        assert cols == {"cap_tier", "component", "effective_from"}


# ---------------------------------------------------------------------------
# Unit: FKs
# ---------------------------------------------------------------------------


class TestWalkforwardRunsForeignKeys:
    def _fks_for(self, column_name: str) -> list:
        call = _table_call("atlas_cell_walkforward_runs")
        cols = {c.name: c for c in call.args[1:] if hasattr(c, "name")}
        col = cols[column_name]
        return list(col.foreign_keys)

    def test_provenance_log_id_fk_target(self) -> None:
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

    def test_universe_snapshot_id_no_fk_yet(self) -> None:
        """atlas_universe_snapshot is a Phase 0.5a future addition; the
        column is a plain UUID with no FK target for now."""
        fks = self._fks_for("universe_snapshot_id")
        assert fks == []

    def test_cell_id_no_fk(self) -> None:
        """cell_id is intentionally NOT FK'd — a run may DISCOVER a cell
        before the cell row exists."""
        fks = self._fks_for("cell_id")
        assert fks == []


class TestRetroactiveCellDefinitionsFK:
    """The walkforward_run_id column was declared on atlas_cell_definitions
    by migration 080; 081_z adds the FK now that the target exists."""

    def test_creates_walkforward_run_id_fk(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_foreign_key.call_args_list}
        assert "fk_atlas_cell_definitions_walkforward_run_id" in names

    def test_fk_targets_atlas_cell_walkforward_runs(self) -> None:
        mock_op = _run_upgrade_with_mock()
        call = next(
            c
            for c in mock_op.create_foreign_key.call_args_list
            if c.args[0] == "fk_atlas_cell_definitions_walkforward_run_id"
        )
        assert call.args[1] == "atlas_cell_definitions"
        assert call.args[2] == "atlas_cell_walkforward_runs"
        assert call.args[3] == ["walkforward_run_id"]
        assert call.args[4] == ["run_id"]

    def test_fk_ondelete_set_null(self) -> None:
        mock_op = _run_upgrade_with_mock()
        call = next(
            c
            for c in mock_op.create_foreign_key.call_args_list
            if c.args[0] == "fk_atlas_cell_definitions_walkforward_run_id"
        )
        assert call.kwargs.get("ondelete") == "SET NULL"

    def test_fk_in_atlas_schemas(self) -> None:
        mock_op = _run_upgrade_with_mock()
        call = next(
            c
            for c in mock_op.create_foreign_key.call_args_list
            if c.args[0] == "fk_atlas_cell_definitions_walkforward_run_id"
        )
        assert call.kwargs.get("source_schema") == "atlas"
        assert call.kwargs.get("referent_schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: indexes
# ---------------------------------------------------------------------------


class TestWalkforwardRunsIndexes:
    def test_tenure_cell_started_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_cell_walkforward_runs_tenure_cell_started_desc" in names

    def test_cell_status_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_cell_walkforward_runs_cell_status" in names

    def test_provenance_index_created(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_cell_walkforward_runs_provenance" in names


class TestFrictionParamsPartialIndex:
    def test_partial_current_index_emitted_via_execute(self) -> None:
        mock_op = _run_upgrade_with_mock()
        payloads = " ".join(c.args[0] for c in mock_op.execute.call_args_list)
        assert "ix_atlas_friction_params_current" in payloads
        # WHERE effective_until IS NULL signals partial index for "current" rows.
        assert "WHERE effective_until IS NULL" in payloads


# ---------------------------------------------------------------------------
# Unit: write-once / append-only triggers
# ---------------------------------------------------------------------------


def _execute_payloads() -> list[str]:
    mock_op = _run_upgrade_with_mock()
    payloads: list[str] = []
    for c in mock_op.execute.call_args_list:
        arg = c.args[0]
        payloads.append(arg if isinstance(arg, str) else str(arg))
    return payloads


class TestWalkforwardRunsTrigger:
    def test_creates_plpgsql_function(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "CREATE OR REPLACE FUNCTION" in payloads
        assert "atlas.guard_walkforward_run_mutation" in payloads

    def test_denies_delete(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "DELETE not permitted" in payloads

    def test_blocks_unsetting_run_completed_at(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "run_completed_at is write-once" in payloads

    def test_blocks_terminal_to_running(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "terminal back to running" in payloads

    def test_function_language_plpgsql(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "LANGUAGE plpgsql" in payloads

    def test_creates_trigger(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "CREATE TRIGGER guard_atlas_cell_walkforward_runs_mutation" in payloads

    def test_trigger_fires_before_update_or_delete(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "BEFORE UPDATE OR DELETE ON atlas.atlas_cell_walkforward_runs" in payloads


class TestFrictionParamsTrigger:
    def test_creates_plpgsql_function(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "atlas.guard_friction_params_mutation" in payloads

    def test_blocks_delete(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "atlas_friction_params is append-only" in payloads
        assert "DELETE not permitted" in payloads

    def test_blocks_mutation_of_identity_columns(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "cap_tier" in payloads
        assert "component" in payloads
        assert "effective_from" in payloads

    def test_blocks_unsetting_effective_until(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "effective_until cannot be un-set" in payloads

    def test_creates_trigger(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "CREATE TRIGGER guard_atlas_friction_params_mutation" in payloads

    def test_trigger_fires_before_update_or_delete(self) -> None:
        payloads = " ".join(_execute_payloads())
        assert "BEFORE UPDATE OR DELETE ON atlas.atlas_friction_params" in payloads


# ---------------------------------------------------------------------------
# Unit: enum lifecycle — 081_z owns walkforward_status + friction_component
# ---------------------------------------------------------------------------


class TestEnumLifecycleUpgrade:
    """081_z owns atlas_walkforward_status + atlas_friction_component.
    atlas_tenure and atlas_cap_tier are reused from 080 and must NOT be
    (re)created here."""

    def _record_create(self) -> list[str]:
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

        return created_names

    def test_creates_atlas_walkforward_status_enum(self) -> None:
        assert "atlas_walkforward_status" in self._record_create()

    def test_creates_atlas_friction_component_enum(self) -> None:
        assert "atlas_friction_component" in self._record_create()

    def test_does_not_recreate_atlas_tenure(self) -> None:
        assert "atlas_tenure" not in self._record_create()

    def test_does_not_recreate_atlas_cap_tier(self) -> None:
        assert "atlas_cap_tier" not in self._record_create()

    def test_walkforward_status_values(self) -> None:
        mod = _load()
        assert mod.WALKFORWARD_STATUS == (
            "running",
            "completed",
            "failed",
            "aborted",
        )

    def test_friction_component_values(self) -> None:
        mod = _load()
        assert mod.FRICTION_COMPONENT == (
            "bid_ask",
            "impact",
            "brokerage",
            "slippage",
        )


# ---------------------------------------------------------------------------
# Unit: seed payloads
# ---------------------------------------------------------------------------


class TestFrictionSeeds:
    def test_twelve_rows(self) -> None:
        assert len(_load().FRICTION_SEEDS) == 12

    def test_three_tiers_four_components(self) -> None:
        seeds = _load().FRICTION_SEEDS
        tiers = {row[0] for row in seeds}
        components = {row[1] for row in seeds}
        assert tiers == {"Small", "Mid", "Large"}
        assert components == {"bid_ask", "impact", "brokerage", "slippage"}

    def test_full_cross_product(self) -> None:
        """Each (tier, component) pair must appear exactly once."""
        seeds = _load().FRICTION_SEEDS
        pairs = [(row[0], row[1]) for row in seeds]
        assert len(pairs) == 12
        assert len(set(pairs)) == 12, "duplicate (tier, component) pairs in seeds"

    def test_small_bid_ask_wider_than_large(self) -> None:
        """Sanity: small caps have wider spreads than large caps."""
        from decimal import Decimal

        seeds = _load().FRICTION_SEEDS
        small = next(Decimal(row[2]) for row in seeds if row[0] == "Small" and row[1] == "bid_ask")
        large = next(Decimal(row[2]) for row in seeds if row[0] == "Large" and row[1] == "bid_ask")
        assert small > large

    def test_all_values_non_negative_strings(self) -> None:
        from decimal import Decimal

        for row in _load().FRICTION_SEEDS:
            assert Decimal(row[2]) >= 0

    def test_brokerage_uniform_across_tiers(self) -> None:
        """Indian brokerage (Zerodha-style) is flat 3bps across tiers."""
        from decimal import Decimal

        seeds = _load().FRICTION_SEEDS
        brokerage = {row[0]: Decimal(row[2]) for row in seeds if row[1] == "brokerage"}
        assert brokerage["Small"] == brokerage["Mid"] == brokerage["Large"]

    def test_effective_from_set(self) -> None:
        assert _load().FRICTION_SEED_EFFECTIVE_FROM == "2026-05-24"

    def test_seed_notes_marked_placeholder(self) -> None:
        notes = _load().FRICTION_SEED_NOTES
        assert "placeholder" in notes.lower()
        assert "0.5d" in notes.lower() or "phase 0.5d" in notes.lower()


class TestRegimeThresholdSeeds:
    def test_seven_rows(self) -> None:
        assert len(_load().REGIME_THRESHOLD_SEEDS) == 7

    def test_expected_keys_present(self) -> None:
        keys = {row[0] for row in _load().REGIME_THRESHOLD_SEEDS}
        expected = {
            "regime.smallcap_rs_z.below_trend_threshold",
            "regime.smallcap_rs_z.risk_off_threshold",
            "regime.breadth.below_trend_threshold",
            "regime.breadth.risk_off_threshold",
            "regime.vix_pct.elevated_threshold",
            "regime.vix_pct.risk_off_threshold",
            "regime.dispersion.elevated_threshold",
        }
        assert keys == expected

    def test_smallcap_below_trend_value(self) -> None:
        from decimal import Decimal

        row = next(
            r
            for r in _load().REGIME_THRESHOLD_SEEDS
            if r[0] == "regime.smallcap_rs_z.below_trend_threshold"
        )
        assert Decimal(row[1]) == Decimal("-1.0")

    def test_breadth_risk_off_value(self) -> None:
        from decimal import Decimal

        row = next(
            r for r in _load().REGIME_THRESHOLD_SEEDS if r[0] == "regime.breadth.risk_off_threshold"
        )
        assert Decimal(row[1]) == Decimal("0.2")

    def test_vix_elevated_value(self) -> None:
        from decimal import Decimal

        row = next(
            r for r in _load().REGIME_THRESHOLD_SEEDS if r[0] == "regime.vix_pct.elevated_threshold"
        )
        assert Decimal(row[1]) == Decimal("0.7")

    def test_each_seed_within_min_max(self) -> None:
        """Catches the atlas_thresholds CHECK constraint (threshold_value
        BETWEEN min_allowed AND max_allowed) before live DB sees it."""
        from decimal import Decimal

        for row in _load().REGIME_THRESHOLD_SEEDS:
            value = Decimal(row[1])
            min_allowed = Decimal(row[6])
            max_allowed = Decimal(row[7])
            assert (
                min_allowed <= value <= max_allowed
            ), f"{row[0]} value {value} outside [{min_allowed}, {max_allowed}]"


# ---------------------------------------------------------------------------
# Unit: friction seed INSERT execution
# ---------------------------------------------------------------------------


class TestFrictionSeedExecution:
    def test_friction_inserts_use_on_conflict_do_nothing(self) -> None:
        """Re-applying the migration must not duplicate seed rows."""
        mod = _load()
        executed: list[str] = []

        with patch.object(mod, "op") as mock_op:
            mock_bind = MagicMock()

            def _record(sql, *_args, **_kwargs) -> MagicMock:
                executed.append(str(sql))
                return MagicMock()

            mock_bind.execute.side_effect = _record
            mock_op.get_bind.return_value = mock_bind
            mod.upgrade()

        joined = " ".join(executed)
        assert "INSERT INTO atlas.atlas_friction_params" in joined
        assert "ON CONFLICT" in joined
        assert "DO NOTHING" in joined

    def test_friction_inserts_fire_twelve_times(self) -> None:
        """One INSERT statement per (cap_tier, component) row."""
        mod = _load()
        executed: list[str] = []

        with patch.object(mod, "op") as mock_op:
            mock_bind = MagicMock()

            def _record(sql, *_args, **_kwargs) -> MagicMock:
                executed.append(str(sql))
                return MagicMock()

            mock_bind.execute.side_effect = _record
            mock_op.get_bind.return_value = mock_bind
            mod.upgrade()

        friction_inserts = [s for s in executed if "atlas_friction_params" in s and "INSERT" in s]
        assert len(friction_inserts) == 12

    def test_regime_threshold_inserts_fire_seven_times(self) -> None:
        mod = _load()
        executed: list[str] = []

        with patch.object(mod, "op") as mock_op:
            mock_bind = MagicMock()

            def _record(sql, *_args, **_kwargs) -> MagicMock:
                executed.append(str(sql))
                return MagicMock()

            mock_bind.execute.side_effect = _record
            mock_op.get_bind.return_value = mock_bind
            mod.upgrade()

        threshold_inserts = [s for s in executed if "atlas_thresholds" in s and "INSERT" in s]
        assert len(threshold_inserts) == 7


# ---------------------------------------------------------------------------
# Unit: downgrade
# ---------------------------------------------------------------------------


class TestDowngradeTableDrops:
    def test_drops_both_tables(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {"atlas_cell_walkforward_runs", "atlas_friction_params"}


class TestDowngradeDropsRetroactiveFK:
    def test_drops_walkforward_run_id_fk(self) -> None:
        mock_op = _run_downgrade_with_mock()
        names = {c.args[0] for c in mock_op.drop_constraint.call_args_list}
        assert "fk_atlas_cell_definitions_walkforward_run_id" in names

    def test_drops_fk_before_table(self) -> None:
        mod = _load()
        events: list[tuple[str, str]] = []

        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record_drop_constraint(name, *_args, **_kwargs) -> None:
                events.append(("drop_constraint", name))

            def _record_drop_table(name, *_args, **_kwargs) -> None:
                events.append(("drop_table", name))

            mock_op.drop_constraint.side_effect = _record_drop_constraint
            mock_op.drop_table.side_effect = _record_drop_table
            mod.downgrade()

        fk_idx = next(
            i
            for i, e in enumerate(events)
            if e[0] == "drop_constraint" and e[1] == "fk_atlas_cell_definitions_walkforward_run_id"
        )
        table_idx = next(
            i
            for i, e in enumerate(events)
            if e[0] == "drop_table" and e[1] == "atlas_cell_walkforward_runs"
        )
        assert fk_idx < table_idx, "FK must be dropped before its target table"


class TestDowngradeTriggerOrder:
    def test_drops_triggers_before_functions(self) -> None:
        mod = _load()
        execute_payloads: list[str] = []

        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record_execute(sql) -> None:
                execute_payloads.append(sql)

            mock_op.execute.side_effect = _record_execute
            mod.downgrade()

        trigger_indices = [i for i, p in enumerate(execute_payloads) if "DROP TRIGGER" in p]
        function_indices = [i for i, p in enumerate(execute_payloads) if "DROP FUNCTION" in p]
        assert trigger_indices and function_indices
        assert max(trigger_indices) < min(function_indices)

    def test_drops_both_trigger_functions(self) -> None:
        mod = _load()
        executed: list[str] = []

        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record_execute(sql) -> None:
                executed.append(sql)

            mock_op.execute.side_effect = _record_execute
            mod.downgrade()

        joined = " ".join(executed)
        assert "DROP FUNCTION IF EXISTS atlas.guard_walkforward_run_mutation" in joined
        assert "DROP FUNCTION IF EXISTS atlas.guard_friction_params_mutation" in joined


class TestDowngradeRemovesSeeds:
    def test_deletes_regime_threshold_seeds(self) -> None:
        mod = _load()
        executed: list[str] = []

        with patch.object(mod, "op") as mock_op:
            mock_bind = MagicMock()

            def _record(sql, *_args, **_kwargs) -> MagicMock:
                executed.append(str(sql))
                return MagicMock()

            mock_bind.execute.side_effect = _record
            mock_op.get_bind.return_value = mock_bind
            mod.downgrade()

        joined = " ".join(executed)
        assert "DELETE FROM atlas.atlas_thresholds" in joined
        assert "threshold_key" in joined


class TestDowngradeEnumDrops:
    def _record_drops(self) -> list[str]:
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

        return dropped_names

    def test_drops_walkforward_status_enum(self) -> None:
        assert "atlas_walkforward_status" in self._record_drops()

    def test_drops_friction_component_enum(self) -> None:
        assert "atlas_friction_component" in self._record_drops()

    def test_does_not_drop_atlas_tenure(self) -> None:
        assert (
            "atlas_tenure" not in self._record_drops()
        ), "atlas_tenure owned by 080; 081_z must not drop it"

    def test_does_not_drop_atlas_cap_tier(self) -> None:
        assert (
            "atlas_cap_tier" not in self._record_drops()
        ), "atlas_cap_tier owned by 080; 081_z must not drop it"


class TestDowngradeIndexDrops:
    def test_drops_all_three_named_indexes(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_index.call_args_list}
        expected = {
            "ix_atlas_cell_walkforward_runs_provenance",
            "ix_atlas_cell_walkforward_runs_cell_status",
            "ix_atlas_cell_walkforward_runs_tenure_cell_started_desc",
        }
        missing = expected - dropped
        assert not missing, f"missing index drops on downgrade: {missing}"

    def test_drops_partial_friction_index(self) -> None:
        mod = _load()
        executed: list[str] = []

        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()

            def _record_execute(sql) -> None:
                executed.append(sql)

            mock_op.execute.side_effect = _record_execute
            mod.downgrade()

        joined = " ".join(executed)
        assert "DROP INDEX IF EXISTS atlas.ix_atlas_friction_params_current" in joined


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_walkforward_runs_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_friction_params_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_friction_seed_rowcount_twelve(self) -> None:
        pytest.skip("verify SELECT COUNT(*) FROM atlas.atlas_friction_params = 12")

    def test_regime_threshold_seed_rowcount_seven(self) -> None:
        pytest.skip(
            "verify SELECT COUNT(*) FROM atlas.atlas_thresholds WHERE "
            "threshold_key LIKE 'regime.%' >= 7"
        )

    def test_walkforward_delete_blocked(self) -> None:
        pytest.skip("verify DELETE raises 'DELETE not permitted'")

    def test_walkforward_terminal_to_running_blocked(self) -> None:
        pytest.skip("verify UPDATE status: 'completed' -> 'running' raises")

    def test_walkforward_unset_completed_at_blocked(self) -> None:
        pytest.skip("verify UPDATE run_completed_at: non-null -> null raises")

    def test_friction_delete_blocked(self) -> None:
        pytest.skip("verify DELETE raises 'append-only; DELETE not permitted'")

    def test_friction_value_mutation_blocked(self) -> None:
        pytest.skip("verify UPDATE friction value raises append-only")

    def test_friction_effective_until_mutation_allowed(self) -> None:
        pytest.skip("verify UPDATE effective_until from NULL to a date is permitted")

    def test_cell_definitions_fk_set_null_on_walkforward_delete(self) -> None:
        pytest.skip(
            "verify DELETE on atlas_cell_walkforward_runs nulls "
            "atlas_cell_definitions.walkforward_run_id"
        )
