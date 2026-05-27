"""Tests for atlas.ingest.macro.fred_ingest.

TDD order: tests written FIRST, then implementation in fred_ingest.py.
All DB calls are mocked — these tests never touch the real database.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# fetch_series
# ---------------------------------------------------------------------------


def test_fetch_series_returns_dataframe_with_date_and_value():
    """Happy path: FRED returns one observation, we get a clean DataFrame."""
    from atlas.ingest.macro.fred_ingest import fetch_series

    with (
        patch("atlas.ingest.macro.fred_ingest.requests.get") as mock_get,
        patch.dict("os.environ", {"FRED_API_KEY": "test-key"}),
    ):
        mock_get.return_value.json.return_value = {
            "observations": [{"date": "2024-01-01", "value": "4.05"}]
        }
        mock_get.return_value.raise_for_status = MagicMock()

        df = fetch_series("DGS10", "2024-01-01", "2024-01-31")

    assert list(df.columns) == ["date", "value"]
    assert len(df) == 1
    assert df.iloc[0]["date"] == "2024-01-01"
    assert df.iloc[0]["value"] == pytest.approx(4.05)


def test_fetch_series_filters_missing_observations():
    """FRED returns '.' for missing data — these must be dropped."""
    from atlas.ingest.macro.fred_ingest import fetch_series

    with (
        patch("atlas.ingest.macro.fred_ingest.requests.get") as mock_get,
        patch.dict("os.environ", {"FRED_API_KEY": "test-key"}),
    ):
        mock_get.return_value.json.return_value = {
            "observations": [
                {"date": "2024-01-01", "value": "4.05"},
                {"date": "2024-01-02", "value": "."},  # missing — must be excluded
                {"date": "2024-01-03", "value": "4.10"},
            ]
        }
        mock_get.return_value.raise_for_status = MagicMock()

        df = fetch_series("DGS10", "2024-01-01", "2024-01-03")

    assert len(df) == 2
    assert "2024-01-02" not in df["date"].values


def test_fetch_series_passes_api_key_in_params():
    """API key must be passed as a query parameter."""
    from atlas.ingest.macro.fred_ingest import fetch_series

    with (
        patch("atlas.ingest.macro.fred_ingest.requests.get") as mock_get,
        patch.dict("os.environ", {"FRED_API_KEY": "test-key-123"}),
    ):
        mock_get.return_value.json.return_value = {"observations": []}
        mock_get.return_value.raise_for_status = MagicMock()

        fetch_series("DGS10", "2024-01-01", "2024-01-31")

    call_kwargs = mock_get.call_args
    params = call_kwargs[1]["params"] if call_kwargs[1] else call_kwargs[0][1]
    assert params["api_key"] == "test-key-123"
    assert params["series_id"] == "DGS10"


def test_fetch_series_raises_when_no_api_key():
    """Missing FRED_API_KEY must raise KeyError immediately."""
    import os

    from atlas.ingest.macro.fred_ingest import fetch_series

    env_without_key = {k: v for k, v in os.environ.items() if k != "FRED_API_KEY"}
    with patch.dict("os.environ", env_without_key, clear=True):
        with pytest.raises(KeyError, match="FRED_API_KEY"):
            fetch_series("DGS10", "2024-01-01", "2024-01-31")


def test_fetch_series_empty_response_returns_empty_dataframe():
    """FRED returning zero observations gives an empty DataFrame."""
    from atlas.ingest.macro.fred_ingest import fetch_series

    with (
        patch("atlas.ingest.macro.fred_ingest.requests.get") as mock_get,
        patch.dict("os.environ", {"FRED_API_KEY": "test-key"}),
    ):
        mock_get.return_value.json.return_value = {"observations": []}
        mock_get.return_value.raise_for_status = MagicMock()

        df = fetch_series("DGS10", "2024-01-01", "2024-01-01")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert list(df.columns) == ["date", "value"]


# ---------------------------------------------------------------------------
# upsert_macro_col
# ---------------------------------------------------------------------------


def test_upsert_macro_col_returns_row_count():
    """upsert_macro_col must return the count of rows upserted."""
    from atlas.ingest.macro.fred_ingest import upsert_macro_col

    df = pd.DataFrame(
        [
            {"date": "2024-01-01", "value": 4.05},
            {"date": "2024-01-02", "value": 4.10},
        ]
    )

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    with patch("atlas.ingest.macro.fred_ingest.get_engine", return_value=mock_engine):
        count = upsert_macro_col("us_10y_yield", df, engine=mock_engine)

    assert count == 2


def test_upsert_macro_col_uses_decimal_not_float():
    """All values passed to the DB must be Decimal, never raw float."""
    from atlas.ingest.macro.fred_ingest import upsert_macro_col

    df = pd.DataFrame([{"date": "2024-01-01", "value": 4.05}])

    executed_params = []

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    def capture_execute(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn.execute.side_effect = capture_execute
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    with patch("atlas.ingest.macro.fred_ingest.get_engine", return_value=mock_engine):
        upsert_macro_col("us_10y_yield", df, engine=mock_engine)

    assert len(executed_params) == 1
    param_val = executed_params[0]["v"]
    assert isinstance(param_val, Decimal), f"Expected Decimal, got {type(param_val)}"


def test_upsert_macro_col_empty_dataframe_returns_zero():
    """Empty DataFrame must return 0 without touching the DB."""
    from atlas.ingest.macro.fred_ingest import upsert_macro_col

    df = pd.DataFrame(columns=["date", "value"])

    mock_engine = MagicMock()

    with patch("atlas.ingest.macro.fred_ingest.get_engine", return_value=mock_engine):
        count = upsert_macro_col("us_10y_yield", df, engine=mock_engine)

    assert count == 0
    mock_engine.begin.assert_not_called()
