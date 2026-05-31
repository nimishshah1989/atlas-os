"""Regression tests for migration 072 — atlas_stock_state_daily.

Unit tests (always run, no DB)
------------------------------
Mock alembic.op to verify create_table, check constraints, and indexes
are emitted by upgrade() / downgrade().

Integration tests (require ATLAS_INTEGRATION_TESTS=1)
------------------------------------------------------
Verify the table and constraints are actually present in the live DB.
Skipped by default; run on EC2 after migration is applied.
"""

from __future__ import annotations

import importlib
import os
import types
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_MODULE = "migrations.versions.072_atlas_stock_state_daily"
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
        assert _load().revision == "072"

    def test_down_revision(self) -> None:
        assert _load().down_revision == "071"

    def test_branch_labels_none(self) -> None:
        assert _load().branch_labels is None

    def test_depends_on_none(self) -> None:
        assert _load().depends_on is None


# ---------------------------------------------------------------------------
# Unit: upgrade() emits correct DDL via mocked alembic.op
# ---------------------------------------------------------------------------


class TestUpgrade:
    def _run(self) -> tuple[MagicMock, MagicMock]:
        mod = _load()
        with (
            patch("alembic.op.create_table") as mock_ct,
            patch("alembic.op.create_index") as mock_ci,
        ):
            mod.upgrade()
        return mock_ct, mock_ci

    def test_creates_atlas_stock_state_daily(self) -> None:
        mock_ct, _ = self._run()
        names = [c.args[0] for c in mock_ct.call_args_list]
        assert "atlas_stock_state_daily" in names

    def test_creates_exactly_one_table(self) -> None:
        mock_ct, _ = self._run()
        names = [c.args[0] for c in mock_ct.call_args_list]
        assert len(names) == 1, f"expected 1 table, got {names}"

    def test_creates_date_index(self) -> None:
        _, mock_ci = self._run()
        names = [c.args[0] for c in mock_ci.call_args_list]
        assert "ix_atlas_stock_state_daily_date" in names

    def test_creates_date_state_index(self) -> None:
        _, mock_ci = self._run()
        names = [c.args[0] for c in mock_ci.call_args_list]
        assert "ix_atlas_stock_state_daily_date_state" in names

    def test_creates_exactly_two_indexes(self) -> None:
        _, mock_ci = self._run()
        names = [c.args[0] for c in mock_ci.call_args_list]
        assert len(names) == 2, f"expected 2 indexes, got {names}"

    def test_table_uses_atlas_schema(self) -> None:
        mock_ct, _ = self._run()
        call_kwargs = mock_ct.call_args_list[0].kwargs
        assert call_kwargs.get("schema") == "atlas"

    def test_check_constraint_state_value_present(self) -> None:
        """ck_state_value CHECK constraint must be emitted via create_table."""
        mock_ct, _ = self._run()
        # Column args are positional; scan all args for CheckConstraint with the right name
        call_args = mock_ct.call_args_list[0].args
        check_names = [a.name for a in call_args if isinstance(a, sa.CheckConstraint)]
        assert "ck_state_value" in check_names, (
            f"ck_state_value CHECK constraint not found. Constraints: {check_names}"
        )

    def test_check_constraint_urgency_value_present(self) -> None:
        """ck_urgency_value CHECK constraint must be emitted via create_table."""
        mock_ct, _ = self._run()
        call_args = mock_ct.call_args_list[0].args
        check_names = [a.name for a in call_args if isinstance(a, sa.CheckConstraint)]
        assert "ck_urgency_value" in check_names, (
            f"ck_urgency_value CHECK constraint not found. Constraints: {check_names}"
        )


# ---------------------------------------------------------------------------
# Unit: downgrade() drops table and indexes
# ---------------------------------------------------------------------------


class TestDowngrade:
    def _run(self) -> tuple[MagicMock, MagicMock]:
        mod = _load()
        with (
            patch("alembic.op.drop_table") as mock_dt,
            patch("alembic.op.drop_index") as mock_di,
        ):
            mod.downgrade()
        return mock_dt, mock_di

    def test_drops_atlas_stock_state_daily(self) -> None:
        mock_dt, _ = self._run()
        names = [c.args[0] for c in mock_dt.call_args_list]
        assert "atlas_stock_state_daily" in names

    def test_drops_date_index(self) -> None:
        _, mock_di = self._run()
        names = [c.args[0] for c in mock_di.call_args_list]
        assert "ix_atlas_stock_state_daily_date" in names

    def test_drops_date_state_index(self) -> None:
        _, mock_di = self._run()
        names = [c.args[0] for c in mock_di.call_args_list]
        assert "ix_atlas_stock_state_daily_date_state" in names


# ---------------------------------------------------------------------------
# Integration: live DB assertions (skipped unless ATLAS_INTEGRATION_TESTS=1)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
def test_atlas_stock_state_daily_columns_present(db_engine: sa.Engine) -> None:
    """Migration 072 creates the table with all required columns."""
    with db_engine.connect() as c:
        cols = c.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='atlas' AND table_name='atlas_stock_state_daily'"
            )
        ).fetchall()
    names = {r[0] for r in cols}
    required = {
        "instrument_id",
        "date",
        "state",
        "prior_state",
        "state_since_date",
        "dwell_days",
        "dwell_percentile",
        "urgency_score",
        "within_state_rank",
        "rs_rank_12m",
        "close_vs_sma_50",
        "close_vs_sma_150",
        "close_vs_sma_200",
        "sma_200_slope",
        "volume_ratio_50d",
        "distribution_days",
        "classifier_version",
        "created_at",
    }
    missing = required - names
    assert not missing, f"missing columns: {missing}"


@_SKIP_INTEGRATION
def test_atlas_stock_state_daily_check_constraints(db_engine: sa.Engine) -> None:
    """ck_state_value rejects bogus state values."""
    with pytest.raises(IntegrityError, match="ck_state_value"):
        with db_engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO atlas.atlas_stock_state_daily "
                    "(instrument_id, date, state, state_since_date,"
                    " dwell_days, urgency_score, classifier_version) "
                    "VALUES (gen_random_uuid(), '2026-01-01',"
                    " 'bogus_state', '2026-01-01', 0, 'normal', 'v1')"
                )
            )
