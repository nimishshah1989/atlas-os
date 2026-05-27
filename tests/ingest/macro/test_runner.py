"""Tests for atlas.ingest.macro.runner.

Covers:
  - _forward_fill_monthly_col: validates forward-fill SQL behavior via mock
  - _derive_brent_inr: validates in-memory brent derivation
  - run_backfill: smoke test with all external calls mocked
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# _forward_fill_monthly_col
# ---------------------------------------------------------------------------


def test_forward_fill_monthly_col_executes_sql():
    """_forward_fill_monthly_col must execute an UPDATE statement."""
    from atlas.ingest.macro.runner import _forward_fill_monthly_col

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_result = MagicMock()
    mock_result.rowcount = 50
    mock_conn.execute.return_value = mock_result
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    count = _forward_fill_monthly_col("india_10y_yield", mock_engine)

    assert count == 50
    mock_conn.execute.assert_called_once()
    # Verify the SQL contains the expected pattern (UPDATE ... SET col = ...)
    sql_arg = mock_conn.execute.call_args[0][0]
    sql_str = str(sql_arg)
    assert "UPDATE" in sql_str or "update" in sql_str.lower()


def test_forward_fill_monthly_col_rejects_invalid_col():
    """_forward_fill_monthly_col must raise ValueError for non-monthly columns."""
    from atlas.ingest.macro.runner import _forward_fill_monthly_col

    mock_engine = MagicMock()

    with pytest.raises(ValueError, match="monthly-safe set"):
        _forward_fill_monthly_col("us_10y_yield", mock_engine)


def test_forward_fill_monthly_col_accepts_valid_cols():
    """_forward_fill_monthly_col must accept all three valid monthly columns."""
    from atlas.ingest.macro.runner import _forward_fill_monthly_col

    for col in ("india_10y_yield", "risk_free_91d", "cpi_yoy"):
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_result = MagicMock()
        mock_result.rowcount = 10
        mock_conn.execute.return_value = mock_result
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn

        count = _forward_fill_monthly_col(col, mock_engine)
        assert count == 10, f"Expected 10 for col {col!r}"


def test_forward_fill_monthly_col_passes_start_param():
    """_forward_fill_monthly_col must pass start date as SQL parameter."""
    from atlas.ingest.macro.runner import _forward_fill_monthly_col

    executed_params = []

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_result = MagicMock()
    mock_result.rowcount = 0

    def capture(sql, params=None):
        executed_params.append(params)
        return mock_result

    mock_conn.execute.side_effect = capture
    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn

    _forward_fill_monthly_col("risk_free_91d", mock_engine, start="2020-01-01")

    assert len(executed_params) == 1
    assert executed_params[0]["start"] == "2020-01-01"


# ---------------------------------------------------------------------------
# _derive_brent_inr
# ---------------------------------------------------------------------------


def test_derive_brent_inr_skips_empty_df():
    """_derive_brent_inr returns 0 when brent_usd DataFrame is empty."""
    from atlas.ingest.macro.runner import _derive_brent_inr

    df = pd.DataFrame(columns=["date", "value"])
    mock_engine = MagicMock()

    count = _derive_brent_inr(df, mock_engine, start="2024-01-01")

    assert count == 0
    mock_engine.begin.assert_not_called()


def test_derive_brent_inr_computes_product():
    """_derive_brent_inr must write brent_inr = brent_usd × usdinr as Decimal."""
    from atlas.ingest.macro.runner import _derive_brent_inr

    brent_df = pd.DataFrame([{"date": "2024-01-02", "value": 80.0}])

    executed_params = []

    # Mock the connect() for SELECT usdinr
    mock_select_result = MagicMock()
    mock_select_result.fetchall.return_value = [("2024-01-02", Decimal("83.50"))]

    mock_conn_ro = MagicMock()
    mock_conn_ro.__enter__ = MagicMock(return_value=mock_conn_ro)
    mock_conn_ro.__exit__ = MagicMock(return_value=False)
    mock_conn_ro.execute.return_value = mock_select_result

    # Mock the begin() for INSERT brent_inr
    mock_conn_rw = MagicMock()
    mock_conn_rw.__enter__ = MagicMock(return_value=mock_conn_rw)
    mock_conn_rw.__exit__ = MagicMock(return_value=False)

    def capture_insert(sql, params):
        executed_params.append(params)
        return MagicMock()

    mock_conn_rw.execute.side_effect = capture_insert

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn_ro
    mock_engine.begin.return_value = mock_conn_rw

    count = _derive_brent_inr(brent_df, mock_engine, start="2024-01-01")

    assert count == 1
    assert len(executed_params) == 1
    # brent_inr = 80.0 × 83.50 = 6680.00
    brent_inr_val = executed_params[0]["v"]
    assert isinstance(brent_inr_val, Decimal)
    assert float(brent_inr_val) == pytest.approx(6680.0, rel=1e-3)


# ---------------------------------------------------------------------------
# run_backfill (smoke test — all IO mocked)
# ---------------------------------------------------------------------------


def test_run_backfill_returns_dict_with_expected_keys():
    """run_backfill must return a dict including all major source keys."""
    from atlas.ingest.macro.runner import run_backfill

    mock_engine = MagicMock()

    with (
        patch("atlas.ingest.macro.runner.fred_ingest.run_all") as mock_fred,
        patch("atlas.ingest.macro.runner.fred_ingest.fetch_series") as mock_fetch,
        patch("atlas.ingest.macro.runner._forward_fill_monthly_col") as mock_ffill,
        patch("atlas.ingest.macro.runner.nse_bhavcopy_ingest.run_all") as mock_fii,
        patch("atlas.ingest.macro.runner.mospi_cpi_ingest.run_all") as mock_cpi,
        patch("atlas.ingest.macro.runner.nse_vix_ingest.run_all") as mock_vix,
        patch("atlas.ingest.macro.runner._derive_brent_inr") as mock_brent,
        patch.dict("os.environ", {"FRED_API_KEY": "test-key-12345678901234"}),
    ):
        mock_fred.return_value = {
            "us_10y_yield": 2500,
            "india_10y_yield": 123,
            "risk_free_91d": 123,
        }
        mock_fetch.return_value = pd.DataFrame([{"date": "2024-01-01", "value": 80.0}])
        mock_ffill.return_value = 50
        mock_fii.return_value = 1  # today only
        mock_cpi.return_value = 150
        mock_vix.return_value = 2500
        mock_brent.return_value = 2000

        results = run_backfill(start="2024-01-01", engine=mock_engine)

    assert isinstance(results, dict)
    assert "us_10y_yield" in results
    assert "india_10y_yield" in results
    assert "risk_free_91d" in results
    assert "vix_9d" in results
    assert "cpi_yoy" in results
    assert "brent_inr" in results
    assert "fii_dii" in results
