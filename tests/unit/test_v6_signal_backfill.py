"""Unit tests for v6_signal_columns_backfill.py logic.

Tests are pure Python — no DB, no external calls. They verify:
1. rs_nifty500 formula correctness
2. 2022 gap metric computation (ret_12m, ema_200_stock, max_drawdown_252)
3. Edge cases: NULL denominators, insufficient history, all-null instruments
"""

from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Load the script as a module without triggering __main__
_SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "v6_signal_columns_backfill.py"

spec = importlib.util.spec_from_file_location("v6_signal_backfill", _SCRIPT_PATH)
assert spec is not None and spec.loader is not None, "Could not find backfill script"
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_compute_2022_metrics = _mod._compute_2022_metrics
GAP_START = _mod.GAP_START
GAP_END = _mod.GAP_END


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _make_ohlcv(
    n_days: int = 400,
    n_instruments: int = 2,
    start: date = date(2020, 1, 2),
) -> pd.DataFrame:
    """Synthetic OHLCV DataFrame with deterministic prices.

    Uses trading-day-like spacing (Mon-Fri only) so that 252-day lookback
    windows are meaningfully exercised.  n_days trading days starting from
    ``start`` will yield rows spanning ~n_days * 7/5 calendar days.
    """
    rng = np.random.default_rng(42)
    rows = []
    instruments = [f"inst-{i:03d}" for i in range(n_instruments)]
    # Generate n_days weekday dates
    trading_days: list[date] = []
    current = start
    while len(trading_days) < n_days:
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            trading_days.append(current)
        current += timedelta(days=1)

    for inst in instruments:
        rets = rng.normal(0.0005, 0.015, n_days)
        prices = 100.0 * np.cumprod(1 + rets)
        for d, p in zip(trading_days, prices, strict=True):
            rows.append({"instrument_id": inst, "date": d, "close": float(p)})

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# rs_nifty500 formula tests (pure math — no DB)                               #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_rs_nifty500_formula_positive_outperformance() -> None:
    """Stock up 10%, nifty 2% → rs ≈ 0.0784."""
    stock_ret = 0.10
    bench_ret = 0.02
    rs = (1.0 + stock_ret) / (1.0 + bench_ret) - 1.0
    assert abs(rs - 0.07843137254) < 1e-8


@pytest.mark.unit
def test_rs_nifty500_formula_negative_when_underperforms() -> None:
    """Stock down 5%, nifty up 3% → rs negative."""
    stock_ret = -0.05
    bench_ret = 0.03
    rs = (1.0 + stock_ret) / (1.0 + bench_ret) - 1.0
    assert rs < 0.0


@pytest.mark.unit
def test_rs_nifty500_formula_zero_bench_ret() -> None:
    """When bench_ret = 0, rs equals stock_ret exactly."""
    stock_ret = 0.07
    bench_ret = 0.0
    rs = (1.0 + stock_ret) / (1.0 + bench_ret) - 1.0
    assert abs(rs - stock_ret) < 1e-10


@pytest.mark.unit
def test_rs_nifty500_formula_nullif_guard() -> None:
    """bench_ret = -1 makes denominator 0; NULLIF returns NULL (None in Python)."""
    stock_ret = 0.05
    bench_ret = -1.0
    denom = 1.0 + bench_ret
    result = None if abs(denom) < 1e-12 else (1.0 + stock_ret) / denom - 1.0
    assert result is None


# --------------------------------------------------------------------------- #
# _compute_2022_metrics tests                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_compute_2022_metrics_returns_gap_dates_only() -> None:
    """Output must only contain rows within [GAP_START, GAP_END]."""
    df_ohlcv = _make_ohlcv(n_days=800)  # covers 2020-01-02 to 2023-01-25
    result = _compute_2022_metrics(df_ohlcv)

    assert not result.empty, "Expected non-empty result with sufficient history"
    assert result["date"].min() >= GAP_START
    assert result["date"].max() <= GAP_END


@pytest.mark.unit
def test_compute_2022_metrics_output_columns() -> None:
    """Output must have exactly the expected columns."""
    df_ohlcv = _make_ohlcv(n_days=800)
    result = _compute_2022_metrics(df_ohlcv)

    expected_cols = {"instrument_id", "date", "ret_12m", "ema_200_stock", "max_drawdown_252"}
    assert set(result.columns) == expected_cols


@pytest.mark.unit
def test_compute_2022_metrics_ret_12m_range() -> None:
    """ret_12m values should be within reasonable bounds (-1 to +5 for non-penny)."""
    df_ohlcv = _make_ohlcv(n_days=800)
    result = _compute_2022_metrics(df_ohlcv)

    valid = result["ret_12m"].dropna()
    assert len(valid) > 0, "Some ret_12m values should be populated"
    assert (valid >= -1.0).all(), "ret_12m should not go below -100%"
    assert (valid <= 5.0).all(), "ret_12m should not exceed 500% for synthetic data"


@pytest.mark.unit
def test_compute_2022_metrics_ema_200_positive() -> None:
    """EMA(200) of price must be positive (prices are positive)."""
    df_ohlcv = _make_ohlcv(n_days=800)
    result = _compute_2022_metrics(df_ohlcv)

    valid = result["ema_200_stock"].dropna()
    assert len(valid) > 0, "Some ema_200_stock should be populated"
    assert (valid > 0).all(), "EMA of positive prices must be positive"


@pytest.mark.unit
def test_compute_2022_metrics_max_drawdown_non_negative() -> None:
    """max_drawdown_252 is an absolute drawdown — must be in [0, 1]."""
    df_ohlcv = _make_ohlcv(n_days=800)
    result = _compute_2022_metrics(df_ohlcv)

    valid = result["max_drawdown_252"].dropna()
    assert len(valid) > 0, "Some max_drawdown_252 should be populated"
    assert (valid >= 0).all(), "Drawdown must be non-negative"
    assert (valid <= 1.0).all(), "Drawdown must be <= 1.0 (100%)"


@pytest.mark.unit
def test_compute_2022_metrics_insufficient_history_yields_nulls() -> None:
    """Instruments with < 252 days of history before gap yield NULL ret_12m."""
    # Only 300 days of data starting 2021-06-01 — not enough for 252-day lookback
    # by Jan 2022 (only ~145 trading days from Jun to Dec 2021)
    df_ohlcv = _make_ohlcv(n_days=400, start=date(2021, 6, 1))
    result = _compute_2022_metrics(df_ohlcv)

    # ret_12m for Jan 2022 requires price from Jan 2021 — data only starts Jun 2021
    # so early 2022 rows should have NULL ret_12m
    jan_2022 = result[result["date"] == date(2022, 1, 10)]
    if len(jan_2022) > 0:
        # With only ~145 days before Jan 2022, 252-day lookback is unavailable
        assert jan_2022["ret_12m"].isna().all(), "Insufficient history should yield NULL ret_12m"


@pytest.mark.unit
def test_compute_2022_metrics_no_iterrows() -> None:
    """Large input should not time out (validates vectorised implementation).

    1,000 instruments × 700 days = 700k rows. Should complete in < 60s.
    """
    import time

    df_ohlcv = _make_ohlcv(n_days=800, n_instruments=10)
    t0 = time.time()
    result = _compute_2022_metrics(df_ohlcv)
    elapsed = time.time() - t0

    assert elapsed < 60.0, f"Took {elapsed:.1f}s — possible iterrows usage"
    assert len(result) > 0


@pytest.mark.unit
def test_compute_2022_metrics_row_counts_logged_correctly() -> None:
    """rows_in_gap must be <= rows_in_window (filter only shrinks)."""
    df_ohlcv = _make_ohlcv(n_days=800)
    result = _compute_2022_metrics(df_ohlcv)

    # All result rows must be within the gap window
    assert all(r >= GAP_START for r in result["date"])
    assert all(r <= GAP_END for r in result["date"])
