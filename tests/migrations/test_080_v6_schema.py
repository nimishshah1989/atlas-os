"""Regression tests for migration 080 — v6 foundation schema.

Tables created:
- atlas_regime_daily
- atlas_scorecard_daily
- atlas_cell_definitions
- atlas_signal_calls

Plus 7 canonical v6 enums.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, enums, indexes, and constraints
match the v6 spec in CONTEXT.md + eng review §1.3.

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

_MODULE = "migrations.versions.080_v6_scorecard_signals_cells_regime"
_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="live-DB tests — set ATLAS_INTEGRATION_TESTS=1 to run (EC2 only)",
)


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


# ---------------------------------------------------------------------------
# Unit: metadata
# ---------------------------------------------------------------------------


class TestMigrationMetadata:
    def test_revision(self) -> None:
        assert _load().revision == "080"

    def test_down_revision_continues_079_chain(self) -> None:
        """Path A per /grill Q10 — continue the 079 chain, not a new head."""
        assert _load().down_revision == "079"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: enum vocabularies match CONTEXT.md
# ---------------------------------------------------------------------------


class TestEnumVocabularies:
    def test_cap_tier_three_values(self) -> None:
        assert _load().CAP_TIER == ("Small", "Mid", "Large")

    def test_family_state_rag(self) -> None:
        assert _load().FAMILY_STATE == ("R", "A", "G")

    def test_cell_action_is_three_states_not_six(self) -> None:
        """Post-adversarial R1: action vocab collapsed from 6 to 3.

        ACCUMULATE / HOLD / WATCH / SELL are display labels rendered by
        the API based on user ownership — NOT validated cell states.
        """
        assert _load().CELL_ACTION == ("POSITIVE", "NEUTRAL", "NEGATIVE")
        # Sanity: old vocab is NOT present
        assert "BUY" not in _load().CELL_ACTION
        assert "ACCUMULATE" not in _load().CELL_ACTION
        assert "AVOID" not in _load().CELL_ACTION

    def test_tenure_four_horizons(self) -> None:
        assert _load().TENURE == ("1m", "3m", "6m", "12m")

    def test_regime_state_four_states(self) -> None:
        assert _load().REGIME_STATE == (
            "Risk-On",
            "Elevated",
            "Below-Trend",
            "Risk-Off",
        )

    def test_drift_status_advisory_mode(self) -> None:
        """Post-adversarial F3/R3: drift detector is advisory in v6."""
        assert _load().DRIFT_STATUS == ("healthy", "drift_warn", "deprecated")

    def test_exit_reason_uses_negative_collapse(self) -> None:
        """Post-adversarial R1: cell_flip_to_negative (single trigger),
        NOT cell_flip_to_trim / cell_flip_to_avoid / cell_flip_to_watch.

        Per CONTEXT.md exit semantics: position exits only when underlying
        cell state flips to NEGATIVE.
        """
        assert "cell_flip_to_negative" in _load().EXIT_REASON
        assert "tenure_expiry" in _load().EXIT_REASON
        assert "user_close" in _load().EXIT_REASON
        assert "delisting" in _load().EXIT_REASON
        assert "cell_deprecated" in _load().EXIT_REASON
        # Old vocab should NOT be here
        assert "cell_flip_to_trim" not in _load().EXIT_REASON
        assert "cell_flip_to_avoid" not in _load().EXIT_REASON
        assert "cell_flip_to_watch" not in _load().EXIT_REASON


# ---------------------------------------------------------------------------
# Unit: upgrade() emits expected create_table calls
# ---------------------------------------------------------------------------


class TestUpgradeEmitsTables:
    def _run_upgrade_with_mock(self) -> MagicMock:
        """Run upgrade() with op mocked; return the mock for assertions."""
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            # Make get_bind return a magic mock — enums call .create() on it
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()
        return mock_op

    def test_creates_four_tables(self) -> None:
        mock_op = self._run_upgrade_with_mock()
        calls = [c for c in mock_op.create_table.call_args_list]
        table_names = {c.args[0] for c in calls}
        assert table_names == {
            "atlas_regime_daily",
            "atlas_scorecard_daily",
            "atlas_cell_definitions",
            "atlas_signal_calls",
        }

    def test_all_tables_use_atlas_schema(self) -> None:
        mock_op = self._run_upgrade_with_mock()
        for call in mock_op.create_table.call_args_list:
            assert call.kwargs.get("schema") == "atlas", f"Table {call.args[0]} not in atlas schema"


# ---------------------------------------------------------------------------
# Unit: scorecard_daily structural properties
# ---------------------------------------------------------------------------


class TestScorecardDailySchema:
    def _scorecard_columns(self) -> list:
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()
        for call in mock_op.create_table.call_args_list:
            if call.args[0] == "atlas_scorecard_daily":
                return list(call.args[1:])
        raise AssertionError("atlas_scorecard_daily not created")

    def test_five_family_columns(self) -> None:
        col_names = [c.name for c in self._scorecard_columns() if hasattr(c, "name")]
        for fam in (
            "family_trend",
            "family_volatility",
            "family_volume",
            "family_path",
            "family_sector",
        ):
            assert fam in col_names, f"missing scorecard family column: {fam}"

    def test_methodology_locked_features_first_class(self) -> None:
        """Locked features per methodology lock §3 are first-class columns
        for direct queryability. Extended features go in features JSONB.
        """
        col_names = [c.name for c in self._scorecard_columns() if hasattr(c, "name")]
        for feat in (
            "rs_residual_6m",
            "log_med_tv_60d",
            "realized_vol_60d",
            "formation_max_dd",
            "listing_age_days",
            "log_price",
        ):
            assert feat in col_names, f"missing locked feature column: {feat}"

    def test_features_jsonb_for_extensions(self) -> None:
        """Per CONTEXT.md 24-framework discovery + continuous improvement:
        feature library can expand. JSONB column supports dynamic features.
        """
        col_names = [c.name for c in self._scorecard_columns() if hasattr(c, "name")]
        assert "features" in col_names

    def test_data_completeness_column_for_partial_days(self) -> None:
        col_names = [c.name for c in self._scorecard_columns() if hasattr(c, "name")]
        assert "data_completeness" in col_names


# ---------------------------------------------------------------------------
# Unit: signal_calls structural properties
# ---------------------------------------------------------------------------


class TestSignalCallsSchema:
    def _signal_call_kwargs(self) -> dict:
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()
        for call in mock_op.create_table.call_args_list:
            if call.args[0] == "atlas_signal_calls":
                return {"args": list(call.args[1:]), "kwargs": call.kwargs}
        raise AssertionError("atlas_signal_calls not created")

    def test_has_cap_tier_denormalized(self) -> None:
        """Per eng review §4 Finding 4.A: cap_tier_at_trigger denormalized
        onto signal_calls so the (date, action, cap_tier) composite index
        works without join.
        """
        cols = [c.name for c in self._signal_call_kwargs()["args"] if hasattr(c, "name")]
        assert "cap_tier_at_trigger" in cols

    def test_has_exit_tracking_columns(self) -> None:
        """Per CONTEXT.md signal_call_id: trigger-only; row stays open until
        exit_date set.
        """
        cols = [c.name for c in self._signal_call_kwargs()["args"] if hasattr(c, "name")]
        for col in ("exit_date", "exit_price", "exit_reason"):
            assert col in cols, f"missing exit-tracking column: {col}"

    def test_has_scorecard_id_fk(self) -> None:
        """signal_call links back to its scorecard via FK."""
        cols = [c.name for c in self._signal_call_kwargs()["args"] if hasattr(c, "name")]
        assert "scorecard_id" in cols

    def test_has_cell_id_fk(self) -> None:
        cols = [c.name for c in self._signal_call_kwargs()["args"] if hasattr(c, "name")]
        assert "cell_id" in cols


# ---------------------------------------------------------------------------
# Unit: cell_definitions partial-unique constraint
# ---------------------------------------------------------------------------


class TestCellDefinitionsPartialUnique:
    def test_upgrade_creates_partial_unique_index(self) -> None:
        """Per eng review §1.3: UNIQUE (cap_tier, action, tenure,
        deprecated_at IS NULL) — multiple deprecated cells with same
        key permitted, only one active.
        """
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()
        executed_sql = [
            c.args[0] if isinstance(c.args[0], str) else str(c.args[0])
            for c in mock_op.execute.call_args_list
        ]
        # Look for the partial unique index DDL
        found = any(
            "uq_atlas_cell_definitions_active" in sql and "WHERE deprecated_at IS NULL" in sql
            for sql in executed_sql
        )
        assert found, "partial unique index uq_atlas_cell_definitions_active not created"


# ---------------------------------------------------------------------------
# Unit: downgrade() reverses upgrade()
# ---------------------------------------------------------------------------


class TestDowngrade:
    def test_drops_four_tables(self) -> None:
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.downgrade()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {
            "atlas_signal_calls",
            "atlas_cell_definitions",
            "atlas_scorecard_daily",
            "atlas_regime_daily",
        }

    def test_drops_in_fk_dependency_order(self) -> None:
        """signal_calls must drop BEFORE scorecard_daily (FK) and
        cell_definitions (FK)."""
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.downgrade()
        ordered_drops = [c.args[0] for c in mock_op.drop_table.call_args_list]
        sc_idx = ordered_drops.index("atlas_signal_calls")
        sd_idx = ordered_drops.index("atlas_scorecard_daily")
        cd_idx = ordered_drops.index("atlas_cell_definitions")
        assert sc_idx < sd_idx, "signal_calls must drop before scorecard_daily"
        assert sc_idx < cd_idx, "signal_calls must drop before cell_definitions"


# ---------------------------------------------------------------------------
# Integration (requires ATLAS_INTEGRATION_TESTS=1 + live DB)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
class TestLiveDB:
    """Live-DB regression. Run on staging / EC2 only.

    Verifies the migration applies cleanly + the schema matches the spec.
    """

    def test_migration_applies(self) -> None:
        # alembic upgrade head should land at 080 without error
        # (driven by ATLAS_DB_URL pointing at a clean test schema)
        pytest.skip("wire alembic.command.upgrade() invocation when staging DB available")

    def test_schema_has_all_four_tables(self) -> None:
        pytest.skip("wire inspector.get_table_names('atlas') check")

    def test_unique_constraints(self) -> None:
        pytest.skip("verify (date, instrument_id) on scorecard, partial unique on cells")
