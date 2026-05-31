"""Regression tests for migration 086 — Macro overlay (Phase 9).

Tables created:
- atlas_macro_features_daily        — cross-asset macro features driving
  the allocation rule engine.
- atlas_macro_recommendation_daily  — asset-class % band emissions
  (equity / debt / gold / cash). Per /grill Q11 D10, ranges only — no
  per-instrument sizing.

Reused enum (owned by 080 — referenced with create_type=False, NOT
dropped on downgrade):
- atlas_regime_state

No NEW enums are introduced by 086.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, indexes, FKs, CHECK constraints,
UNIQUE constraints, enum reuse (not recreation), and downgrade ordering
match the v6 spec.

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

_MODULE = "migrations.versions.086_v6_macro_overlay"
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
        assert _load().revision == "086"

    def test_down_revision_085(self) -> None:
        assert _load().down_revision == "085"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() creates both tables in atlas schema
# ---------------------------------------------------------------------------


class TestUpgradeCreatesTables:
    def test_creates_macro_features_daily(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_macro_features_daily" in names

    def test_creates_macro_recommendation_daily(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert "atlas_macro_recommendation_daily" in names

    def test_only_two_tables_created(self) -> None:
        """Migration 086 is scoped to two tables — no scope creep."""
        mock_op = _run_upgrade_with_mock()
        assert mock_op.create_table.call_count == 2

    def test_macro_features_daily_in_atlas_schema(self) -> None:
        assert _table_call("atlas_macro_features_daily").kwargs.get("schema") == "atlas"

    def test_macro_recommendation_daily_in_atlas_schema(self) -> None:
        assert _table_call("atlas_macro_recommendation_daily").kwargs.get("schema") == "atlas"


# ---------------------------------------------------------------------------
# Unit: atlas_macro_features_daily columns
# ---------------------------------------------------------------------------


class TestMacroFeaturesDailyColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_macro_features_daily")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_has_id_pk(self) -> None:
        col = self._columns()["id"]
        assert col.primary_key is True

    def test_has_date_not_null(self) -> None:
        assert self._columns()["date"].nullable is False

    def test_has_regime_state_not_null(self) -> None:
        assert self._columns()["regime_state"].nullable is False

    def test_equity_vs_debt_spread_nullable_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["equity_vs_debt_spread"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)

    def test_gold_trend_nullable_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["gold_trend"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)

    def test_inr_usd_trend_nullable_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["inr_usd_trend"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)

    def test_cross_asset_dispersion_nullable_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["cross_asset_dispersion"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)

    def test_vix_level_nullable_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["vix_level"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)

    def test_g_sec_10y_yield_nullable_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["g_sec_10y_yield"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)

    def test_crude_brent_inr_nullable_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["crude_brent_inr"]
        assert col.nullable is True
        assert isinstance(col.type, sa.Numeric)

    def test_provenance_log_id_nullable(self) -> None:
        """FK target table arrives later; nullable now so we can ALTER
        ADD CONSTRAINT without rewriting NOT NULL semantics."""
        assert self._columns()["provenance_log_id"].nullable is True

    def test_computed_at_is_tz_aware(self) -> None:
        assert self._columns()["computed_at"].type.timezone is True


# ---------------------------------------------------------------------------
# Unit: atlas_macro_features_daily constraints + indexes
# ---------------------------------------------------------------------------


class TestMacroFeaturesDailyConstraints:
    def test_unique_on_date(self) -> None:
        import sqlalchemy as sa

        call = _table_call("atlas_macro_features_daily")
        uqs = [arg for arg in call.args[1:] if isinstance(arg, sa.UniqueConstraint)]
        assert len(uqs) == 1
        uq = uqs[0]
        cols = set(uq._pending_colargs)
        assert cols == {"date"}

    def test_date_desc_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_macro_features_daily_date_desc" in names


# ---------------------------------------------------------------------------
# Unit: atlas_macro_recommendation_daily columns
# ---------------------------------------------------------------------------


class TestMacroRecommendationDailyColumns:
    def _columns(self) -> dict:
        call = _table_call("atlas_macro_recommendation_daily")
        return {c.name: c for c in call.args[1:] if hasattr(c, "name")}

    def test_has_id_pk(self) -> None:
        assert self._columns()["id"].primary_key is True

    def test_has_date_not_null(self) -> None:
        assert self._columns()["date"].nullable is False

    def test_has_regime_state_not_null(self) -> None:
        assert self._columns()["regime_state"].nullable is False

    def test_equity_pct_low_not_null_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["equity_pct_low"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)

    def test_equity_pct_high_not_null_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["equity_pct_high"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)

    def test_debt_pct_low_not_null_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["debt_pct_low"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)

    def test_debt_pct_high_not_null_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["debt_pct_high"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)

    def test_gold_pct_low_not_null_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["gold_pct_low"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)

    def test_gold_pct_high_not_null_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["gold_pct_high"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)

    def test_cash_pct_low_not_null_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["cash_pct_low"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)

    def test_cash_pct_high_not_null_numeric(self) -> None:
        import sqlalchemy as sa

        col = self._columns()["cash_pct_high"]
        assert col.nullable is False
        assert isinstance(col.type, sa.Numeric)

    def test_drivers_nullable_jsonb(self) -> None:
        from sqlalchemy.dialects.postgresql import JSONB

        col = self._columns()["drivers"]
        assert col.nullable is True
        assert isinstance(col.type, JSONB)

    def test_methodology_ref_nullable(self) -> None:
        assert self._columns()["methodology_ref"].nullable is True

    def test_macro_features_id_nullable(self) -> None:
        assert self._columns()["macro_features_id"].nullable is True

    def test_computed_at_is_tz_aware(self) -> None:
        assert self._columns()["computed_at"].type.timezone is True


# ---------------------------------------------------------------------------
# Unit: atlas_macro_recommendation_daily FK + indexes
# ---------------------------------------------------------------------------


class TestMacroRecommendationDailyForeignKeysAndIndexes:
    def _fks(self) -> list:
        call = _table_call("atlas_macro_recommendation_daily")
        fks: list = []
        for c in call.args[1:]:
            if not hasattr(c, "foreign_keys"):
                continue
            for fk in c.foreign_keys:
                fks.append((c.name, fk))
        return fks

    def test_macro_features_id_fk_set_null(self) -> None:
        feature_fks = [fk for col, fk in self._fks() if col == "macro_features_id"]
        assert len(feature_fks) == 1
        fk = feature_fks[0]
        assert "atlas_macro_features_daily" in fk.target_fullname
        assert "id" in fk.target_fullname
        assert fk.ondelete == "SET NULL"

    def test_date_desc_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_macro_recommendation_daily_date_desc" in names

    def test_regime_state_index(self) -> None:
        mock_op = _run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_index.call_args_list}
        assert "ix_atlas_macro_recommendation_daily_regime_state" in names

    def test_unique_on_date(self) -> None:
        import sqlalchemy as sa

        call = _table_call("atlas_macro_recommendation_daily")
        uqs = [arg for arg in call.args[1:] if isinstance(arg, sa.UniqueConstraint)]
        assert len(uqs) == 1
        uq = uqs[0]
        cols = set(uq._pending_colargs)
        assert cols == {"date"}


# ---------------------------------------------------------------------------
# Unit: CHECK constraints — low <= high per asset class
# ---------------------------------------------------------------------------


def _check_constraints(table_name: str) -> dict:
    import sqlalchemy as sa

    call = _table_call(table_name)
    return {c.name: c for c in call.args[1:] if isinstance(c, sa.CheckConstraint)}


class TestMacroRecommendationDailyLowVsHighChecks:
    """Four CHECK constraints — low ≤ high for each asset class."""

    def test_equity_low_le_high(self) -> None:
        cks = _check_constraints("atlas_macro_recommendation_daily")
        assert "ck_atlas_macro_reco_equity_low_le_high" in cks
        ck = cks["ck_atlas_macro_reco_equity_low_le_high"]
        assert "equity_pct_low" in str(ck.sqltext)
        assert "equity_pct_high" in str(ck.sqltext)
        assert "<=" in str(ck.sqltext)

    def test_debt_low_le_high(self) -> None:
        cks = _check_constraints("atlas_macro_recommendation_daily")
        assert "ck_atlas_macro_reco_debt_low_le_high" in cks
        ck = cks["ck_atlas_macro_reco_debt_low_le_high"]
        assert "debt_pct_low" in str(ck.sqltext)
        assert "debt_pct_high" in str(ck.sqltext)
        assert "<=" in str(ck.sqltext)

    def test_gold_low_le_high(self) -> None:
        cks = _check_constraints("atlas_macro_recommendation_daily")
        assert "ck_atlas_macro_reco_gold_low_le_high" in cks
        ck = cks["ck_atlas_macro_reco_gold_low_le_high"]
        assert "gold_pct_low" in str(ck.sqltext)
        assert "gold_pct_high" in str(ck.sqltext)
        assert "<=" in str(ck.sqltext)

    def test_cash_low_le_high(self) -> None:
        cks = _check_constraints("atlas_macro_recommendation_daily")
        assert "ck_atlas_macro_reco_cash_low_le_high" in cks
        ck = cks["ck_atlas_macro_reco_cash_low_le_high"]
        assert "cash_pct_low" in str(ck.sqltext)
        assert "cash_pct_high" in str(ck.sqltext)
        assert "<=" in str(ck.sqltext)


# ---------------------------------------------------------------------------
# Unit: CHECK constraints — [0, 100] range per low/high column
# ---------------------------------------------------------------------------


class TestMacroRecommendationDailyRangeChecks:
    """Eight CHECK constraints — each low / high in [0, 100]."""

    @pytest.mark.parametrize(
        "name,col",
        [
            ("ck_atlas_macro_reco_equity_low_range", "equity_pct_low"),
            ("ck_atlas_macro_reco_equity_high_range", "equity_pct_high"),
            ("ck_atlas_macro_reco_debt_low_range", "debt_pct_low"),
            ("ck_atlas_macro_reco_debt_high_range", "debt_pct_high"),
            ("ck_atlas_macro_reco_gold_low_range", "gold_pct_low"),
            ("ck_atlas_macro_reco_gold_high_range", "gold_pct_high"),
            ("ck_atlas_macro_reco_cash_low_range", "cash_pct_low"),
            ("ck_atlas_macro_reco_cash_high_range", "cash_pct_high"),
        ],
    )
    def test_range_constraint(self, name: str, col: str) -> None:
        cks = _check_constraints("atlas_macro_recommendation_daily")
        assert name in cks, f"missing CHECK constraint {name}"
        ck = cks[name]
        sqltext = str(ck.sqltext)
        assert col in sqltext
        assert "0" in sqltext
        assert "100" in sqltext

    def test_all_twelve_check_constraints_present(self) -> None:
        """4 low-vs-high + 8 range = 12 total CHECKs on the recommendation
        table.
        """
        cks = _check_constraints("atlas_macro_recommendation_daily")
        assert len(cks) == 12, f"expected 12 CHECK constraints, got {len(cks)}: {list(cks)}"


# ---------------------------------------------------------------------------
# Unit: enum reuse — atlas_regime_state must NOT be recreated
# ---------------------------------------------------------------------------


class TestEnumReuse:
    """The atlas_regime_state enum is owned by 080. 086 must reference it
    with create_type=False and never call .create() on it. 086 introduces
    no NEW enums.
    """

    def test_does_not_create_any_enum(self) -> None:
        """086 owns no new enums — nothing should be created via ENUM.create()."""
        mod = _load()
        created_names: list[str] = []

        original_enum_cls = importlib.import_module("sqlalchemy.dialects.postgresql").ENUM

        class _SpyEnum(original_enum_cls):  # type: ignore[misc, valid-type]
            def create(  # type: ignore[override]
                self,
                bind,  # pyright: ignore[reportUnusedParameter]
                checkfirst: bool = False,  # pyright: ignore[reportUnusedParameter]
            ) -> None:
                # Only record .create() calls where the enum is being
                # built — i.e. the constructor passed values. Reused-enum
                # stubs use create_type=False and have no values list.
                if getattr(self, "enums", None):
                    created_names.append(self.name)

        with (
            patch.object(mod, "op") as mock_op,
            patch("sqlalchemy.dialects.postgresql.ENUM", _SpyEnum),
        ):
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()

        assert created_names == [], (
            f"086 must not create any enums (introduces none); created: {created_names}"
        )

    def test_does_not_recreate_regime_state(self) -> None:
        """atlas_regime_state is owned by 080."""
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

        assert "atlas_regime_state" not in created_names


# ---------------------------------------------------------------------------
# Unit: downgrade
# ---------------------------------------------------------------------------


class TestDowngrade:
    def test_drops_both_tables(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {
            "atlas_macro_features_daily",
            "atlas_macro_recommendation_daily",
        }

    def test_drops_recommendation_before_features(self) -> None:
        """FK from recommendation → features means recommendation must
        be dropped first."""
        mock_op = _run_downgrade_with_mock()
        order = [c.args[0] for c in mock_op.drop_table.call_args_list]
        assert order.index("atlas_macro_recommendation_daily") < order.index(
            "atlas_macro_features_daily"
        )

    def test_drops_all_named_indexes(self) -> None:
        mock_op = _run_downgrade_with_mock()
        dropped = {c.args[0] for c in mock_op.drop_index.call_args_list}
        expected = {
            "ix_atlas_macro_features_daily_date_desc",
            "ix_atlas_macro_recommendation_daily_date_desc",
            "ix_atlas_macro_recommendation_daily_regime_state",
        }
        missing = expected - dropped
        assert not missing, f"missing index drops on downgrade: {missing}"

    def test_does_not_drop_regime_state_enum(self) -> None:
        """atlas_regime_state is owned by 080 — downgrade of 086 must
        leave it intact.
        """
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

        assert "atlas_regime_state" not in dropped_names, (
            "downgrade of 086 must not drop atlas_regime_state (owned by 080)"
        )

    def test_drops_no_enums_at_all(self) -> None:
        """086 owns no enums — downgrade must not drop any."""
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
            f"086 owns no enums; downgrade must not drop any: {dropped_names}"
        )


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only."""

    def test_migration_applies(self) -> None:
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_macro_features_daily_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_macro_recommendation_daily_table_exists(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_check_low_le_high_enforced(self) -> None:
        pytest.skip(
            "verify INSERT with equity_pct_low > equity_pct_high raises "
            "check_violation; same for debt/gold/cash"
        )

    def test_check_range_zero_to_hundred_enforced(self) -> None:
        pytest.skip(
            "verify INSERT with equity_pct_low = -1 or 101 raises "
            "check_violation; same for all 8 columns"
        )

    def test_fk_set_null_on_features_delete(self) -> None:
        pytest.skip(
            "verify DELETE on atlas_macro_features_daily row sets "
            "macro_features_id NULL on dependent recommendation rows"
        )
