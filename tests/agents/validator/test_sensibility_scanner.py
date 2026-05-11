"""Tests for atlas.agents.validator.sensibility_scanner.

Tests use a mock SQL layer rather than live DB. The per-row scanning logic
is exercised by passing fake row dicts directly to the internal helper.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from atlas.agents.validator.sensibility_scanner import _scan_row, scan_table

# ---------------------------------------------------------------------------
# _scan_row — per-row logic (no I/O)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scan_row_detects_inf() -> None:
    row: dict[str, Any] = {
        "instrument_id": "RELIANCE",
        "date": date(2026, 1, 5),
        "ema_50": float("inf"),
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "P0"
    assert f.finding_class == "insensible_value"
    assert "ema_50" in f.surface
    assert "RELIANCE" in f.identifier


@pytest.mark.unit
def test_scan_row_detects_nan() -> None:
    row: dict[str, Any] = {
        "instrument_id": "TCS",
        "date": date(2026, 1, 5),
        "rs_3m": float("nan"),
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert len(findings) == 1
    assert findings[0].severity == "P0"


@pytest.mark.unit
def test_scan_row_detects_future_date() -> None:
    future = date.today() + timedelta(days=5)
    row: dict[str, Any] = {
        "instrument_id": "INFY",
        "date": future,
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert len(findings) == 1
    assert findings[0].severity == "P0"


@pytest.mark.unit
def test_scan_row_detects_negative_volume() -> None:
    row: dict[str, Any] = {
        "instrument_id": "HDFCBANK",
        "date": date(2026, 1, 5),
        "volume": -500,
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert len(findings) == 1
    assert findings[0].severity == "P1"


@pytest.mark.unit
def test_scan_row_detects_percentile_out_of_range() -> None:
    row: dict[str, Any] = {
        "instrument_id": "WIPRO",
        "date": date(2026, 1, 5),
        "rs_percentile": 1.5,
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert len(findings) == 1
    assert findings[0].severity == "P1"


@pytest.mark.unit
def test_scan_row_clean_row_returns_empty() -> None:
    row: dict[str, Any] = {
        "instrument_id": "ITC",
        "date": date(2026, 1, 5),
        "ema_50": 450.0,
        "rs_percentile": 0.75,
        "volume": 1_000_000,
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert findings == []


@pytest.mark.unit
def test_scan_row_null_values_skipped() -> None:
    row: dict[str, Any] = {
        "instrument_id": "LT",
        "date": date(2026, 1, 5),
        "rs_percentile": None,
        "ema_50": None,
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert findings == []


@pytest.mark.unit
def test_scan_row_multiple_violations() -> None:
    row: dict[str, Any] = {
        "instrument_id": "BAD",
        "date": date(2026, 1, 5),
        "ema_50": math.inf,
        "volume": -100,
        "rs_percentile": 2.0,
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert len(findings) == 3


@pytest.mark.unit
def test_scan_row_identifier_uses_pk_columns() -> None:
    row: dict[str, Any] = {
        "instrument_id": "SBIN",
        "date": date(2026, 1, 5),
        "ema_50": math.inf,
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    assert "SBIN" in findings[0].identifier


@pytest.mark.unit
def test_finding_dataclass_fields() -> None:
    row: dict[str, Any] = {
        "instrument_id": "TEST",
        "date": date(2026, 1, 5),
        "rs_percentile": -0.1,
    }
    findings = _scan_row(row, table="atlas_stock_metrics_daily")
    f = findings[0]
    assert f.finding_class == "insensible_value"
    assert f.severity in ("P0", "P1", "P2", "P3")
    assert "." in f.surface  # should be table.column
    assert f.expected_value is not None
    assert f.actual_value is not None
    assert isinstance(f.evidence, dict)


# ---------------------------------------------------------------------------
# scan_table — integration with mocked engine
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scan_table_unknown_table_raises() -> None:
    engine = MagicMock()
    with pytest.raises(ValueError, match="not in TABLE_WHITELIST"):
        scan_table(engine, "some_unknown_table")


@pytest.mark.unit
def test_scan_table_returns_findings_from_rows() -> None:
    """scan_table with a mocked engine that returns one poisoned row.

    SQLAlchemy result rows are iterable tuples of values (not dicts);
    keys() returns the column names separately.
    """
    col_names = ["instrument_id", "date", "ema_50", "rs_percentile", "volume"]
    # Build a tuple of values matching the column order — same as SA row
    row_values = ("FAKE", date(2026, 1, 5), float("inf"), 0.5, 1_000)

    engine = MagicMock()
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.keys.return_value = col_names
    mock_result.__iter__ = MagicMock(return_value=iter([row_values]))
    mock_conn.execute.return_value = mock_result
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = mock_conn

    with patch(
        "atlas.agents.validator.sensibility_scanner._build_query",
        return_value=("SELECT 1", {}),
    ):
        findings = scan_table(engine, "atlas_stock_metrics_daily", sample_size=100)

    assert len(findings) == 1
    assert findings[0].severity == "P0"
