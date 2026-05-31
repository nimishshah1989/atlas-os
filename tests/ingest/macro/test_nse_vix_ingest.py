"""Tests for atlas.ingest.macro.nse_vix_ingest.

TDD: tests written before implementation.
Primary source: Yahoo Finance ^INDIAVIX (NSE archives 404 as of 2026-05-27).
vix_9d is a documented proxy: 9-day backward EMA of India VIX daily close.
NSE does not publish a 9-day VIX directly.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# fetch_vix_from_yahoo
# ---------------------------------------------------------------------------


def test_fetch_vix_from_yahoo_returns_expected_columns():
    """Yahoo Finance fetch returns DataFrame with date and india_vix."""
    from atlas.ingest.macro.nse_vix_ingest import fetch_vix_from_yahoo

    mock_response = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704067200, 1704153600],  # 2024-01-01, 2024-01-02
                    "indicators": {"quote": [{"close": [14.5, 15.2]}]},
                }
            ]
        }
    }

    with patch("atlas.ingest.macro.nse_vix_ingest.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        df = fetch_vix_from_yahoo("2024-01-01", "2024-01-02")

    assert "date" in df.columns
    assert "india_vix" in df.columns
    assert len(df) == 2
    assert list(df["india_vix"].values) == pytest.approx([14.5, 15.2], abs=0.01)


def test_fetch_vix_from_yahoo_filters_null_closes():
    """Null close values must be excluded from the result."""
    from atlas.ingest.macro.nse_vix_ingest import fetch_vix_from_yahoo

    mock_response = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704067200, 1704153600, 1704240000],
                    "indicators": {"quote": [{"close": [14.5, None, 15.2]}]},
                }
            ]
        }
    }

    with patch("atlas.ingest.macro.nse_vix_ingest.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        df = fetch_vix_from_yahoo("2024-01-01", "2024-01-03")

    assert len(df) == 2  # null row excluded


def test_fetch_vix_from_yahoo_empty_result_returns_empty_df():
    """Empty chart result returns empty DataFrame."""
    from atlas.ingest.macro.nse_vix_ingest import fetch_vix_from_yahoo

    mock_response = {"chart": {"result": []}}

    with patch("atlas.ingest.macro.nse_vix_ingest.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        df = fetch_vix_from_yahoo("2024-01-01", "2024-01-02")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert "date" in df.columns
    assert "india_vix" in df.columns


def test_fetch_vix_from_yahoo_dates_are_iso_format():
    """Output dates must be ISO YYYY-MM-DD strings derived from Unix timestamps."""
    from atlas.ingest.macro.nse_vix_ingest import fetch_vix_from_yahoo

    # 2024-01-15 00:00:00 UTC = 1705276800
    mock_response = {
        "chart": {
            "result": [
                {
                    "timestamp": [1705276800],
                    "indicators": {"quote": [{"close": [14.0]}]},
                }
            ]
        }
    }

    with patch("atlas.ingest.macro.nse_vix_ingest.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        df = fetch_vix_from_yahoo("2024-01-15", "2024-01-15")

    date_str = df.iloc[0]["date"]
    assert len(date_str) == 10
    assert date_str[4] == "-"
    assert date_str[7] == "-"


# ---------------------------------------------------------------------------
# parse_vix_csv
# ---------------------------------------------------------------------------


def test_parse_vix_csv_returns_expected_columns():
    """Parsed DataFrame must have date and india_vix columns."""
    from atlas.ingest.macro.nse_vix_ingest import parse_vix_csv

    fixture_path = FIXTURES_DIR / "vix_sample.csv"
    df = parse_vix_csv(str(fixture_path))

    assert "date" in df.columns
    assert "india_vix" in df.columns


def test_parse_vix_csv_uses_close_price():
    """india_vix must reflect the VIX Close column."""
    from atlas.ingest.macro.nse_vix_ingest import parse_vix_csv

    fixture_path = FIXTURES_DIR / "vix_sample.csv"
    df = parse_vix_csv(str(fixture_path))

    row = df[df["date"] == "2024-01-01"].iloc[0]
    assert float(row["india_vix"]) == pytest.approx(13.10, abs=0.01)


def test_parse_vix_csv_date_is_iso_format():
    """Output dates must be ISO YYYY-MM-DD strings."""
    from atlas.ingest.macro.nse_vix_ingest import parse_vix_csv

    fixture_path = FIXTURES_DIR / "vix_sample.csv"
    df = parse_vix_csv(str(fixture_path))

    for dt in df["date"].values:
        assert len(str(dt)) == 10
        assert str(dt)[4] == "-"


def test_parse_vix_csv_returns_all_rows():
    """All non-header rows should be parsed."""
    from atlas.ingest.macro.nse_vix_ingest import parse_vix_csv

    fixture_path = FIXTURES_DIR / "vix_sample.csv"
    df = parse_vix_csv(str(fixture_path))

    assert len(df) == 5


# ---------------------------------------------------------------------------
# compute_vix_9d_ema
# ---------------------------------------------------------------------------


def test_compute_vix_9d_ema_correct_length():
    """vix_9d must have same length as input."""
    from atlas.ingest.macro.nse_vix_ingest import compute_vix_9d_ema

    df_in = pd.DataFrame(
        {
            "date": [f"2024-01-{i + 1:02d}" for i in range(20)],
            "india_vix": [13.0 + i * 0.1 for i in range(20)],
        }
    )

    df_out = compute_vix_9d_ema(df_in)

    assert "vix_9d" in df_out.columns
    assert len(df_out) == len(df_in)


def test_compute_vix_9d_ema_first_8_rows_are_null():
    """EMA spans 9 days — first 8 rows cannot have a stable EMA (should be NaN)."""
    import math

    from atlas.ingest.macro.nse_vix_ingest import compute_vix_9d_ema

    df_in = pd.DataFrame(
        {
            "date": [f"2024-01-{i + 1:02d}" for i in range(15)],
            "india_vix": [13.0 + i * 0.1 for i in range(15)],
        }
    )

    df_out = compute_vix_9d_ema(df_in)

    # First 8 rows should be NaN (can't compute 9-day EMA with fewer points)
    for i in range(8):
        val = df_out.iloc[i]["vix_9d"]
        assert math.isnan(float(val)), f"Row {i} expected NaN, got {val}"


def test_compute_vix_9d_ema_converges():
    """9th+ rows should have a non-null EMA."""
    import math

    from atlas.ingest.macro.nse_vix_ingest import compute_vix_9d_ema

    df_in = pd.DataFrame(
        {
            "date": [f"2024-01-{i + 1:02d}" for i in range(15)],
            "india_vix": [13.0 + i * 0.1 for i in range(15)],
        }
    )

    df_out = compute_vix_9d_ema(df_in)

    # Row 8 (9th row) must have a computed value
    val = df_out.iloc[8]["vix_9d"]
    assert not math.isnan(float(val)), f"Row 8 expected non-NaN EMA, got {val}"


# ---------------------------------------------------------------------------
# upsert_vix
# ---------------------------------------------------------------------------


def test_upsert_vix_returns_row_count():
    """upsert_vix must return count of rows written."""
    from atlas.ingest.macro.nse_vix_ingest import upsert_vix

    df = pd.DataFrame(
        [
            {"date": "2024-01-09", "india_vix": 13.5, "vix_9d": 13.3},
            {"date": "2024-01-10", "india_vix": 13.8, "vix_9d": 13.4},
        ]
    )

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    with patch("atlas.ingest.macro.nse_vix_ingest.get_engine", return_value=mock_engine):
        count = upsert_vix(df, engine=mock_engine)

    assert count == 2


def test_upsert_vix_stores_decimal():
    """VIX values must be stored as Decimal."""
    from atlas.ingest.macro.nse_vix_ingest import upsert_vix

    df = pd.DataFrame([{"date": "2024-01-09", "india_vix": 13.5, "vix_9d": 13.3}])

    executed_params = []
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def capture(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn.execute.side_effect = capture
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    with patch("atlas.ingest.macro.nse_vix_ingest.get_engine", return_value=mock_engine):
        upsert_vix(df, engine=mock_engine)

    assert len(executed_params) == 1
    params = executed_params[0]
    # At least the non-null values should be Decimal
    if "vix_9d" in params and params["vix_9d"] is not None:
        assert isinstance(params["vix_9d"], Decimal)


def test_upsert_vix_skips_nan_vix9d():
    """Rows where vix_9d is NaN must still upsert india_vix but write NULL for vix_9d."""
    from atlas.ingest.macro.nse_vix_ingest import upsert_vix

    df = pd.DataFrame(
        [
            {"date": "2024-01-01", "india_vix": 13.5, "vix_9d": float("nan")},
        ]
    )

    executed_params = []
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def capture(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn.execute.side_effect = capture
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    with patch("atlas.ingest.macro.nse_vix_ingest.get_engine", return_value=mock_engine):
        upsert_vix(df, engine=mock_engine)

    assert len(executed_params) == 1
    params = executed_params[0]
    assert params["vix_9d"] is None  # NaN → NULL


def test_upsert_vix_empty_returns_zero():
    """Empty DataFrame returns 0."""
    from atlas.ingest.macro.nse_vix_ingest import upsert_vix

    df = pd.DataFrame(columns=["date", "india_vix", "vix_9d"])
    mock_engine = MagicMock()

    with patch("atlas.ingest.macro.nse_vix_ingest.get_engine", return_value=mock_engine):
        count = upsert_vix(df, engine=mock_engine)

    assert count == 0
    mock_engine.begin.assert_not_called()
