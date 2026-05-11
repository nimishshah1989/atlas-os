"""Tests for atlas.agents.validator.schema_scanner.

All tests use a mock SQLAlchemy engine — no live DB required.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from atlas.agents.validator.coverage_loader import TableCoverage
from atlas.agents.validator.schema_scanner import (
    _check_date_coverage,
    _check_null_forbidden,
    scan_coverage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(
    table_name: str = "atlas_market_regime_daily",
    expected_dates: str = "business_days",
    coverage_tolerance_pct: float = 100.0,
    expected_instruments_min: int | None = None,
    null_forbidden_columns: tuple[str, ...] = (),
) -> TableCoverage:
    return TableCoverage(
        table_name=table_name,
        description="test",
        expected_dates=expected_dates,
        coverage_tolerance_pct=coverage_tolerance_pct,
        expected_instruments_min=expected_instruments_min,
        null_forbidden_columns=null_forbidden_columns,
    )


def _mock_engine_for_range(
    d_min: date | None,
    d_max: date | None,
    total_rows: int,
    date_counts: dict[date, int] | None = None,
) -> MagicMock:
    """Build a mock engine that returns the given date range + per-date counts."""
    engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = mock_conn

    # First execute call = MIN/MAX/COUNT query
    range_row = MagicMock()
    range_row.__getitem__ = lambda self, i: (d_min, d_max, total_rows)[i]

    range_result = MagicMock()
    range_result.fetchone.return_value = range_row

    if date_counts is not None:
        # Second execute call = per-date GROUP BY
        per_date_result = MagicMock()
        per_date_result.__iter__ = MagicMock(return_value=iter(list(date_counts.items())))
        mock_conn.execute.side_effect = [range_result, per_date_result]
    else:
        mock_conn.execute.return_value = range_result

    return engine


# ---------------------------------------------------------------------------
# _check_date_coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_date_coverage_empty_table_returns_p0() -> None:
    """Empty table (0 rows) raises a P0 data_gap Finding."""
    engine = _mock_engine_for_range(None, None, 0)
    spec = _make_spec(coverage_tolerance_pct=100.0)
    findings = _check_date_coverage(engine, spec, "atlas")
    assert len(findings) == 1
    assert findings[0].severity == "P0"
    assert findings[0].finding_class == "data_gap"


@pytest.mark.unit
def test_check_date_coverage_missing_dates_flagged() -> None:
    """A table missing 50% of expected business dates gets a P0 coverage finding."""
    # Use a short known range: Mon 2026-01-05 to Fri 2026-01-09 = 5 business days
    d_min = date(2026, 1, 5)
    d_max = date(2026, 1, 9)
    # Only 2 of 5 dates present
    date_counts = {
        date(2026, 1, 5): 1,
        date(2026, 1, 6): 1,
    }
    engine = _mock_engine_for_range(d_min, d_max, total_rows=2, date_counts=date_counts)
    spec = _make_spec(coverage_tolerance_pct=99.0)

    with patch("atlas.agents.validator.schema_scanner._yesterday", return_value=date(2026, 1, 10)):
        findings = _check_date_coverage(engine, spec, "atlas")

    assert any(f.severity == "P0" for f in findings)
    assert any(f.finding_class == "data_gap" for f in findings)


@pytest.mark.unit
def test_check_date_coverage_clean_table_returns_empty() -> None:
    """A table with 100% date coverage returns no findings."""
    d_min = date(2026, 1, 5)
    d_max = date(2026, 1, 9)
    # All 5 Mon-Fri dates present
    date_counts = {
        date(2026, 1, 5): 1,
        date(2026, 1, 6): 1,
        date(2026, 1, 7): 1,
        date(2026, 1, 8): 1,
        date(2026, 1, 9): 1,
    }
    engine = _mock_engine_for_range(d_min, d_max, total_rows=5, date_counts=date_counts)
    spec = _make_spec(coverage_tolerance_pct=100.0)

    with patch("atlas.agents.validator.schema_scanner._yesterday", return_value=date(2026, 1, 10)):
        findings = _check_date_coverage(engine, spec, "atlas")

    assert findings == []


@pytest.mark.unit
def test_check_date_coverage_tolerance_zero_skips_check() -> None:
    """Tables with coverage_tolerance_pct=0 are skipped entirely."""
    engine = MagicMock()
    spec = _make_spec(coverage_tolerance_pct=0.0)
    findings = _check_date_coverage(engine, spec, "atlas")
    engine.connect.assert_not_called()
    assert findings == []


# ---------------------------------------------------------------------------
# _check_null_forbidden
# ---------------------------------------------------------------------------


def _mock_engine_for_nulls(
    col_exists: bool,
    null_count: int,
) -> MagicMock:
    """Engine mock for null-check tests."""
    engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = mock_conn

    col_check_result = MagicMock()
    col_check_result.fetchone.return_value = (1,) if col_exists else None

    null_result = MagicMock()
    null_result.scalar.return_value = null_count

    mock_conn.execute.side_effect = [col_check_result, null_result]
    return engine


@pytest.mark.unit
def test_check_null_forbidden_flags_nulls() -> None:
    """NULL values in a forbidden column produce a P1 data_gap Finding."""
    engine = _mock_engine_for_nulls(col_exists=True, null_count=5)
    spec = _make_spec(null_forbidden_columns=("regime_state",))
    findings = _check_null_forbidden(engine, spec, "atlas")
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "P1"
    assert f.finding_class == "data_gap"
    assert "regime_state" in f.surface


@pytest.mark.unit
def test_check_null_forbidden_passes_clean_column() -> None:
    """Zero NULLs in a forbidden column returns no findings."""
    engine = _mock_engine_for_nulls(col_exists=True, null_count=0)
    spec = _make_spec(null_forbidden_columns=("regime_state",))
    findings = _check_null_forbidden(engine, spec, "atlas")
    assert findings == []


@pytest.mark.unit
def test_check_null_forbidden_skips_missing_column() -> None:
    """Column missing from schema (schema drift) is skipped without crashing."""
    engine = _mock_engine_for_nulls(col_exists=False, null_count=0)
    spec = _make_spec(null_forbidden_columns=("ghost_column",))
    findings = _check_null_forbidden(engine, spec, "atlas")
    # Should not raise; no Finding for a missing column
    assert findings == []


# ---------------------------------------------------------------------------
# scan_coverage — integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scan_coverage_aggregates_findings_from_all_specs() -> None:
    """scan_coverage returns findings from every spec in the coverage map."""
    # Two specs, one empty table (P0), one clean.
    spec_empty = _make_spec(table_name="table_a", coverage_tolerance_pct=100.0)
    spec_clean_no_enforce = _make_spec(table_name="table_b", coverage_tolerance_pct=0.0)

    empty_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    empty_engine.connect.return_value = mock_conn

    range_row = MagicMock()
    range_row.__getitem__ = lambda self, i: (None, None, 0)[i]
    range_result = MagicMock()
    range_result.fetchone.return_value = range_row
    mock_conn.execute.return_value = range_result

    with patch(
        "atlas.agents.validator.schema_scanner.load_coverage_map",
        return_value=[spec_empty, spec_clean_no_enforce],
    ):
        findings = scan_coverage(empty_engine, coverage_map=None)

    assert any(f.severity == "P0" for f in findings)
    assert any(f.finding_class == "data_gap" for f in findings)
