"""Regression tests for migration 092 — atlas_cell_rule_candidates +
atlas_conviction_daily.

These tests run a mock-driven upgrade and assert the expected tables,
columns, indexes, and constraints exist. No live DB required.
"""

from __future__ import annotations

import importlib
import types
from unittest.mock import MagicMock, patch

_MODULE = "migrations.versions.092_atlas_conviction_daily_and_candidates"


def _load() -> types.ModuleType:
    return importlib.import_module(_MODULE)


class TestMigrationMetadata:
    def test_revision_is_092(self) -> None:
        assert _load().revision == "092"

    def test_continues_089_chain(self) -> None:
        """089 is the head of the v6 schema chain after 080-088. We hop
        straight to 092 since 090/091 are intentionally left unallocated
        for any in-flight v6 sub-feature branches that may need a slot.
        """
        assert _load().down_revision == "089"


class TestUpgradeEmitsTables:
    def _run_upgrade_with_mock(self) -> MagicMock:
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()
        return mock_op

    def test_creates_two_tables(self) -> None:
        mock_op = self._run_upgrade_with_mock()
        names = {c.args[0] for c in mock_op.create_table.call_args_list}
        assert names == {"atlas_cell_rule_candidates", "atlas_conviction_daily"}

    def test_both_in_atlas_schema(self) -> None:
        mock_op = self._run_upgrade_with_mock()
        for call in mock_op.create_table.call_args_list:
            assert call.kwargs.get("schema") == "atlas"


class TestRuleCandidatesSchema:
    def _candidate_columns(self) -> list:
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()
        for call in mock_op.create_table.call_args_list:
            if call.args[0] == "atlas_cell_rule_candidates":
                return list(call.args[1:])
        raise AssertionError("atlas_cell_rule_candidates not created")

    def test_required_columns_present(self) -> None:
        cols = [c.name for c in self._candidate_columns() if hasattr(c, "name")]
        for required in (
            "cell_definition_id",
            "rank",
            "rule_dsl",
            "archetype",
            "ic",
            "friction_adjusted_excess",
            "bh_q_value",
            "eli5",
            "validated",
            "notes",
        ):
            assert required in cols, f"missing column: {required}"

    def test_unique_constraint_cell_plus_rank(self) -> None:
        """Top-5 ranks per cell, exclusive."""
        cols = self._candidate_columns()
        uqs = [c for c in cols if c.__class__.__name__ == "UniqueConstraint"]
        assert any(
            "cell_definition_id" in [col for col in uq.columns]
            and "rank" in [col for col in uq.columns]
            for uq in uqs
        ) or any(getattr(uq, "name", "") == "uq_atlas_cell_rule_candidates_cell_rank" for uq in uqs)


class TestConvictionDailySchema:
    def _conv_columns(self) -> list:
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.upgrade()
        for call in mock_op.create_table.call_args_list:
            if call.args[0] == "atlas_conviction_daily":
                return list(call.args[1:])
        raise AssertionError("atlas_conviction_daily not created")

    def test_required_columns_present(self) -> None:
        cols = [c.name for c in self._conv_columns() if hasattr(c, "name")]
        for required in (
            "snapshot_date",
            "instrument_id",
            "tenure",
            "verdict",
            "best_rule_id",
            "cell_definition_id",
            "ic",
            "friction_adjusted_excess",
            "fired_predicates",
            "eli5",
            "conflict",
        ):
            assert required in cols, f"missing column: {required}"

    def test_natural_key_unique_constraint(self) -> None:
        cols = self._conv_columns()
        uq_names = [
            getattr(c, "name", "") for c in cols if c.__class__.__name__ == "UniqueConstraint"
        ]
        assert "uq_atlas_conviction_daily_natural_key" in uq_names

    def test_tenure_check_constraint(self) -> None:
        cols = self._conv_columns()
        ck_names = [
            getattr(c, "name", "") for c in cols if c.__class__.__name__ == "CheckConstraint"
        ]
        assert "ck_atlas_conviction_daily_tenure" in ck_names
        assert "ck_atlas_conviction_daily_verdict" in ck_names


class TestDowngradeReverses:
    def test_downgrade_drops_both_tables(self) -> None:
        mod = _load()
        with patch.object(mod, "op") as mock_op:
            mock_op.get_bind.return_value = MagicMock()
            mod.downgrade()
        dropped = {c.args[0] for c in mock_op.drop_table.call_args_list}
        assert dropped == {"atlas_cell_rule_candidates", "atlas_conviction_daily"}
