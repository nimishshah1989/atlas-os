"""Regression tests for migration 089 — v5 deprecation flags + v6 placeholder seed.

Scope
-----
1. Every v5 atlas_* table created in migrations 060–079 gets a nullable
   ``deprecated_at TIMESTAMPTZ`` column + table COMMENT (read-only marker,
   NOT enforcement — see CONTEXT.md §"Migration cutover" + /grill Q10
   Path A).

2. 12 PLACEHOLDER rows seeded into ``atlas.atlas_cell_definitions``
   covering every (cap_tier × action × tenure) tuple where
   action ∈ {POSITIVE, NEGATIVE} and tenure ∈ {6m, 12m}. Real values
   ship from Phase 0.5g 24-framework discovery (issue #25).

3. ``atlas_thresholds`` regime placeholder seeding is SKIPPED — the
   column type (NUMERIC + range CHECK) cannot hold a string sentinel
   like 'PLACEHOLDER'. Documented in the migration docstring.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify add_column for each v5 atlas_* table,
bulk_insert covers 12 cells, every placeholder carries the locked
methodology_lock_ref, table COMMENT is set, and downgrade DELETEs
placeholders before dropping columns.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the migration applies cleanly on a real Postgres + that the
deprecated_at column is queryable + that placeholder rows obey the
partial unique constraint from migration 080. Skipped by default.
"""

from __future__ import annotations

import importlib
import json
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.089_v6_v5_deprecation_and_seed"
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


# ---------------------------------------------------------------------------
# Unit: metadata
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    def test_revision(self) -> None:
        assert _load().revision == "089"

    def test_down_revision_088(self) -> None:
        assert _load().down_revision == "088"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None

    def test_schema_constant(self) -> None:
        assert _load()._SCHEMA == "atlas"


# ---------------------------------------------------------------------------
# Unit: v5 atlas_* tables marked deprecated — add_column invariants
# ---------------------------------------------------------------------------


class TestV5DeprecationList:
    """The migration must publish the v5 deprecation list and act on it."""

    def test_list_is_non_empty(self) -> None:
        mod = _load()
        assert len(mod.V5_DEPRECATED_TABLES) > 0

    def test_list_contains_canonical_v5_tables(self) -> None:
        """Sanity-check: explicit candidates from CEO plan must be present."""
        mod = _load()
        canonical = {
            "atlas_stock_state_daily",
            "atlas_state_dwell_statistics",
            "atlas_state_thresholds",
            "atlas_state_action_log",
            "atlas_component_validation",
            "atlas_strategy_leaderboard",
        }
        missing = canonical - set(mod.V5_DEPRECATED_TABLES)
        assert not missing, f"missing canonical v5 tables: {missing}"

    def test_list_excludes_v6_tables(self) -> None:
        """v6 trunk tables must NOT be flagged deprecated."""
        mod = _load()
        v6_trunk = {
            "atlas_scorecard_daily",
            "atlas_signal_calls",
            "atlas_cell_definitions",
            "atlas_regime_daily",
            "atlas_brief_cache",
            "atlas_ledger",
            "atlas_paper_portfolio",
            "atlas_user_lots",
            "atlas_provenance_log",
            "atlas_drift_event_log",
        }
        overlap = v6_trunk & set(mod.V5_DEPRECATED_TABLES)
        assert not overlap, f"v6 trunk tables marked deprecated: {overlap}"

    def test_list_is_immutable_tuple(self) -> None:
        mod = _load()
        assert isinstance(mod.V5_DEPRECATED_TABLES, tuple)


class TestUpgradeAddsDeprecatedAtColumn:
    def test_add_column_called_for_every_v5_table(self) -> None:
        mod = _load()
        mock_op = _run_upgrade_with_mock()
        targets = {c.args[0] for c in mock_op.add_column.call_args_list}
        missing = set(mod.V5_DEPRECATED_TABLES) - targets
        assert not missing, f"add_column missing for: {missing}"

    def test_add_column_count_matches_list(self) -> None:
        mod = _load()
        mock_op = _run_upgrade_with_mock()
        assert mock_op.add_column.call_count == len(mod.V5_DEPRECATED_TABLES)

    def test_added_column_named_deprecated_at(self) -> None:
        mock_op = _run_upgrade_with_mock()
        for call in mock_op.add_column.call_args_list:
            col = call.args[1]
            assert col.name == "deprecated_at", (
                f"add_column on {call.args[0]} added column "
                f"{col.name!r}; expected 'deprecated_at'"
            )

    def test_added_column_is_tz_aware_datetime(self) -> None:
        import sqlalchemy as sa

        mock_op = _run_upgrade_with_mock()
        for call in mock_op.add_column.call_args_list:
            col = call.args[1]
            assert isinstance(col.type, sa.DateTime), (
                f"add_column on {call.args[0]} type is {col.type!r}; " f"expected sa.DateTime"
            )
            assert col.type.timezone is True

    def test_added_column_is_nullable(self) -> None:
        mock_op = _run_upgrade_with_mock()
        for call in mock_op.add_column.call_args_list:
            col = call.args[1]
            assert (
                col.nullable is True
            ), f"add_column on {call.args[0]} not nullable — must be NULL by default"

    def test_add_column_uses_atlas_schema(self) -> None:
        mock_op = _run_upgrade_with_mock()
        for call in mock_op.add_column.call_args_list:
            assert (
                call.kwargs.get("schema") == "atlas"
            ), f"add_column on {call.args[0]} not in atlas schema"


# ---------------------------------------------------------------------------
# Unit: table COMMENT — each v5 atlas_* table gets the canonical comment
# ---------------------------------------------------------------------------


def _execute_payloads_upgrade() -> list[str]:
    mock_op = _run_upgrade_with_mock()
    payloads: list[str] = []
    for call in mock_op.execute.call_args_list:
        arg = call.args[0]
        # alembic.op.execute accepts both sa.TextClause and str — both
        # render their SQL via str().
        payloads.append(str(arg))
    return payloads


class TestUpgradeSetsTableComment:
    def test_comment_executed_for_every_v5_table(self) -> None:
        mod = _load()
        payloads = " ".join(_execute_payloads_upgrade())
        for table in mod.V5_DEPRECATED_TABLES:
            assert (
                f"COMMENT ON TABLE atlas.{table}" in payloads
            ), f"COMMENT ON TABLE missing for {table}"

    def test_comment_message_mentions_v5_and_v6_trunk(self) -> None:
        mod = _load()
        comment = mod._DEPRECATED_COMMENT
        assert "v5" in comment
        assert "atlas_signal_calls" in comment
        assert "atlas_scorecard_daily" in comment


# ---------------------------------------------------------------------------
# Unit: placeholder cell_definitions seed — bulk_insert invariants
# ---------------------------------------------------------------------------


def _bulk_insert_rows() -> list[dict[str, object]]:
    mock_op = _run_upgrade_with_mock()
    assert (
        mock_op.bulk_insert.call_count == 1
    ), f"expected exactly one bulk_insert call, got {mock_op.bulk_insert.call_count}"
    call = mock_op.bulk_insert.call_args_list[0]
    return call.args[1]


class TestPlaceholderSeed:
    def test_seed_inserts_12_rows(self) -> None:
        rows = _bulk_insert_rows()
        assert len(rows) == 12, f"expected 12 placeholder rows, got {len(rows)}"

    def test_seed_targets_atlas_cell_definitions(self) -> None:
        mock_op = _run_upgrade_with_mock()
        target = mock_op.bulk_insert.call_args_list[0].args[0]
        assert target.name == "atlas_cell_definitions"
        # sqlalchemy.sql.table puts the schema on the Table's schema attr
        # when passed via schema= kwarg.
        assert getattr(target, "schema", None) == "atlas"

    def test_every_row_has_placeholder_methodology_lock_ref(self) -> None:
        rows = _bulk_insert_rows()
        bad = [r for r in rows if r["methodology_lock_ref"] != "PLACEHOLDER_2026-05-24"]
        assert not bad, f"rows with wrong methodology_lock_ref: {bad}"

    def test_methodology_lock_ref_constant_published(self) -> None:
        mod = _load()
        assert mod.PLACEHOLDER_METHODOLOGY_LOCK_REF == "PLACEHOLDER_2026-05-24"

    def test_rows_cover_all_cap_tier_action_tenure_combos(self) -> None:
        rows = _bulk_insert_rows()
        seen: set[tuple[str, str, str]] = {
            (str(r["cap_tier"]), str(r["action"]), str(r["tenure"])) for r in rows
        }
        expected: set[tuple[str, str, str]] = {
            (tier, action, tenure)
            for tier in ("Small", "Mid", "Large")
            for action in ("POSITIVE", "NEGATIVE")
            for tenure in ("6m", "12m")
        }
        assert (
            seen == expected
        ), f"missing combos: {expected - seen}; extra combos: {seen - expected}"

    def test_every_combo_appears_exactly_once(self) -> None:
        """Partial unique index uq_atlas_cell_definitions_active requires
        (cap_tier, action, tenure) unique while deprecated_at IS NULL.
        Each placeholder leaves deprecated_at NULL — duplicates would
        violate the constraint at apply time.
        """
        rows = _bulk_insert_rows()
        combos = [(r["cap_tier"], r["action"], r["tenure"]) for r in rows]
        assert len(combos) == len(set(combos)), "duplicate combos would break partial UQ index"

    def test_every_row_has_distinct_cell_id(self) -> None:
        rows = _bulk_insert_rows()
        cell_ids = [r["cell_id"] for r in rows]
        assert len(set(cell_ids)) == len(cell_ids), "cell_id collision in placeholder seed"

    def test_rule_dsl_is_valid_json_with_placeholder_marker(self) -> None:
        rows = _bulk_insert_rows()
        for r in rows:
            dsl = json.loads(str(r["rule_dsl"]))
            assert dsl["rule_type"] == "placeholder"
            assert dsl["methodology_lock_ref"] == "PLACEHOLDER_2026-05-24"
            assert dsl["rule_version"] == 0
            # eligibility + entry start empty — real rules ship from Phase 0.5g
            assert dsl["eligibility"] == []
            assert dsl["entry"] == []

    def test_rule_dsl_carries_tier_action_tenure(self) -> None:
        rows = _bulk_insert_rows()
        for r in rows:
            dsl = json.loads(str(r["rule_dsl"]))
            assert dsl["tier"] == r["cap_tier"]
            assert dsl["action"] == r["action"]
            assert dsl["tenure"] == r["tenure"]

    def test_metric_columns_left_null(self) -> None:
        """Real values come from Phase 0.5g walk-forward; placeholders
        leave them NULL so dashboards can filter cleanly."""
        rows = _bulk_insert_rows()
        for r in rows:
            assert r["confidence_unconditional"] is None
            assert r["friction_adjusted_excess"] is None
            assert r["confidence_by_regime"] is None
            assert r["stable_features"] is None
            assert r["validated_at"] is None
            assert r["deprecated_at"] is None

    def test_drift_status_starts_healthy(self) -> None:
        rows = _bulk_insert_rows()
        for r in rows:
            assert r["drift_status"] == "healthy"

    def test_rule_version_zero_for_placeholders(self) -> None:
        rows = _bulk_insert_rows()
        for r in rows:
            assert r["rule_version"] == 0


# ---------------------------------------------------------------------------
# Unit: scope discipline — upgrade does NOT create tables / indexes / enums
# ---------------------------------------------------------------------------


class TestUpgradeScope:
    def test_no_create_table_calls(self) -> None:
        """089 is scoped to ALTER + INSERT — never CREATE TABLE."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 0

    def test_no_create_index_calls(self) -> None:
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_index.call_count == 0


# ---------------------------------------------------------------------------
# Unit: downgrade
# ---------------------------------------------------------------------------


def _downgrade_events() -> list[tuple[str, str]]:
    """Replay downgrade() and capture (op_name, arg0) tuples in order."""
    mod = _load()
    events: list[tuple[str, str]] = []

    with patch.object(mod, "op") as mock_op:
        mock_op.get_bind.return_value = MagicMock()

        def _record_execute(sql) -> None:
            events.append(("execute", str(sql)))

        def _record_drop_column(table_name, column_name, *_args, **_kwargs) -> None:
            events.append(("drop_column", f"{table_name}.{column_name}"))

        mock_op.execute.side_effect = _record_execute
        mock_op.drop_column.side_effect = _record_drop_column
        mod.downgrade()
    return events


class TestDowngrade:
    def test_downgrade_deletes_placeholder_rows(self) -> None:
        events = _downgrade_events()
        delete_events = [e for e in events if e[0] == "execute" and "DELETE" in e[1]]
        assert delete_events, "downgrade did not DELETE placeholder rows"

    def test_delete_keys_off_placeholder_methodology_lock_ref(self) -> None:
        events = _downgrade_events()
        delete_payloads = [e[1] for e in events if e[0] == "execute" and "DELETE" in e[1]]
        joined = " ".join(delete_payloads)
        assert "atlas_cell_definitions" in joined
        assert "methodology_lock_ref" in joined

    def test_delete_uses_bound_param_not_string_interp(self) -> None:
        """SQL injection guard: must use :ref bind param, not f-string."""
        events = _downgrade_events()
        delete_payloads = [e[1] for e in events if e[0] == "execute" and "DELETE" in e[1]]
        joined = " ".join(delete_payloads)
        # The constant value must NOT appear inline in the SQL string —
        # it goes via bindparams.
        assert (
            "PLACEHOLDER_2026-05-24" not in joined
        ), "placeholder constant inlined into SQL; use bindparams instead"
        assert ":ref" in joined

    def test_drops_deprecated_at_for_every_v5_table(self) -> None:
        mod = _load()
        events = _downgrade_events()
        dropped = {e[1] for e in events if e[0] == "drop_column"}
        expected = {f"{t}.deprecated_at" for t in mod.V5_DEPRECATED_TABLES}
        missing = expected - dropped
        assert not missing, f"drop_column missing for: {missing}"

    def test_drop_column_count_matches_list(self) -> None:
        mod = _load()
        mock_op = _run_downgrade_with_mock()
        assert mock_op.drop_column.call_count == len(mod.V5_DEPRECATED_TABLES)

    def test_delete_runs_before_any_drop_column(self) -> None:
        """Data first, then schema — DELETE placeholder rows before
        dropping deprecated_at columns. Conceptual ordering even though
        the two operations target different tables."""
        events = _downgrade_events()
        delete_idx = next(i for i, e in enumerate(events) if e[0] == "execute" and "DELETE" in e[1])
        first_drop_col_idx = next(
            (i for i, e in enumerate(events) if e[0] == "drop_column"),
            None,
        )
        if first_drop_col_idx is not None:
            assert (
                delete_idx < first_drop_col_idx
            ), "downgrade dropped a deprecated_at column before deleting placeholders"

    def test_drop_column_uses_atlas_schema(self) -> None:
        mock_op = _run_downgrade_with_mock()
        for call in mock_op.drop_column.call_args_list:
            assert call.kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: _build_placeholder_cells() is a pure builder (no DB side effects)
# ---------------------------------------------------------------------------


class TestPlaceholderBuilder:
    def test_builder_callable(self) -> None:
        mod = _load()
        assert callable(mod._build_placeholder_cells)

    def test_builder_returns_12_rows(self) -> None:
        mod = _load()
        rows = mod._build_placeholder_cells()
        assert len(rows) == 12

    def test_builder_is_idempotent_in_shape(self) -> None:
        """Calling twice yields the same shape (uuid differs, structure same)."""
        mod = _load()
        rows_a = mod._build_placeholder_cells()
        rows_b = mod._build_placeholder_cells()
        assert len(rows_a) == len(rows_b)
        # Same combos
        combos_a = {(r["cap_tier"], r["action"], r["tenure"]) for r in rows_a}
        combos_b = {(r["cap_tier"], r["action"], r["tenure"]) for r in rows_b}
        assert combos_a == combos_b

    def test_builder_uuids_differ_per_call(self) -> None:
        """Each call gets fresh UUIDs — running upgrade twice without
        downgrade in between would naturally produce distinct cell_ids."""
        mod = _load()
        rows_a = mod._build_placeholder_cells()
        rows_b = mod._build_placeholder_cells()
        ids_a = {r["cell_id"] for r in rows_a}
        ids_b = {r["cell_id"] for r in rows_b}
        assert ids_a.isdisjoint(ids_b)


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_deprecated_at_column_present_on_v5_tables(self) -> None:
        pytest.skip(
            "verify inspector.get_columns(<v5_table>, 'atlas') contains "
            "deprecated_at with timezone-aware DateTime type"
        )

    def test_deprecated_at_is_null_by_default(self) -> None:
        pytest.skip("verify SELECT deprecated_at FROM <v5_table> returns NULL on existing rows")

    def test_placeholder_rows_present(self) -> None:
        pytest.skip(
            "verify SELECT count(*) FROM atlas.atlas_cell_definitions "
            "WHERE methodology_lock_ref = 'PLACEHOLDER_2026-05-24' = 12"
        )

    def test_partial_unique_index_holds(self) -> None:
        pytest.skip(
            "verify uq_atlas_cell_definitions_active still enforced after seed "
            "(no duplicate (cap_tier, action, tenure) where deprecated_at IS NULL)"
        )

    def test_downgrade_removes_placeholders(self) -> None:
        pytest.skip(
            "after downgrade, SELECT count(*) FROM atlas.atlas_cell_definitions "
            "WHERE methodology_lock_ref = 'PLACEHOLDER_2026-05-24' = 0"
        )

    def test_downgrade_drops_deprecated_at_columns(self) -> None:
        pytest.skip(
            "after downgrade, inspector.get_columns(<v5_table>, 'atlas') "
            "no longer contains 'deprecated_at'"
        )
