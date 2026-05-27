"""TDD tests for new sector columns: rs_1w/1m/6m/12m, pct_above_ema20/200, pct_52wh, hhi.

Tests are pure unit tests — no DB. All four new functions accept pre-pulled DataFrames.

Function signatures:
    compute_rs_windows(sector_returns, nifty500_returns) -> DataFrame
        cols: sector_name, date, rs_1w, rs_1m, rs_6m, rs_12m

    compute_breadth_per_sector(constituents_metrics) -> DataFrame
        cols: sector_name, date, pct_above_ema20, pct_above_ema200

    compute_52wh_per_sector(constituents_metrics) -> DataFrame
        cols: sector_name, date, pct_52wh

    compute_concentration_per_sector(mcap_history) -> DataFrame
        cols: sector_name, date, hhi
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from atlas.compute.sectors import (
    compute_52wh_per_sector,
    compute_breadth_per_sector,
    compute_concentration_per_sector,
    compute_rs_windows,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_DATE = date(2024, 6, 1)


def _sector_returns_frame() -> pd.DataFrame:
    """Bottom-up sector returns: two sectors on one date."""
    return pd.DataFrame(
        [
            {
                "sector_name": "Bank",
                "date": _DATE,
                "bottomup_ret_1w": 0.03,
                "bottomup_ret_1m": 0.06,
                "bottomup_ret_6m": 0.12,
                "bottomup_ret_12m": 0.18,
            },
            {
                "sector_name": "Tech",
                "date": _DATE,
                "bottomup_ret_1w": -0.01,
                "bottomup_ret_1m": -0.02,
                "bottomup_ret_6m": -0.05,
                "bottomup_ret_12m": -0.10,
            },
        ]
    )


def _nifty500_returns_frame() -> pd.DataFrame:
    """Nifty 500 returns for the same date."""
    return pd.DataFrame(
        [
            {
                "date": _DATE,
                "_n500_ret_1w": 0.01,
                "_n500_ret_1m": 0.02,
                "_n500_ret_6m": 0.04,
                "_n500_ret_12m": 0.08,
            }
        ]
    )


def _constituents_frame() -> pd.DataFrame:
    """Constituent stock metrics: Bank x 3, Tech x 2."""
    return pd.DataFrame(
        [
            # Bank — big stock above ema20, below ema200, near 52wh
            {
                "instrument_id": "iid_big_bank",
                "date": _DATE,
                "sector_name": "Bank",
                "ema_20_ratio": 1.05,  # above ema20
                "extension_pct": -0.03,  # below ema200
                "close_approx": 97.0,
                "rolling_max_252": 99.0,  # within 5%
                "avg_volume_20": 1_000_000,
            },
            # Bank — mid stock below ema20, above ema200, far from 52wh
            {
                "instrument_id": "iid_mid_bank",
                "date": _DATE,
                "sector_name": "Bank",
                "ema_20_ratio": 0.98,  # below ema20
                "extension_pct": 0.05,  # above ema200
                "close_approx": 50.0,
                "rolling_max_252": 80.0,  # more than 5% below
                "avg_volume_20": 100_000,
            },
            # Bank — small stock below both EMAs, near 52wh
            {
                "instrument_id": "iid_small_bank",
                "date": _DATE,
                "sector_name": "Bank",
                "ema_20_ratio": 0.92,  # below ema20
                "extension_pct": -0.10,  # below ema200
                "close_approx": 22.0,
                "rolling_max_252": 23.0,  # within 5%: 22/23 = 0.957 > 0.95
                "avg_volume_20": 10_000,
            },
            # Tech — large stock above ema20, above ema200, at 52wh
            {
                "instrument_id": "iid_big_tech",
                "date": _DATE,
                "sector_name": "Tech",
                "ema_20_ratio": 1.10,  # above ema20
                "extension_pct": 0.15,  # above ema200
                "close_approx": 115.0,
                "rolling_max_252": 115.0,  # at 52wh
                "avg_volume_20": 500_000,
            },
            # Tech — small stock below ema20, below ema200, far from 52wh
            {
                "instrument_id": "iid_small_tech",
                "date": _DATE,
                "sector_name": "Tech",
                "ema_20_ratio": 0.85,  # below ema20
                "extension_pct": -0.20,  # below ema200
                "close_approx": 40.0,
                "rolling_max_252": 70.0,  # far below 52wh
                "avg_volume_20": 50_000,
            },
        ]
    )


# ---------------------------------------------------------------------------
# compute_rs_windows
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_rs_windows_returns_correct_columns() -> None:
    """Output must have sector_name, date, rs_1w, rs_1m, rs_6m, rs_12m."""
    sector_ret = _sector_returns_frame()
    n500 = _nifty500_returns_frame()
    out = compute_rs_windows(sector_ret, n500)
    for col in ("sector_name", "date", "rs_1w", "rs_1m", "rs_6m", "rs_12m"):
        assert col in out.columns, f"missing column: {col}"


@pytest.mark.unit
def test_compute_rs_windows_bank_rs_1w_hand_computed() -> None:
    """Bank rs_1w = bottomup_ret_1w - n500_ret_1w = 0.03 - 0.01 = 0.02."""
    out = compute_rs_windows(_sector_returns_frame(), _nifty500_returns_frame())
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["rs_1w"] == pytest.approx(0.03 - 0.01, abs=1e-8)


@pytest.mark.unit
def test_compute_rs_windows_tech_rs_12m_hand_computed() -> None:
    """Tech rs_12m = -0.10 - 0.08 = -0.18."""
    out = compute_rs_windows(_sector_returns_frame(), _nifty500_returns_frame())
    tech = out[out["sector_name"] == "Tech"].iloc[0]
    assert tech["rs_12m"] == pytest.approx(-0.10 - 0.08, abs=1e-8)


@pytest.mark.unit
def test_compute_rs_windows_null_n500_produces_null() -> None:
    """Missing Nifty500 return for a date → NaN RS for all windows."""
    sector_ret = _sector_returns_frame()
    # n500 has no row for _DATE
    n500_empty = pd.DataFrame(
        columns=["date", "_n500_ret_1w", "_n500_ret_1m", "_n500_ret_6m", "_n500_ret_12m"]
    )
    out = compute_rs_windows(sector_ret, n500_empty)
    for col in ("rs_1w", "rs_1m", "rs_6m", "rs_12m"):
        assert out[col].isna().all(), f"expected NaN in {col} when n500 is missing"


@pytest.mark.unit
def test_compute_rs_windows_empty_sector_returns_empty() -> None:
    empty_sector = pd.DataFrame(
        columns=[
            "sector_name",
            "date",
            "bottomup_ret_1w",
            "bottomup_ret_1m",
            "bottomup_ret_6m",
            "bottomup_ret_12m",
        ]
    )
    out = compute_rs_windows(empty_sector, _nifty500_returns_frame())
    assert out.empty


@pytest.mark.unit
def test_compute_rs_windows_two_dates_correct() -> None:
    """Multi-date frame: RS computed per date, not using wrong n500 row."""
    d1 = date(2024, 1, 1)
    d2 = date(2024, 2, 1)
    sector_ret = pd.DataFrame(
        [
            {
                "sector_name": "Bank",
                "date": d1,
                "bottomup_ret_1w": 0.05,
                "bottomup_ret_1m": 0.10,
                "bottomup_ret_6m": 0.20,
                "bottomup_ret_12m": 0.30,
            },
            {
                "sector_name": "Bank",
                "date": d2,
                "bottomup_ret_1w": 0.02,
                "bottomup_ret_1m": 0.04,
                "bottomup_ret_6m": 0.08,
                "bottomup_ret_12m": 0.12,
            },
        ]
    )
    n500 = pd.DataFrame(
        [
            {
                "date": d1,
                "_n500_ret_1w": 0.01,
                "_n500_ret_1m": 0.02,
                "_n500_ret_6m": 0.04,
                "_n500_ret_12m": 0.06,
            },
            {
                "date": d2,
                "_n500_ret_1w": 0.00,
                "_n500_ret_1m": 0.00,
                "_n500_ret_6m": 0.00,
                "_n500_ret_12m": 0.00,
            },
        ]
    )
    out = compute_rs_windows(sector_ret, n500)
    row_d1 = out[(out["sector_name"] == "Bank") & (out["date"] == d1)].iloc[0]
    row_d2 = out[(out["sector_name"] == "Bank") & (out["date"] == d2)].iloc[0]
    assert row_d1["rs_1w"] == pytest.approx(0.04, abs=1e-8)
    assert row_d2["rs_1w"] == pytest.approx(0.02, abs=1e-8)


# ---------------------------------------------------------------------------
# compute_breadth_per_sector
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_breadth_returns_correct_columns() -> None:
    out = compute_breadth_per_sector(_constituents_frame())
    for col in ("sector_name", "date", "pct_above_ema20", "pct_above_ema200"):
        assert col in out.columns, f"missing column: {col}"


@pytest.mark.unit
def test_compute_breadth_bank_pct_above_ema20() -> None:
    """Bank: only iid_big_bank has ema_20_ratio > 1 → 1/3."""
    out = compute_breadth_per_sector(_constituents_frame())
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["pct_above_ema20"] == pytest.approx(1 / 3, abs=1e-8)


@pytest.mark.unit
def test_compute_breadth_bank_pct_above_ema200() -> None:
    """Bank: only iid_mid_bank has extension_pct > 0 → 1/3."""
    out = compute_breadth_per_sector(_constituents_frame())
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["pct_above_ema200"] == pytest.approx(1 / 3, abs=1e-8)


@pytest.mark.unit
def test_compute_breadth_tech_pct_above_ema20() -> None:
    """Tech: only iid_big_tech has ema_20_ratio > 1 → 1/2."""
    out = compute_breadth_per_sector(_constituents_frame())
    tech = out[out["sector_name"] == "Tech"].iloc[0]
    assert tech["pct_above_ema20"] == pytest.approx(0.5, abs=1e-8)


@pytest.mark.unit
def test_compute_breadth_tech_pct_above_ema200() -> None:
    """Tech: only iid_big_tech has extension_pct > 0 → 1/2."""
    out = compute_breadth_per_sector(_constituents_frame())
    tech = out[out["sector_name"] == "Tech"].iloc[0]
    assert tech["pct_above_ema200"] == pytest.approx(0.5, abs=1e-8)


@pytest.mark.unit
def test_compute_breadth_null_ema20_ratio_excluded() -> None:
    """Stocks with NULL ema_20_ratio excluded from both numerator and denominator."""
    df = _constituents_frame().copy()
    df.loc[df["instrument_id"] == "iid_big_bank", "ema_20_ratio"] = np.nan
    out = compute_breadth_per_sector(df)
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    # Only 2 stocks with valid ema_20_ratio; 0 above threshold → 0/2
    assert bank["pct_above_ema20"] == pytest.approx(0.0, abs=1e-8)


@pytest.mark.unit
def test_compute_breadth_empty_input_returns_empty() -> None:
    empty = pd.DataFrame(
        columns=[
            "instrument_id",
            "date",
            "sector_name",
            "ema_20_ratio",
            "extension_pct",
            "close_approx",
            "rolling_max_252",
            "avg_volume_20",
        ]
    )
    out = compute_breadth_per_sector(empty)
    assert out.empty


# ---------------------------------------------------------------------------
# compute_52wh_per_sector
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_52wh_returns_correct_columns() -> None:
    out = compute_52wh_per_sector(_constituents_frame())
    for col in ("sector_name", "date", "pct_52wh"):
        assert col in out.columns, f"missing column: {col}"


@pytest.mark.unit
def test_compute_52wh_bank_hand_computed() -> None:
    """Bank:
    - iid_big_bank: 97/99 = 0.9798 > 0.95 → within 5% → YES
    - iid_mid_bank: 50/80 = 0.625 < 0.95 → NO
    - iid_small_bank: 22/23 = 0.9565 > 0.95 → YES
    → 2/3 = 0.667
    """
    out = compute_52wh_per_sector(_constituents_frame())
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["pct_52wh"] == pytest.approx(2 / 3, abs=1e-8)


@pytest.mark.unit
def test_compute_52wh_tech_hand_computed() -> None:
    """Tech:
    - iid_big_tech: 115/115 = 1.0 > 0.95 → YES
    - iid_small_tech: 40/70 = 0.571 < 0.95 → NO
    → 1/2 = 0.5
    """
    out = compute_52wh_per_sector(_constituents_frame())
    tech = out[out["sector_name"] == "Tech"].iloc[0]
    assert tech["pct_52wh"] == pytest.approx(0.5, abs=1e-8)


@pytest.mark.unit
def test_compute_52wh_null_rolling_max_excluded() -> None:
    """Stocks with NULL rolling_max_252 excluded from denominator."""
    df = _constituents_frame().copy()
    df.loc[df["instrument_id"] == "iid_mid_bank", "rolling_max_252"] = np.nan
    out = compute_52wh_per_sector(df)
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    # Only big_bank and small_bank have valid rolling_max; both within 5% → 2/2 = 1.0
    assert bank["pct_52wh"] == pytest.approx(1.0, abs=1e-8)


@pytest.mark.unit
def test_compute_52wh_at_exactly_5pct_below_is_excluded() -> None:
    """A stock at exactly 95% of the 52wh (ratio == 0.95) is NOT within 5% — boundary check."""
    df = _constituents_frame().copy()
    # Set big_bank close_approx to exactly 95% of rolling_max
    df.loc[df["instrument_id"] == "iid_big_bank", "close_approx"] = 0.95 * 99.0
    df.loc[df["instrument_id"] == "iid_big_bank", "rolling_max_252"] = 99.0
    out = compute_52wh_per_sector(df)
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    # big_bank ratio == 0.95, only small_bank (22/23=0.957) qualifies → 1/3
    assert bank["pct_52wh"] == pytest.approx(1 / 3, abs=1e-8)


@pytest.mark.unit
def test_compute_52wh_empty_input_returns_empty() -> None:
    empty = pd.DataFrame(
        columns=["instrument_id", "date", "sector_name", "close_approx", "rolling_max_252"]
    )
    out = compute_52wh_per_sector(empty)
    assert out.empty


# ---------------------------------------------------------------------------
# compute_concentration_per_sector (HHI)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_concentration_returns_correct_columns() -> None:
    out = compute_concentration_per_sector(_constituents_frame())
    for col in ("sector_name", "date", "hhi"):
        assert col in out.columns, f"missing column: {col}"


@pytest.mark.unit
def test_compute_concentration_hhi_range() -> None:
    """HHI must be in [1/n, 1] for any non-degenerate sector."""
    out = compute_concentration_per_sector(_constituents_frame())
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    tech = out[out["sector_name"] == "Tech"].iloc[0]
    # Bank: 3 stocks → HHI ∈ [1/3, 1]
    assert 1 / 3 <= bank["hhi"] <= 1.0
    # Tech: 2 stocks → HHI ∈ [1/2, 1]
    assert 0.5 <= tech["hhi"] <= 1.0


@pytest.mark.unit
def test_compute_concentration_bank_hhi_hand_computed() -> None:
    """Bank HHI by traded value:
    traded_value = avg_volume_20 * close_approx:
    - big_bank: 1_000_000 * 97.0 = 97_000_000
    - mid_bank: 100_000 * 50.0 = 5_000_000
    - small_bank: 10_000 * 22.0 = 220_000
    total = 102_220_000
    shares: s1=97M/102.22M=0.9489, s2=5M/102.22M=0.04893, s3=220K/102.22M=0.002152
    HHI = s1^2 + s2^2 + s3^2
    """
    out = compute_concentration_per_sector(_constituents_frame())
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    # Hand-compute
    tv1 = 1_000_000 * 97.0
    tv2 = 100_000 * 50.0
    tv3 = 10_000 * 22.0
    total = tv1 + tv2 + tv3
    s1, s2, s3 = tv1 / total, tv2 / total, tv3 / total
    expected_hhi = s1**2 + s2**2 + s3**2
    assert bank["hhi"] == pytest.approx(expected_hhi, rel=1e-6)


@pytest.mark.unit
def test_compute_concentration_monopoly_case() -> None:
    """Single stock in a sector → HHI = 1.0."""
    df = pd.DataFrame(
        [
            {
                "instrument_id": "solo",
                "date": _DATE,
                "sector_name": "Solo",
                "ema_20_ratio": 1.0,
                "extension_pct": 0.0,
                "close_approx": 100.0,
                "rolling_max_252": 100.0,
                "avg_volume_20": 50_000,
            }
        ]
    )
    out = compute_concentration_per_sector(df)
    solo = out[out["sector_name"] == "Solo"].iloc[0]
    assert solo["hhi"] == pytest.approx(1.0, abs=1e-8)


@pytest.mark.unit
def test_compute_concentration_equal_weight_case() -> None:
    """Two stocks with identical traded value → HHI = 0.5."""
    df = pd.DataFrame(
        [
            {
                "instrument_id": "a",
                "date": _DATE,
                "sector_name": "Equal",
                "ema_20_ratio": 1.0,
                "extension_pct": 0.0,
                "close_approx": 100.0,
                "rolling_max_252": 100.0,
                "avg_volume_20": 100_000,
            },
            {
                "instrument_id": "b",
                "date": _DATE,
                "sector_name": "Equal",
                "ema_20_ratio": 1.0,
                "extension_pct": 0.0,
                "close_approx": 100.0,
                "rolling_max_252": 100.0,
                "avg_volume_20": 100_000,
            },
        ]
    )
    out = compute_concentration_per_sector(df)
    eq = out[out["sector_name"] == "Equal"].iloc[0]
    assert eq["hhi"] == pytest.approx(0.5, abs=1e-8)


@pytest.mark.unit
def test_compute_concentration_null_traded_value_excluded() -> None:
    """Stocks with NULL close_approx are excluded from HHI computation."""
    df = _constituents_frame().copy()
    df.loc[df["instrument_id"] == "iid_mid_bank", "close_approx"] = np.nan
    out = compute_concentration_per_sector(df)
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    # Only big_bank and small_bank contribute
    tv1 = 1_000_000 * 97.0
    tv3 = 10_000 * 22.0
    total = tv1 + tv3
    s1, s3 = tv1 / total, tv3 / total
    expected_hhi = s1**2 + s3**2
    assert bank["hhi"] == pytest.approx(expected_hhi, rel=1e-6)


@pytest.mark.unit
def test_compute_concentration_empty_input_returns_empty() -> None:
    empty = pd.DataFrame(
        columns=["instrument_id", "date", "sector_name", "close_approx", "avg_volume_20"]
    )
    out = compute_concentration_per_sector(empty)
    assert out.empty
