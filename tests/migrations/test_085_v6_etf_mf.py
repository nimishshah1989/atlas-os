"""Regression tests for migration 085 — ETF + MF tables (Phase 8).

Tables + objects created:
- atlas_etf_signal_calls       — ETF cell-matrix analog to
  atlas_signal_calls (trigger-only cadence, 3-state action vocab).
- atlas_mf_recommendation_daily — per-fund daily quartile + consistency
  per CEO plan §09 MF locked methodology.
- atlas_mf_switch_rules         — SWITCH selection configuration per
  /grill Q11 D5 (same-category only).

NEW enums (owned by 085):
- atlas_etf_sub_category (broad_market, sectoral)
- atlas_mf_quartile (Q1, Q2, Q3, Q4)
- atlas_mf_recommendation (BUY, HOLD, SWITCH, AVOID)

Reused enums (owned by 080 — referenced with create_type=False, NOT
dropped on downgrade):
- atlas_cap_tier, atlas_tenure, atlas_cell_action, atlas_regime_state,
  atlas_exit_reason

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, indexes, FKs, partial indexes,
enum creation/reuse, and downgrade ordering match the v6 spec.

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the migration applies cleanly on a real Postgres. Skipped by
default; run on EC2 / staging.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest

_MODULE = "migrations.versions.085_v6_etf_mf"
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


def _executed_sql_upgrade() -> list[str]:
    """Return all SQL strings passed to op.execute() during upgrade."""
    mock_op = _run_upgrade_with_mock()
    return [
        c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
        for c in mock_op.execute.call_args_list
    ]


def _executed_sql_downgrade() -> list[str]:
    mock_op = _run_downgrade_with_mock()
    return [
        c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
        for c in mock_op.execute.call_args_list
    ]


# ---------------------------------------------------------------------------
# Unit: metadata
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    def test_revision(self) -> None:
        assert _load().revision == "085"

    def test_down_revision_084(self) -> None:
        assert _load().down_revision == "084"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() creates all three tables
# ---------------------------------------------------------------------------


class TestUpgradeCreatesTables:
    def test_creates_etf_signal_calls(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_etf_signal_calls" in names

    def test_creates_mf_recommendation_daily(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_mf_recommendation_daily" in names

    def test_creates_mf_switch_rules(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_mf_switch_rules" in names

    def test_only_three_tables_created(self) -> None:
        """Migration 085 is scoped to three tables — no scope creep."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 3

    def test_etf_signal_calls_in_atlas_schema(self) -> None:
        assert _table_call("atlas_etf_signal_calls").kwargs.get("schema") == "atlas"

    def test_mf_recommendation_daily_in_atlas_schema(self) -> None:
        assert _table_call("atlas_mf_recommendation_daily").kwargs.get("schema") == "atlas"

    def test_mf_switch_rules_in_atlas_schema(self) -> None:
        assert _table_call("atlas_mf_switch_rules").kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: atlas_etf_signal_calls columns
# ---------------------------------------------------------------------------


class TestEtfSignalCallsColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_etf_signal_calls")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_has_etf_signal_call_id_pk(self) -> None:
        col = self._columns()["etf_signal_call_id"]
        assert col.primary_key is True

    def test_has_etf_instrument_id(self) -> None:
        assert self._columns()["etf_instrument_id"].nullable is False

    def test_has_etf_sub_category(self) -> None:
        assert self._columns()["etf_sub_category"].nullable is False

    def test_has_date_not_null(self) -> None:
        assert self._columns()["date"].nullable is False

    def test_has_cell_id_not_null(self) -> None:
        assert self._columns()["cell_id"].nullable is False

    def test_has_cap_tier_at_trigger(self) -> None:
        assert self._columns()["cap_tier_at_trigger"].nullable is False

    def test_has_tenure(self) -> None:
        assert self._columns()["tenure"].nullable is False

    def test_has_action(self) -> None:
        assert self._columns()["action"].nullable is False

    def test_confidence_unconditional_not_null(self) -> None:
        assert self._columns()["confidence_unconditional"].nullable is False

    def test_confidence_regime_conditional_nullable(self) -> None:
        assert self._columns()["confidence_regime_conditional"].nullable is True

    def test_has_regime_state_at_call(self) -> None:
        assert self._columns()["regime_state_at_call"].nullable is False

    def test_cell_active_in_regime_default_true(self) -> None:
        col = self._columns()["cell_active_in_regime"]
        assert col.nullable is False
        assert "TRUE" in str(col.server_default.arg).upper()

    def test_predicted_excess_nullable(self) -> None:
        assert self._columns()["predicted_excess"].nullable is True

    def test_exit_date_nullable(self) -> None:
        assert self._columns()["exit_date"].nullable is True

    def test_exit_price_nullable(self) -> None:
        assert self._columns()["exit_price"].nullable is True

    def test_exit_reason_nullable(self) -> None:
        assert self._columns()["exit_reason"].nullable is True

    def test_computed_at_is_tz_aware(self) -> None:
        assert self._columns()["computed_at"].type.timezone is True

    def test_exit_price_is_numeric_not_float(self) -> None:
        """Financial domain rule: Numeric not Float for money."""
        import sqlalchemy as sa

        assert isinstance(self._columns()["exit_price"].type, sa.Numeric)

    def test_confidence_unconditional_is_numeric(self) -> None:
        import sqlalchemy as sa

        assert isinstance(self._columns()["confidence_unconditional"].type, sa.Numeric)


# ---------------------------------------------------------------------------
# Unit: atlas_etf_signal_calls FKs + indexes
# ---------------------------------------------------------------------------


class TestEtfSignalCallsForeignKeysAndIndexes:
    def _fks(self) -> list:
        call = _table_call("atlas_etf_signal_calls")
        fks: list = []
        for c in call.args[1:]:
            if not hasattr(c, "foreign_keys"):
                continue
            for fk in c.foreign_keys:
                fks.append((c.name, fk))
        return fks

    def test_cell_id_fk_with_restrict(self) -> None:
        cell_fks = [fk for col, fk in self._fks() if col == "cell_id"]
        assert len(cell_fks) == 1
        fk = cell_fks[0]
        assert "atlas_cell_definitions" in fk.target_fullname
        assert "cell_id" in fk.target_fullname
        assert fk.ondelete == "RESTRICT"

    def test_no_fk_on_etf_instrument_id(self) -> None:
        """etf_instrument_id is resolved at the application layer
        against the ETF instrument-master (same convention as
        instrument_id in 080 / 084).
        """
        fks = [fk for col, fk in self._fks() if col == "etf_instrument_id"]
        assert len(fks) == 0

    def test_composite_index_date_action_tier(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_etf_signal_calls_date_action_tier" in names

    def test_composite_index_columns(self) -> None:
        mock_op = _run_upgrade_with_mock()
        for call in mock_op.create_index.call_args_list:
            if call.args[0] == "ix_atlas_etf_signal_calls_date_action_tier":
                assert list(call.args[2]) == ["date", "action", "cap_tier_at_trigger"]
                return
        pytest.fail("composite index not found")

    def test_iid_date_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_etf_signal_calls_iid_date" in names

    def test_cell_date_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_etf_signal_calls_cell_date" in names

    def test_open_positions_partial_index_via_raw_sql(self) -> None:
        """Partial index `WHERE exit_date IS NULL` for open ETF calls."""
        sql_list = _executed_sql_upgrade()
        partial = next(
            (
                sql
                for sql in sql_list
                if "ix_atlas_etf_signal_calls_open" in sql
                and "WHERE exit_date IS NULL" in sql
                and "CREATE INDEX" in sql.upper()
            ),
            None,
        )
        assert partial is not None, "partial open-positions index missing"
        assert "atlas.atlas_etf_signal_calls" in partial
        assert "etf_instrument_id" in partial
        assert "cell_id" in partial
        assert "tenure" in partial


# ---------------------------------------------------------------------------
# Unit: atlas_mf_recommendation_daily columns + types
# ---------------------------------------------------------------------------


class TestMfRecommendationDailyColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_mf_recommendation_daily")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_has_id_pk(self) -> None:
        assert self._columns()["id"].primary_key is True

    def test_has_date_not_null(self) -> None:
        assert self._columns()["date"].nullable is False

    def test_has_mf_instrument_id(self) -> None:
        assert self._columns()["mf_instrument_id"].nullable is False

    def test_has_category(self) -> None:
        assert self._columns()["category"].nullable is False

    def test_has_peer_quartile(self) -> None:
        assert self._columns()["peer_quartile"].nullable is False

    def test_consistency_months_not_null_default_zero(self) -> None:
        col = self._columns()["consistency_months"]
        assert col.nullable is False
        assert "0" in str(col.server_default.arg)

    def test_nav_is_numeric_not_float(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["nav"]
        assert isinstance(col.type, sa.Numeric)
        assert col.nullable is False

    def test_expense_ratio_is_numeric(self) -> None:
        """Tie-break for SWITCH — nullable because feed may lag."""
        import sqlalchemy as sa

        col = self._columns()["expense_ratio"]
        assert isinstance(col.type, sa.Numeric)
        assert col.nullable is True

    def test_has_recommendation(self) -> None:
        assert self._columns()["recommendation"].nullable is False

    def test_switch_target_iid_nullable(self) -> None:
        """Only populated when recommendation='SWITCH'."""
        assert self._columns()["switch_target_iid"].nullable is True

    def test_data_as_of_not_null(self) -> None:
        """NAV date can lag the run date; explicit column."""
        assert self._columns()["data_as_of"].nullable is False

    def test_computed_at_is_tz_aware(self) -> None:
        assert self._columns()["computed_at"].type.timezone is True


# ---------------------------------------------------------------------------
# Unit: atlas_mf_recommendation_daily constraints + indexes
# ---------------------------------------------------------------------------


class TestMfRecommendationDailyConstraints:
    def test_unique_on_date_mf_instrument_id(self) -> None:
        import sqlalchemy as sa

        call = _table_call("atlas_mf_recommendation_daily")
        uqs = [arg for arg in call.args[1:] if isinstance(arg, sa.UniqueConstraint)]
        assert len(uqs) == 1
        uq = uqs[0]
        cols = set(uq._pending_colargs)
        assert cols == {"date", "mf_instrument_id"}

    def test_date_reco_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_mf_recommendation_daily_date_reco" in names

    def test_date_reco_index_columns(self) -> None:
        mock_op = _run_upgrade_with_mock()
        for call in mock_op.create_index.call_args_list:
            if call.args[0] == "ix_atlas_mf_recommendation_daily_date_reco":
                assert list(call.args[2]) == ["date", "recommendation"]
                return
        pytest.fail("date_reco index not found")

    def test_iid_date_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_mf_recommendation_daily_iid_date" in names

    def test_category_date_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_mf_recommendation_daily_category_date" in names


# ---------------------------------------------------------------------------
# Unit: atlas_mf_switch_rules columns + partial unique
# ---------------------------------------------------------------------------


class TestMfSwitchRulesColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_mf_switch_rules")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_has_id_pk(self) -> None:
        assert self._columns()["id"].primary_key is True

    def test_has_category(self) -> None:
        assert self._columns()["category"].nullable is False

    def test_has_current_quartile_floor(self) -> None:
        assert self._columns()["current_quartile_floor"].nullable is False

    def test_has_target_quartile_ceiling(self) -> None:
        assert self._columns()["target_quartile_ceiling"].nullable is False

    def test_min_target_consistency_months_default_6(self) -> None:
        """Per /grill Q11 D5: target must have ≥ 6 months consistency."""
        col = self._columns()["min_target_consistency_months"]
        assert col.nullable is False
        assert "6" in str(col.server_default.arg)

    def test_tie_break_default_lowest_expense_ratio(self) -> None:
        col = self._columns()["tie_break"]
        assert col.nullable is False
        assert "lowest_expense_ratio" in str(col.server_default.arg)

    def test_active_default_true(self) -> None:
        col = self._columns()["active"]
        assert col.nullable is False
        assert "TRUE" in str(col.server_default.arg).upper()

    def test_created_at_is_tz_aware(self) -> None:
        assert self._columns()["created_at"].type.timezone is True

    def test_partial_unique_on_category_active(self) -> None:
        """At most ONE active rule per category — partial unique
        constraint `WHERE active = TRUE` per /grill Q11 D5.
        """
        sql_list = _executed_sql_upgrade()
        partial = next(
            (
                sql
                for sql in sql_list
                if "uq_atlas_mf_switch_rules_category_active" in sql
                and "WHERE active = TRUE" in sql
                and "CREATE UNIQUE INDEX" in sql.upper()
            ),
            None,
        )
        assert partial is not None, "partial unique on (category) WHERE active = TRUE missing"
        assert "atlas.atlas_mf_switch_rules" in partial


# ---------------------------------------------------------------------------
# Unit: NEW enums created; existing enums NOT recreated
# ---------------------------------------------------------------------------


class TestEnumCreation:
    """The NEW enums (atlas_etf_sub_category, atlas_mf_quartile,
    atlas_mf_recommendation) are created via ENUM(...).create(bind) at
    the top of upgrade(). The reused enums from migration 080 are NOT.

    The cleanest way to assert this in a mocked environment is to patch
    postgresql.ENUM and inspect what .create() was called on.
    """

    def test_creates_three_new_enums(self) -> None:
        mod = _load()
        created_names: list[str] = []

        original_enum_cls = importlib.import_module("sqlalchemy.dialects.postgresql").ENUM

        class _SpyEnum(original_enum_cls):  # type: ignore[misc, valid-type]
            def create(self, bind, checkfirst: bool = False) -> None:  # type: ignore[override]
                # Only record .create() calls where the enum is being
                # built — i.e. the constructor passed values (the
                # reused-enum stubs use create_type=False, never call
                # .create()).
                if getattr(self, "enums", None):
                    created_names.append(self.name)

        with (
            patch.object(mod, "op") as mock_op,
            patch("sqlalchemy.dialects.postgresql.ENUM", _SpyEnum),
        ):
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()

        assert "atlas_etf_sub_category" in created_names
        assert "atlas_mf_quartile" in created_names
        assert "atlas_mf_recommendation" in created_names

    def test_does_not_recreate_existing_enums(self) -> None:
        """Reused enums from 080 must NOT be passed to .create()."""
        mod = _load()
        created_names: list[str] = []

        original_enum_cls = importlib.import_module("sqlalchemy.dialects.postgresql").ENUM

        class _SpyEnum(original_enum_cls):  # type: ignore[misc, valid-type]
            def create(self, bind, checkfirst: bool = False) -> None:  # type: ignore[override]
                if getattr(self, "enums", None):
                    created_names.append(self.name)

        with (
            patch.object(mod, "op") as mock_op,
            patch("sqlalchemy.dialects.postgresql.ENUM", _SpyEnum),
        ):
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()

        forbidden = {
            "atlas_cap_tier",
            "atlas_tenure",
            "atlas_cell_action",
            "atlas_regime_state",
            "atlas_exit_reason",
        }
        leaked = forbidden & set(created_names)
        assert not leaked, f"reused enums must not be recreated: {leaked}"


# ---------------------------------------------------------------------------
# Unit: downgrade
# ---------------------------------------------------------------------------


class TestDowngrade:
    def test_drops_all_three_tables(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {
            "atlas_etf_signal_calls",
            "atlas_mf_recommendation_daily",
            "atlas_mf_switch_rules",
        }

    def test_drops_all_named_indexes(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_index.call_args_list}
        expected = {
            "ix_atlas_etf_signal_calls_date_action_tier",
            "ix_atlas_etf_signal_calls_iid_date",
            "ix_atlas_etf_signal_calls_cell_date",
            "ix_atlas_mf_recommendation_daily_date_reco",
            "ix_atlas_mf_recommendation_daily_iid_date",
            "ix_atlas_mf_recommendation_daily_category_date",
        }
        missing = expected - dropped
        assert not missing, f"missing index drops on downgrade: {missing}"

    def test_drops_partial_open_index_via_raw_sql(self) -> None:
        sql_list = _executed_sql_downgrade()
        drop = next(
            (
                sql
                for sql in sql_list
                if "DROP INDEX" in sql.upper() and "ix_atlas_etf_signal_calls_open" in sql
            ),
            None,
        )
        assert drop is not None, "partial open-positions index not dropped via raw SQL"

    def test_drops_partial_unique_via_raw_sql(self) -> None:
        sql_list = _executed_sql_downgrade()
        drop = next(
            (
                sql
                for sql in sql_list
                if "DROP INDEX" in sql.upper() and "uq_atlas_mf_switch_rules_category_active" in sql
            ),
            None,
        )
        assert drop is not None, "partial unique index not dropped via raw SQL"

    def test_drops_only_new_enums(self) -> None:
        """Downgrade must drop the 3 NEW enums (atlas_etf_sub_category,
        atlas_mf_quartile, atlas_mf_recommendation) and leave the 080-
        owned enums alone.
        """
        mod = _load()
        dropped_names: list[str] = []

        original_enum_cls = importlib.import_module("sqlalchemy.dialects.postgresql").ENUM

        class _SpyEnum(original_enum_cls):  # type: ignore[misc, valid-type]
            def drop(self, bind, checkfirst: bool = False) -> None:  # type: ignore[override]
                dropped_names.append(self.name)

        with (
            patch.object(mod, "op") as mock_op,
            patch("sqlalchemy.dialects.postgresql.ENUM", _SpyEnum),
        ):
            mock_op.get_bind.return_value = MagicMock()
            mod.downgrade()

        # NEW enums must be dropped.
        assert "atlas_etf_sub_category" in dropped_names
        assert "atlas_mf_quartile" in dropped_names
        assert "atlas_mf_recommendation" in dropped_names

        # Reused enums from 080 must NOT be dropped.
        forbidden = {
            "atlas_cap_tier",
            "atlas_tenure",
            "atlas_cell_action",
            "atlas_regime_state",
            "atlas_exit_reason",
        }
        leaked = forbidden & set(dropped_names)
        assert not leaked, f"downgrade must not drop 080-owned enums: {leaked}"


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_etf_signal_calls_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_mf_recommendation_daily_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_mf_switch_rules_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_partial_unique_on_switch_rules_enforces_single_active(self) -> None:
        pytest.skip(
            "verify INSERT-ing two active=TRUE rows for same category raises "
            "unique violation; INSERT-ing one active=TRUE + one active=FALSE works"
        )
