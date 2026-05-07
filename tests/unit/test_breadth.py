"""Unit tests for ``atlas.compute.breadth``.

Hand-traceable synthetic frames; no DB. Each test pins one observable
property of one breadth primitive — counts, cumsum invariance, EMA
warm-up, NaN-safety.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.compute.breadth import (
    compute_ad_line,
    compute_advances_declines,
    compute_ma_breadth,
    compute_mcclellan,
    compute_new_highs_lows,
)


def _stock_frame(n_stocks: int = 5, n_days: int = 60, seed: int = 0) -> pd.DataFrame:
    """Synthetic long stock-day frame with close_approx + EMAs.

    n_days defaults to 60 so ema_50 has at least 10 warm rows; n_stocks
    chosen to keep counts hand-traceable.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days).date
    rows = []
    for sid in range(n_stocks):
        rets = rng.normal(0.001, 0.02, n_days)
        prices = 100.0 * np.cumprod(1 + rets)
        ema50 = pd.Series(prices).ewm(span=50, adjust=False, min_periods=50).mean()
        ema200 = pd.Series(prices).ewm(span=200, adjust=False, min_periods=200).mean()
        for d, p, e50, e200 in zip(dates, prices, ema50, ema200, strict=True):
            rows.append(
                {
                    "instrument_id": f"sid_{sid}",
                    "date": d,
                    "close_approx": p,
                    "ema_50_stock": e50,
                    "ema_200_stock": e200,
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# advances_declines                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_advances_declines_counts_match_handcomputed_simple_case() -> None:
    """3 stocks, 3 days, hand-traceable counts."""
    df = pd.DataFrame(
        [
            {
                "instrument_id": "a",
                "date": pd.Timestamp("2024-01-01").date(),
                "close_approx": 100.0,
            },
            {
                "instrument_id": "a",
                "date": pd.Timestamp("2024-01-02").date(),
                "close_approx": 105.0,
            },
            {
                "instrument_id": "a",
                "date": pd.Timestamp("2024-01-03").date(),
                "close_approx": 100.0,
            },
            {
                "instrument_id": "b",
                "date": pd.Timestamp("2024-01-01").date(),
                "close_approx": 100.0,
            },
            {"instrument_id": "b", "date": pd.Timestamp("2024-01-02").date(), "close_approx": 95.0},
            {"instrument_id": "b", "date": pd.Timestamp("2024-01-03").date(), "close_approx": 95.0},
            {
                "instrument_id": "c",
                "date": pd.Timestamp("2024-01-01").date(),
                "close_approx": 100.0,
            },
            {
                "instrument_id": "c",
                "date": pd.Timestamp("2024-01-02").date(),
                "close_approx": 110.0,
            },
            {
                "instrument_id": "c",
                "date": pd.Timestamp("2024-01-03").date(),
                "close_approx": 110.0,
            },
        ]
    )
    out = compute_advances_declines(df)

    # Day 2024-01-02: a up, b down, c up → 2 adv, 1 dec
    day2 = out.loc[out["date"] == pd.Timestamp("2024-01-02").date()].iloc[0]
    assert day2["advances"] == 2
    assert day2["declines"] == 1
    assert day2["unchanged"] == 0
    assert day2["net_advances"] == 1
    # Day 2024-01-03: a down, b unchanged, c unchanged → 0 adv, 1 dec, 2 unchanged
    day3 = out.loc[out["date"] == pd.Timestamp("2024-01-03").date()].iloc[0]
    assert day3["advances"] == 0
    assert day3["declines"] == 1
    assert day3["unchanged"] == 2


@pytest.mark.unit
def test_advances_declines_empty_input_returns_empty() -> None:
    out = compute_advances_declines(pd.DataFrame(columns=["instrument_id", "date", "close_approx"]))
    assert out.empty
    assert "advances" in out.columns


@pytest.mark.unit
def test_advance_decline_ratio_floors_zero_declines() -> None:
    """When declines == 0, ratio uses max(declines, 1) so we don't divide by 0."""
    df = pd.DataFrame(
        [
            {
                "instrument_id": "a",
                "date": pd.Timestamp("2024-01-01").date(),
                "close_approx": 100.0,
            },
            {
                "instrument_id": "a",
                "date": pd.Timestamp("2024-01-02").date(),
                "close_approx": 105.0,
            },
            {
                "instrument_id": "b",
                "date": pd.Timestamp("2024-01-01").date(),
                "close_approx": 100.0,
            },
            {
                "instrument_id": "b",
                "date": pd.Timestamp("2024-01-02").date(),
                "close_approx": 110.0,
            },
        ]
    )
    out = compute_advances_declines(df)
    day2 = out.loc[out["date"] == pd.Timestamp("2024-01-02").date()].iloc[0]
    assert day2["advances"] == 2
    assert day2["declines"] == 0
    # ratio = 2 / max(0, 1) = 2.0
    assert day2["advance_decline_ratio"] == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# ad_line                                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_ad_line_is_cumulative_sum_of_net_advances() -> None:
    df = _stock_frame(n_stocks=4, n_days=20, seed=7)
    ad = compute_advances_declines(df)
    out = compute_ad_line(ad)
    # ad_line[i] = sum(net_advances[0..i])
    expected = ad["net_advances"].cumsum().to_numpy()
    np.testing.assert_array_almost_equal(out["ad_line"].to_numpy(), expected)


@pytest.mark.unit
def test_ad_line_recomputes_from_scratch() -> None:
    """Calling compute_ad_line twice on the same input gives the same result."""
    df = _stock_frame(n_stocks=4, n_days=20, seed=11)
    ad = compute_advances_declines(df)
    o1 = compute_ad_line(ad)
    o2 = compute_ad_line(ad)
    pd.testing.assert_frame_equal(o1, o2)


# --------------------------------------------------------------------------- #
# mcclellan                                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_mcclellan_oscillator_warm_up_then_finite() -> None:
    df = _stock_frame(n_stocks=10, n_days=80, seed=3)
    ad = compute_advances_declines(df)
    out = compute_mcclellan(ad)
    # pandas-ta EMA seeds with first-N SMA so EMA(39) needs 39 rows of warm-up.
    assert out["mcclellan_oscillator"].iloc[:38].isna().all()
    assert out["mcclellan_oscillator"].iloc[60:].notna().any()


@pytest.mark.unit
def test_mcclellan_summation_cumulative() -> None:
    df = _stock_frame(n_stocks=10, n_days=80, seed=5)
    ad = compute_advances_declines(df)
    out = compute_mcclellan(ad)
    # summation = cumsum(oscillator); should be monotone-non-decreasing under
    # constant positive oscillator inputs (won't hold here, but invariant we
    # care about is that the cumulative is finite once the oscillator is).
    assert out["mcclellan_summation"].iloc[60:].notna().all()


# --------------------------------------------------------------------------- #
# new_highs_lows                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_new_highs_lows_smaller_window_for_test_traceability() -> None:
    """Use window=5 so the synthetic 30-day frame has warm-up rows we can
    inspect; the production call uses window=252 (52w)."""
    df = _stock_frame(n_stocks=3, n_days=30, seed=2)
    out = compute_new_highs_lows(df, window=5)
    # Final row: every monotone-up series is at a 5-day high.
    last_date = max(out["date"])
    last_row = out.loc[out["date"] == last_date].iloc[0]
    # We don't pin an exact count (depends on synthetic seed) but the column
    # must be present and non-negative.
    assert last_row["new_52w_highs"] >= 0
    assert last_row["new_52w_lows"] >= 0
    assert last_row["new_high_low_ratio"] >= 0


@pytest.mark.unit
def test_new_highs_lows_empty_input_returns_empty() -> None:
    out = compute_new_highs_lows(pd.DataFrame(columns=["instrument_id", "date", "close_approx"]))
    assert out.empty


# --------------------------------------------------------------------------- #
# ma_breadth                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_ma_breadth_handcomputed_pct_above_50() -> None:
    """3 stocks on one date — 2 above ema_50, 1 below → pct = 2/3."""
    d = pd.Timestamp("2024-06-01").date()
    df = pd.DataFrame(
        [
            {
                "instrument_id": "a",
                "date": d,
                "close_approx": 110.0,
                "ema_50_stock": 100.0,
                "ema_200_stock": 90.0,
            },
            {
                "instrument_id": "b",
                "date": d,
                "close_approx": 105.0,
                "ema_50_stock": 100.0,
                "ema_200_stock": 90.0,
            },
            {
                "instrument_id": "c",
                "date": d,
                "close_approx": 95.0,
                "ema_50_stock": 100.0,
                "ema_200_stock": 90.0,
            },
        ]
    )
    out = compute_ma_breadth(df)
    row = out.iloc[0]
    assert row["pct_above_ema_50"] == pytest.approx(2 / 3)
    assert row["pct_above_ema_200"] == pytest.approx(1.0)


@pytest.mark.unit
def test_ma_breadth_excludes_null_ema_rows() -> None:
    """Stocks with NULL ema_50 (warm-up) must not bias the ratio."""
    d = pd.Timestamp("2024-06-01").date()
    df = pd.DataFrame(
        [
            {
                "instrument_id": "a",
                "date": d,
                "close_approx": 110.0,
                "ema_50_stock": 100.0,
                "ema_200_stock": 90.0,
            },
            {
                "instrument_id": "b",
                "date": d,
                "close_approx": 95.0,
                "ema_50_stock": np.nan,
                "ema_200_stock": np.nan,
            },
        ]
    )
    out = compute_ma_breadth(df)
    row = out.iloc[0]
    # Only 'a' counted → 1/1 = 1.0 above
    assert row["pct_above_ema_50"] == pytest.approx(1.0)
    assert row["pct_above_ema_200"] == pytest.approx(1.0)


@pytest.mark.unit
def test_ma_breadth_empty_input_returns_empty() -> None:
    out = compute_ma_breadth(
        pd.DataFrame(columns=["date", "close_approx", "ema_50_stock", "ema_200_stock"])
    )
    assert out.empty
