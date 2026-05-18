"""Smoke tests for `atlas-lab states classify`.

Unit tests run without a live DB. Integration test requires ATLAS_INTEGRATION_TESTS=1
and a live DB with atlas.atlas_stock_state_daily (migration 072 applied).
"""

from __future__ import annotations

import argparse
import os

import pandas as pd
import pytest

_SKIP_INTEGRATION = pytest.mark.skipif(
    not os.environ.get("ATLAS_INTEGRATION_TESTS"),
    reason="Requires ATLAS_INTEGRATION_TESTS=1 (live DB)",
)


# ---------------------------------------------------------------------------
# Unit tests (no DB required)
# ---------------------------------------------------------------------------


def test_compute_features_for_stock_columns():
    """_compute_features_for_stock returns all required feature columns."""
    from atlas.trading.cli import _compute_features_for_stock

    n = 300  # enough rows to fill SMA-200 window
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    g = pd.DataFrame(
        {
            "instrument_id": "TEST",
            "date": dates,
            "close": 100.0 + pd.Series(range(n)) * 0.1,
            "high": 101.0 + pd.Series(range(n)) * 0.1,
            "low": 99.0 + pd.Series(range(n)) * 0.1,
            "volume": 1_000_000.0,
        }
    )
    out = _compute_features_for_stock(g)

    required_cols = [
        "instrument_id",
        "date",
        "close",
        "sma_50",
        "sma_150",
        "sma_200",
        "sma_50_slope",
        "sma_150_slope",
        "sma_200_slope",
        "atr_14",
        "atr_14_50d_avg",
        "volume",
        "volume_50d_avg",
        "max_close_60d",
        "distribution_days_25d",
        "distribution_days_5d",
        "ret_12m_raw",
        "low_252_age_days",
        "liquidity_score",
        "data_gap_count",
    ]
    missing = [c for c in required_cols if c not in out.columns]
    assert not missing, f"Missing feature columns: {missing}"
    assert len(out) == n


def test_compute_features_for_stock_sma200_nan_before_warmup():
    """SMA-200 is NaN for the first 199 rows (warm-up not yet full)."""
    from atlas.trading.cli import _compute_features_for_stock

    n = 250
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    g = pd.DataFrame(
        {
            "instrument_id": "TEST",
            "date": dates,
            "close": 100.0 + pd.Series(range(n)) * 0.05,
            "high": 101.0 + pd.Series(range(n)) * 0.05,
            "low": 99.0 + pd.Series(range(n)) * 0.05,
            "volume": 500_000.0,
        }
    )
    out = _compute_features_for_stock(g)
    assert out["sma_200"].iloc[:199].isna().all(), "SMA-200 should be NaN before row 200"
    assert not pd.isna(out["sma_200"].iloc[199]), "SMA-200 should be valid at row 200"


def test_compute_features_for_stock_no_volume_column():
    """Falls back gracefully when volume column is absent (e.g., ETF path)."""
    from atlas.trading.cli import _compute_features_for_stock

    n = 60
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    g = pd.DataFrame(
        {
            "instrument_id": "TEST",
            "date": dates,
            "close": 100.0 + pd.Series(range(n)) * 0.1,
            "high": 101.0 + pd.Series(range(n)) * 0.1,
            "low": 99.0 + pd.Series(range(n)) * 0.1,
            # no volume column
        }
    )
    out = _compute_features_for_stock(g)
    assert "volume" in out.columns
    assert out["volume"].isna().all(), "volume should be all-NaN when absent from input"


def test_states_classify_cmd_missing_db_url(monkeypatch):
    """_states_classify_cmd raises SystemExit when ATLAS_DB_URL is not set."""
    from atlas.trading.cli import _states_classify_cmd

    monkeypatch.delenv("ATLAS_DB_URL", raising=False)
    args = argparse.Namespace(
        start="2024-06-03",
        end="2024-06-07",
        universe="stocks_nifty500",
        classifier_version="v1.0",
    )
    with pytest.raises(SystemExit):
        _states_classify_cmd(args)


def test_states_classify_help():
    """CLI help text includes 'states' and 'classify' subcommands."""
    import subprocess
    import sys

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "atlas.trading.cli", "states", "classify", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "ATLAS_DB_URL": "postgresql://placeholder"},
    )
    assert result.returncode == 0
    assert "--start" in result.stdout
    assert "--end" in result.stdout
    assert "--universe" in result.stdout
    assert "--classifier-version" in result.stdout


# ---------------------------------------------------------------------------
# Integration test (live DB required)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
def test_states_classify_writes_rows():
    """End-to-end smoke: CLI classifies a 1-week window for stocks and writes rows."""
    from sqlalchemy import create_engine, text

    from atlas.trading.cli import _states_classify_cmd

    args = argparse.Namespace(
        start="2024-06-03",
        end="2024-06-07",
        universe="stocks_nifty500",
        classifier_version="v1.0-smoke",
    )
    rc = _states_classify_cmd(args)
    assert rc == 0, "Expected return code 0 from _states_classify_cmd"

    # Verify rows were written.
    db_url = (
        os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://").split("?")[0]
    )
    eng = create_engine(db_url)
    with eng.connect() as c:
        n = c.execute(
            text(
                "SELECT COUNT(*) FROM atlas.atlas_stock_state_daily"
                " WHERE classifier_version = 'v1.0-smoke'"
            )
        ).scalar()
    assert n is not None and n > 0, f"Expected some rows for v1.0-smoke, got {n}"

    # Cleanup so re-runs are idempotent on the test table.
    with eng.begin() as c:
        c.execute(
            text(
                "DELETE FROM atlas.atlas_stock_state_daily"
                " WHERE classifier_version = 'v1.0-smoke'"
            )
        )
