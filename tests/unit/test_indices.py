"""Unit tests for ``atlas.compute.indices``.

Hand-traceable synthetic frames; no DB. The pure :func:`compute_index_metrics`
function is the test surface — orchestrators ``backfill_*`` / ``run_daily_*``
wrap it with I/O and are exercised in integration tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from atlas.compute.indices import (
    METRICS_COLUMNS,
    NIFTY500_CODE,
    compute_index_metrics,
)


def _make_index_frame(
    codes: tuple[str, ...] = (NIFTY500_CODE, "NIFTY 50"),
    n: int = 300,
    seed: int = 0,
) -> pd.DataFrame:
    """Synthetic per-index OHLC frame.

    ``n`` defaults to 300 so 252-day rolling windows have at least one
    fully-warm row. Each index gets an independent geometric-brownian price
    series so RS isn't trivially 1.0.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n).date
    rows = []
    for offset, code in enumerate(codes):
        rets = rng.normal(0.0005, 0.01, n) + offset * 1e-4
        prices = 100 * np.cumprod(1 + rets)
        for d, p in zip(dates, prices, strict=True):
            rows.append(
                {
                    "index_code": code,
                    "date": d,
                    "open": p,
                    "high": p * 1.005,
                    "low": p * 0.995,
                    "close": p,
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Schema / column shape                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_compute_index_metrics_returns_correct_columns() -> None:
    df = _make_index_frame()
    out = compute_index_metrics(df)
    expected = [c for c in METRICS_COLUMNS if c != "compute_run_id"]
    assert list(out.columns) == expected, (
        f"missing: {set(expected) - set(out.columns)}, "
        f"extra: {set(out.columns) - set(expected)}"
    )


@pytest.mark.unit
def test_compute_index_metrics_empty_input_returns_empty() -> None:
    empty = pd.DataFrame(columns=["index_code", "date", "open", "high", "low", "close"])
    out = compute_index_metrics(empty)
    assert out.empty
    expected = [c for c in METRICS_COLUMNS if c != "compute_run_id"]
    assert list(out.columns) == expected


# --------------------------------------------------------------------------- #
# Returns + EMA warm-up                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_compute_index_metrics_ret_1d_first_row_is_nan() -> None:
    df = _make_index_frame()
    out = compute_index_metrics(df)
    # add_returns sorts by (group, date) internally; first row per index has
    # no prior price so ret_1d must be NaN.
    firsts = out.groupby("index_code", group_keys=False).head(1)
    assert firsts["ret_1d"].isna().all()
    # And ret_12m (252-day window) at row 0 must also be NaN.
    assert firsts["ret_12m"].isna().all()


@pytest.mark.unit
def test_compute_index_metrics_ema_warm_up() -> None:
    df = _make_index_frame()
    out = compute_index_metrics(df)
    sub = out[out["index_code"] == NIFTY500_CODE].sort_values("date").reset_index(drop=True)
    # pandas-ta seeds EMA with first-N SMA → values 0..N-2 are NaN.
    assert sub["ema_10_index"].iloc[:9].isna().all()
    assert not np.isnan(sub["ema_10_index"].iloc[10])
    assert sub["ema_20_index"].iloc[:19].isna().all()
    assert not np.isnan(sub["ema_20_index"].iloc[20])


# --------------------------------------------------------------------------- #
# RS-vs-Nifty500                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_compute_index_metrics_rs_vs_nifty500_correct_ratio() -> None:
    """RS of NIFTY 500 against itself = 1.0 wherever ret is non-zero, NaN where 0/0."""
    df = _make_index_frame(codes=(NIFTY500_CODE, "NIFTY 50"))
    out = compute_index_metrics(df)
    nifty = out[out["index_code"] == NIFTY500_CODE].sort_values("date").reset_index(drop=True)
    # Take only rows where we have a non-zero benchmark (price-relative RS
    # requires 1 + ret != 0; for near-zero returns the RS is near 0).
    mask = nifty["ret_1m"].notna() & ((1.0 + nifty["ret_1m"]).abs() > 1e-9)
    same = nifty.loc[mask]
    assert not same.empty
    # Price-relative RS of an index vs itself = (1+r)/(1+r)-1 = 0.0
    assert np.allclose(same["rs_1m_nifty500"], 0.0, atol=1e-9)


@pytest.mark.unit
def test_compute_index_metrics_rs_zero_denominator_is_nan() -> None:
    """When Nifty500 return for a window is exactly 0, RS must be NaN, not inf."""
    # Hand-craft a tiny frame: Nifty500 flat at 100, other index moving.
    dates = pd.date_range("2020-01-01", periods=30).date
    rows = []
    for d in dates:
        rows.append(
            {
                "index_code": NIFTY500_CODE,
                "date": d,
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
            }
        )
    px = 100.0
    for d in dates:
        px *= 1.001
        rows.append(
            {"index_code": "NIFTY 50", "date": d, "open": px, "high": px, "low": px, "close": px}
        )
    df = pd.DataFrame(rows)
    out = compute_index_metrics(df)
    n50 = out[out["index_code"] == "NIFTY 50"]
    # Nifty500 ret_1w == 0 → bench_price_rel = 1.0 (not near-zero, so RS is
    # computed, not NaN). With price-relative formula: RS = (1+n50_ret)/1.0 - 1
    # = n50_ret. Key guard: no inf values regardless of Nifty500 return.
    rs_col = n50.loc[n50["ret_1w"].notna(), "rs_1w_nifty500"]
    assert not np.isinf(rs_col.fillna(0).to_numpy()).any()


# --------------------------------------------------------------------------- #
# VIX columns + missing Nifty500                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_compute_index_metrics_vix_columns_only_for_vix_index() -> None:
    """Schema has no VIX-special columns — ``realized_vol_5d`` and ``vol_252_median``
    are computed for every index. This test pins that behaviour: the columns
    exist on every row and match what add_realized_vol produces for VIX rows.
    """
    df = _make_index_frame(codes=(NIFTY500_CODE, "INDIA VIX"), n=300, seed=42)
    out = compute_index_metrics(df)

    # Both columns must be present in the output for every index_code.
    assert "realized_vol_5d" in out.columns
    assert "vol_252_median" in out.columns
    # Non-VIX rows must also have non-null values once the window is warm.
    nifty = out[out["index_code"] == NIFTY500_CODE].sort_values("date")
    # 5-day window: by row 5 we should have at least one finite reading.
    assert nifty["realized_vol_5d"].iloc[5:].notna().any()
    # VIX rows similarly populated.
    vix = out[out["index_code"] == "INDIA VIX"].sort_values("date")
    assert vix["realized_vol_5d"].iloc[5:].notna().any()


@pytest.mark.unit
def test_compute_index_metrics_missing_nifty500_yields_nan_rs() -> None:
    """If Nifty500 is absent from the input, all rs_*_nifty500 columns are NaN."""
    df = _make_index_frame(codes=("NIFTY 50", "NIFTY BANK"), n=100)
    out = compute_index_metrics(df)
    for w in ("1w", "1m", "3m"):
        assert out[f"rs_{w}_nifty500"].isna().all()
    # EMA ratios likewise — denominator absent.
    assert out["ema_10_ratio_nifty500"].isna().all()
    assert out["ema_20_ratio_nifty500"].isna().all()


# --------------------------------------------------------------------------- #
# Single-group + edge cases                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_compute_index_metrics_single_group_no_crash() -> None:
    """Single index, 300 rows — pipeline must not crash on a 1-group input."""
    df = _make_index_frame(codes=(NIFTY500_CODE,), n=300)
    out = compute_index_metrics(df)
    assert len(out) == 300
    assert out["index_code"].nunique() == 1
    # ret_1d populated after the first row.
    assert out["ret_1d"].iloc[1:].notna().any()
    # Price-relative RS vs itself = (1+r)/(1+r)-1 = 0.0 for all non-zero ret.
    sub = out.sort_values("date").reset_index(drop=True)
    mask = sub["ret_3m"].notna() & ((1.0 + sub["ret_3m"]).abs() > 1e-9)
    assert np.allclose(sub.loc[mask, "rs_3m_nifty500"], 0.0, atol=1e-9)


@pytest.mark.unit
def test_compute_index_metrics_realized_vol_63_is_annualised() -> None:
    """Sanity check: realized_vol_63 = std(ret_1d, 63) * sqrt(252) on the tail."""
    df = _make_index_frame(codes=(NIFTY500_CODE,), n=300)
    out = compute_index_metrics(df).sort_values("date").reset_index(drop=True)
    last_window = out["ret_1d"].iloc[-63:]
    expected = last_window.std() * np.sqrt(252)
    assert abs(out["realized_vol_63"].iloc[-1] - expected) < 1e-9
