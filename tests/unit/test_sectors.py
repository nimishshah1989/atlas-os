"""Unit tests for ``atlas.compute.sectors``.

Synthetic stock + sector master frames; no DB. Tests cover the three pure
functions that drive Phase B output:

* compute_bottom_up_sector_metrics — weighted aggregation, equal-weight fallback
* compute_sector_breadth — participation_50, participation_rs, leadership_concentration
* compute_sector_states — RS state buckets, divergence flag, duplicate-index guard
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from atlas.compute.sectors import (
    METRICS_COLUMNS,
    STATES_COLUMNS,
    assemble_sector_metrics,
    compute_bottom_up_sector_metrics,
    compute_sector_breadth,
    compute_sector_states,
    compute_top_down_sector_metrics,
)

SECTOR_MASTER = pd.DataFrame(
    [
        {
            "sector_name": "Bank",
            "primary_nse_index": "NIFTY BANK",
            "fallback_benchmark": "NIFTY 500",
        },
        {
            "sector_name": "Power",
            "primary_nse_index": "NIFTY ENERGY",
            "fallback_benchmark": "NIFTY 500",
        },
        {
            "sector_name": "Energy",
            "primary_nse_index": "NIFTY ENERGY",
            "fallback_benchmark": "NIFTY 500",
        },
        {"sector_name": "Tech", "primary_nse_index": "NIFTY IT", "fallback_benchmark": "NIFTY 500"},
    ]
)

THRESHOLDS = {
    "sector_overweight_participation_min_pct": Decimal("50"),
    "sector_underweight_participation_max_pct": Decimal("30"),
    "sector_avoid_participation_max_pct": Decimal("25"),
}


# --------------------------------------------------------------------------- #
# bottom-up                                                                   #
# --------------------------------------------------------------------------- #


_DEFAULT_DATE = pd.Timestamp("2024-06-01").date()


def _two_sector_frame(date_d=_DEFAULT_DATE) -> pd.DataFrame:
    """Bank x 3 stocks, Tech x 2 stocks, all on a single date."""
    return pd.DataFrame(
        [
            # Bank — weighted toward large stock 'big_bank'
            {
                "instrument_id": "big_bank",
                "date": date_d,
                "sector_name": "Bank",
                "tier": "Large",
                "ema_50_stock": 100.0,
                "ema_200_stock": 90.0,
                "extension_pct": 0.10,
                "avg_volume_20": 1_000_000,
                "ret_1w": 0.02,
                "ret_1m": 0.05,
                "ret_3m": 0.10,
                "ret_6m": 0.20,
                "rs_1w_tier": 1.05,
                "rs_1m_tier": 1.10,
                "rs_3m_tier": 1.20,
                "ema_10_ratio": 1.05,
                "ema_20_ratio": 1.04,
                "rs_state": "Leader",
                "momentum_state": "Improving",
            },
            {
                "instrument_id": "mid_bank",
                "date": date_d,
                "sector_name": "Bank",
                "tier": "Mid",
                "ema_50_stock": 50.0,
                "ema_200_stock": 45.0,
                "extension_pct": 0.05,
                "avg_volume_20": 100_000,
                "ret_1w": 0.0,
                "ret_1m": 0.0,
                "ret_3m": 0.0,
                "ret_6m": 0.0,
                "rs_1w_tier": 1.0,
                "rs_1m_tier": 1.0,
                "rs_3m_tier": 1.0,
                "ema_10_ratio": 1.0,
                "ema_20_ratio": 1.0,
                "rs_state": "Average",
                "momentum_state": "Flat",
            },
            {
                "instrument_id": "small_bank",
                "date": date_d,
                "sector_name": "Bank",
                "tier": "Small",
                "ema_50_stock": 20.0,
                "ema_200_stock": 22.0,
                "extension_pct": -0.05,
                "avg_volume_20": 10_000,
                "ret_1w": -0.10,
                "ret_1m": -0.15,
                "ret_3m": -0.20,
                "ret_6m": -0.30,
                "rs_1w_tier": 0.90,
                "rs_1m_tier": 0.80,
                "rs_3m_tier": 0.70,
                "ema_10_ratio": 0.90,
                "ema_20_ratio": 0.92,
                "rs_state": "Weak",
                "momentum_state": "Deteriorating",
            },
            # Tech
            {
                "instrument_id": "big_tech",
                "date": date_d,
                "sector_name": "Tech",
                "tier": "Large",
                "ema_50_stock": 200.0,
                "ema_200_stock": 180.0,
                "extension_pct": 0.15,
                "avg_volume_20": 500_000,
                "ret_1w": 0.03,
                "ret_1m": 0.08,
                "ret_3m": 0.15,
                "ret_6m": 0.30,
                "rs_1w_tier": 1.10,
                "rs_1m_tier": 1.15,
                "rs_3m_tier": 1.30,
                "ema_10_ratio": 1.08,
                "ema_20_ratio": 1.05,
                "rs_state": "Strong",
                "momentum_state": "Improving",
            },
            {
                "instrument_id": "mid_tech",
                "date": date_d,
                "sector_name": "Tech",
                "tier": "Mid",
                "ema_50_stock": 80.0,
                "ema_200_stock": 78.0,
                "extension_pct": 0.02,
                "avg_volume_20": 50_000,
                "ret_1w": 0.01,
                "ret_1m": 0.02,
                "ret_3m": 0.05,
                "ret_6m": 0.10,
                "rs_1w_tier": 1.02,
                "rs_1m_tier": 1.03,
                "rs_3m_tier": 1.05,
                "ema_10_ratio": 1.02,
                "ema_20_ratio": 1.01,
                "rs_state": "Strong",
                "momentum_state": "Improving",
            },
        ]
    ).assign(close_approx=lambda d: d["ema_200_stock"] * (1 + d["extension_pct"]))


@pytest.mark.unit
def test_bottom_up_sector_metrics_weighted_mean_dominated_by_large_stock() -> None:
    df = _two_sector_frame()
    out = compute_bottom_up_sector_metrics(df, SECTOR_MASTER, df_nifty500_returns=None)

    bank = out[out["sector_name"] == "Bank"].iloc[0]
    # weight = avg_volume_20 * close_approx; big_bank dominates → ret_1m ≈ 0.05
    assert bank["bottomup_ret_1m"] > 0.04
    assert bank["bottomup_ret_1m"] < 0.06
    assert bank["constituent_count"] == 3


@pytest.mark.unit
def test_bottom_up_constituent_count_excludes_nan_close() -> None:
    df = _two_sector_frame()
    df.loc[df["instrument_id"] == "small_bank", "close_approx"] = np.nan
    out = compute_bottom_up_sector_metrics(df, SECTOR_MASTER)
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["constituent_count"] == 2


@pytest.mark.unit
def test_bottom_up_rs_vs_nifty500_division() -> None:
    df = _two_sector_frame()
    n500 = pd.DataFrame(
        [
            {
                "date": df["date"].iloc[0],
                "_n500_ret_1w": 0.01,
                "_n500_ret_1m": 0.02,
                "_n500_ret_3m": 0.05,
                "_n500_ret_6m": 0.10,
            }
        ]
    )
    out = compute_bottom_up_sector_metrics(df, SECTOR_MASTER, df_nifty500_returns=n500)
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    # Price-relative RS: (1 + bottomup_ret_3m) / (1 + 0.05) - 1
    expected_rs = (1.0 + float(bank["bottomup_ret_3m"])) / (1.0 + 0.05) - 1.0
    assert bank["bottomup_rs_3m_nifty500"] == pytest.approx(expected_rs, rel=1e-6)


@pytest.mark.unit
def test_bottom_up_empty_input_returns_empty() -> None:
    empty = pd.DataFrame(
        columns=[  # type: ignore[arg-type]
            "instrument_id",
            "date",
            "sector_name",
            "close_approx",
            "ema_50_stock",
            "ema_200_stock",
            "avg_volume_20",
            "ret_1w",
            "ret_1m",
            "ret_3m",
            "ret_6m",
            "rs_1w_tier",
            "rs_1m_tier",
            "rs_3m_tier",
            "ema_10_ratio",
            "ema_20_ratio",
            "extension_pct",
        ]
    )
    out = compute_bottom_up_sector_metrics(empty, SECTOR_MASTER)
    assert out.empty


# --------------------------------------------------------------------------- #
# breadth                                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_sector_breadth_participation_50_handcomputed() -> None:
    df = _two_sector_frame()
    out = compute_sector_breadth(df, SECTOR_MASTER)
    # Bank: big_bank 99 > 100? close_approx = 90*(1+0.10)=99 < 100, NO. mid_bank
    # 47.25 < 50, NO. small_bank 20.9 < 20? close=22*0.95=20.9 > 20 = YES.
    # 1/3 above ema_50 → 0.333
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["participation_50"] == pytest.approx(1 / 3, abs=1e-6)


@pytest.mark.unit
def test_sector_breadth_participation_rs_threshold_at_one() -> None:
    df = _two_sector_frame()
    out = compute_sector_breadth(df, SECTOR_MASTER)
    # Bank: rs_1m_tier values 1.10, 1.0, 0.80 → only big_bank > 1 → 1/3
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["participation_rs"] == pytest.approx(1 / 3, abs=1e-6)


@pytest.mark.unit
def test_sector_breadth_leadership_concentration_in_unit_interval() -> None:
    df = _two_sector_frame()
    out = compute_sector_breadth(df, SECTOR_MASTER)
    # leadership_concentration = top-quintile abs(rs_3m) / total abs(rs_3m). Must
    # be in (0, 1] for any non-degenerate sector.
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert 0 < bank["leadership_concentration"] <= 1


# --------------------------------------------------------------------------- #
# top-down                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_top_down_metrics_resolves_index_and_falls_back() -> None:
    """Sector with NULL primary_nse_index uses fallback_benchmark."""
    master = pd.DataFrame(
        [
            {
                "sector_name": "Bank",
                "primary_nse_index": "NIFTY BANK",
                "fallback_benchmark": "NIFTY 500",
            },
            {"sector_name": "Other", "primary_nse_index": None, "fallback_benchmark": "NIFTY 500"},
        ]
    )
    d = pd.Timestamp("2024-06-01").date()
    idx_metrics = pd.DataFrame(
        [
            {
                "index_code": "NIFTY BANK",
                "date": d,
                "ret_1w": 0.01,
                "ret_1m": 0.05,
                "ret_3m": 0.08,
                "rs_3m_nifty500": 1.10,
                "ema_10_ratio_nifty500": 1.05,
                "ema_20_ratio_nifty500": 1.03,
            },
            {
                "index_code": "NIFTY 500",
                "date": d,
                "ret_1w": 0.005,
                "ret_1m": 0.025,
                "ret_3m": 0.04,
                "rs_3m_nifty500": 1.0,
                "ema_10_ratio_nifty500": 1.0,
                "ema_20_ratio_nifty500": 1.0,
            },
        ]
    )
    out = compute_top_down_sector_metrics(idx_metrics, master)
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["topdown_index_code"] == "NIFTY BANK"
    assert bank["topdown_ret_3m"] == pytest.approx(0.08)
    other = out[out["sector_name"] == "Other"].iloc[0]
    assert other["topdown_index_code"] == "NIFTY 500"


# --------------------------------------------------------------------------- #
# sector states                                                               #
# --------------------------------------------------------------------------- #


def _states_input_frame() -> pd.DataFrame:
    """Three sectors on one date with hand-picked metric values."""
    d = pd.Timestamp("2024-06-01").date()
    return pd.DataFrame(
        [
            # Bank: top RS, strong momentum, high participation → Overweight
            {
                "sector_name": "Bank",
                "date": d,
                "bottomup_ret_1m": 0.05,
                "bottomup_ret_3m": 0.10,
                "bottomup_ret_6m": 0.15,
                "bottomup_rs_3m_nifty500": 1.5,
                "bottomup_ema_10_ratio": 1.10,
                "bottomup_ema_20_ratio": 1.05,
                "topdown_index_code": "NIFTY BANK",
                "topdown_ret_1m": 0.04,
                "topdown_ret_3m": 0.09,
                "topdown_rs_3m_nifty500": 1.4,
                "constituent_count": 50,
                "participation_50": 0.7,
                "participation_rs": 0.6,
                "leadership_concentration": 0.4,
            },
            # Tech: bottom RS, low participation → Avoid
            {
                "sector_name": "Tech",
                "date": d,
                "bottomup_ret_1m": -0.05,
                "bottomup_ret_3m": -0.10,
                "bottomup_ret_6m": -0.15,
                "bottomup_rs_3m_nifty500": 0.5,
                "bottomup_ema_10_ratio": 0.95,
                "bottomup_ema_20_ratio": 0.97,
                "topdown_index_code": "NIFTY IT",
                "topdown_ret_1m": -0.04,
                "topdown_ret_3m": -0.09,
                "topdown_rs_3m_nifty500": 0.6,
                "constituent_count": 30,
                "participation_50": 0.2,
                "participation_rs": 0.1,
                "leadership_concentration": 0.5,
            },
            # Power+Energy: shared NIFTY ENERGY index → divergence guard test
            {
                "sector_name": "Power",
                "date": d,
                "bottomup_ret_1m": 0.01,
                "bottomup_ret_3m": 0.02,
                "bottomup_ret_6m": 0.03,
                "bottomup_rs_3m_nifty500": 1.0,
                "bottomup_ema_10_ratio": 1.0,
                "bottomup_ema_20_ratio": 1.0,
                "topdown_index_code": "NIFTY ENERGY",
                "topdown_ret_1m": 0.05,
                "topdown_ret_3m": 0.10,
                "topdown_rs_3m_nifty500": 1.2,
                "constituent_count": 10,
                "participation_50": 0.4,
                "participation_rs": 0.4,
                "leadership_concentration": 0.5,
            },
            {
                "sector_name": "Energy",
                "date": d,
                "bottomup_ret_1m": 0.02,
                "bottomup_ret_3m": 0.03,
                "bottomup_ret_6m": 0.04,
                "bottomup_rs_3m_nifty500": 1.1,
                "bottomup_ema_10_ratio": 1.01,
                "bottomup_ema_20_ratio": 1.0,
                "topdown_index_code": "NIFTY ENERGY",
                "topdown_ret_1m": 0.05,
                "topdown_ret_3m": 0.10,
                "topdown_rs_3m_nifty500": 1.2,
                "constituent_count": 12,
                "participation_50": 0.45,
                "participation_rs": 0.45,
                "leadership_concentration": 0.5,
            },
            # 5th sector — needed so Tech lands at rank 1/5 = 0.20 ≤ RS_QUINTILE_BOTTOM.
            # With only 4 sectors the minimum pct rank is 0.25 which wouldn't trigger Avoid_RS.
            {
                "sector_name": "Pharma",
                "date": d,
                "bottomup_ret_1m": -0.02,
                "bottomup_ret_3m": -0.04,
                "bottomup_ret_6m": -0.06,
                "bottomup_rs_3m_nifty500": 0.75,
                "bottomup_ema_10_ratio": 0.98,
                "bottomup_ema_20_ratio": 0.99,
                "topdown_index_code": "NIFTY PHARMA",
                "topdown_ret_1m": -0.01,
                "topdown_ret_3m": -0.03,
                "topdown_rs_3m_nifty500": 0.8,
                "constituent_count": 20,
                "participation_50": 0.35,
                "participation_rs": 0.35,
                "leadership_concentration": 0.4,
            },
        ]
    )


@pytest.mark.unit
def test_sector_states_overweight_when_top_rs_and_high_participation() -> None:
    df = _states_input_frame()
    out = compute_sector_states(df, THRESHOLDS)
    bank = out[out["sector_name"] == "Bank"].iloc[0]
    assert bank["bottomup_rs_state"] == "Overweight_RS"
    assert bank["sector_state"] == "Overweight"


@pytest.mark.unit
def test_sector_states_avoid_when_bottom_rs_and_low_participation() -> None:
    df = _states_input_frame()
    out = compute_sector_states(df, THRESHOLDS)
    tech = out[out["sector_name"] == "Tech"].iloc[0]
    assert tech["bottomup_rs_state"] == "Avoid_RS"
    assert tech["sector_state"] == "Avoid"


@pytest.mark.unit
def test_sector_states_divergence_guard_for_shared_topdown_index() -> None:
    """When two sectors share the same primary_nse_index (Power + Energy
    both = NIFTY ENERGY), divergence_flag must be FALSE for both rows even
    if the rank difference would normally fire."""
    df = _states_input_frame()
    out = compute_sector_states(df, THRESHOLDS)
    power = out[out["sector_name"] == "Power"].iloc[0]
    energy = out[out["sector_name"] == "Energy"].iloc[0]
    assert power["divergence_flag"] is False or power["divergence_flag"] == np.False_
    assert energy["divergence_flag"] is False or energy["divergence_flag"] == np.False_


@pytest.mark.unit
def test_sector_states_states_columns_match_schema() -> None:
    df = _states_input_frame()
    out = compute_sector_states(df, THRESHOLDS)
    schema_cols = [c for c in STATES_COLUMNS if c != "compute_run_id"]
    for col in schema_cols:
        assert col in out.columns, f"missing schema column: {col}"


@pytest.mark.unit
def test_sector_states_relative_participation_distributes_in_bear_market() -> None:
    """Bear-market scenario: all sectors have absolute participation_rs < 0.30.

    With absolute thresholds (pre-fix), every sector lands Underweight because
    ``participation_rs < underweight_max (0.30)`` is True for all — even relative
    sector leaders. After the fix (cross-sector percentile rank), top-ranked
    sectors still reach Overweight/Neutral.
    """
    d = pd.Timestamp("2024-01-15").date()
    df = pd.DataFrame(
        [
            {  # best — highest participation_rs, top RS
                "sector_name": "Bank",
                "date": d,
                "bottomup_ret_1m": 0.02,
                "bottomup_ret_3m": 0.06,
                "bottomup_ret_6m": 0.10,
                "bottomup_rs_3m_nifty500": 1.30,
                "bottomup_ema_10_ratio": 1.05,
                "bottomup_ema_20_ratio": 1.02,
                "topdown_index_code": "NIFTY BANK",
                "topdown_ret_1m": 0.02,
                "topdown_ret_3m": 0.05,
                "topdown_rs_3m_nifty500": 1.20,
                "constituent_count": 30,
                "participation_50": 0.35,
                "participation_rs": 0.25,  # < 0.30 absolute threshold
                "leadership_concentration": 0.4,
            },
            {
                "sector_name": "Energy",
                "date": d,
                "bottomup_ret_1m": 0.01,
                "bottomup_ret_3m": 0.04,
                "bottomup_ret_6m": 0.08,
                "bottomup_rs_3m_nifty500": 1.20,
                "bottomup_ema_10_ratio": 1.03,
                "bottomup_ema_20_ratio": 1.01,
                "topdown_index_code": "NIFTY ENERGY",
                "topdown_ret_1m": 0.01,
                "topdown_ret_3m": 0.04,
                "topdown_rs_3m_nifty500": 1.10,
                "constituent_count": 20,
                "participation_50": 0.30,
                "participation_rs": 0.20,  # < 0.30 absolute threshold
                "leadership_concentration": 0.4,
            },
            {
                "sector_name": "Power",
                "date": d,
                "bottomup_ret_1m": 0.00,
                "bottomup_ret_3m": 0.01,
                "bottomup_ret_6m": 0.02,
                "bottomup_rs_3m_nifty500": 1.00,
                "bottomup_ema_10_ratio": 1.01,
                "bottomup_ema_20_ratio": 1.00,
                "topdown_index_code": "NIFTY POWER",
                "topdown_ret_1m": 0.00,
                "topdown_ret_3m": 0.01,
                "topdown_rs_3m_nifty500": 1.00,
                "constituent_count": 15,
                "participation_50": 0.25,
                "participation_rs": 0.15,  # < 0.30 absolute threshold
                "leadership_concentration": 0.4,
            },
            {
                "sector_name": "Pharma",
                "date": d,
                "bottomup_ret_1m": -0.01,
                "bottomup_ret_3m": -0.02,
                "bottomup_ret_6m": -0.04,
                "bottomup_rs_3m_nifty500": 0.85,
                "bottomup_ema_10_ratio": 0.98,
                "bottomup_ema_20_ratio": 0.99,
                "topdown_index_code": "NIFTY PHARMA",
                "topdown_ret_1m": -0.01,
                "topdown_ret_3m": -0.02,
                "topdown_rs_3m_nifty500": 0.90,
                "constituent_count": 25,
                "participation_50": 0.20,
                "participation_rs": 0.10,  # < 0.30 absolute threshold
                "leadership_concentration": 0.4,
            },
            {  # weakest — bottom quintile RS, lowest breadth
                "sector_name": "Tech",
                "date": d,
                "bottomup_ret_1m": -0.05,
                "bottomup_ret_3m": -0.10,
                "bottomup_ret_6m": -0.15,
                "bottomup_rs_3m_nifty500": 0.60,
                "bottomup_ema_10_ratio": 0.95,
                "bottomup_ema_20_ratio": 0.97,
                "topdown_index_code": "NIFTY IT",
                "topdown_ret_1m": -0.04,
                "topdown_ret_3m": -0.09,
                "topdown_rs_3m_nifty500": 0.65,
                "constituent_count": 20,
                "participation_50": 0.15,
                "participation_rs": 0.05,  # < 0.30 absolute threshold
                "leadership_concentration": 0.5,
            },
        ]
    )

    out = compute_sector_states(df, THRESHOLDS)
    states = dict(zip(out["sector_name"], out["sector_state"], strict=False))

    # Relative leader must escape Underweight even when absolute breadth is low
    assert states["Bank"] in ("Overweight", "Neutral"), (
        f"Bank (relative breadth leader) got '{states['Bank']}'. "
        f"All-Underweight = absolute participation bug. States: {states}"
    )
    non_negative = {s: v for s, v in states.items() if v not in ("Underweight", "Avoid")}
    assert len(non_negative) >= 2, (
        f"Expected >=2 sectors Overweight/Neutral in bear market, got: {states}"
    )


# --------------------------------------------------------------------------- #
# assemble                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_assemble_sector_metrics_columns_match_schema() -> None:
    df = _two_sector_frame()
    bu = compute_bottom_up_sector_metrics(df, SECTOR_MASTER)
    breadth = compute_sector_breadth(df, SECTOR_MASTER)
    # Empty top-down for this test
    td = pd.DataFrame(
        columns=[  # type: ignore[arg-type]
            "sector_name",
            "date",
            "topdown_index_code",
            "topdown_ret_1m",
            "topdown_ret_3m",
            "topdown_rs_3m_nifty500",
        ]
    )
    out = assemble_sector_metrics(bu, td, breadth)
    expected = [c for c in METRICS_COLUMNS if c != "compute_run_id"]
    assert list(out.columns) == expected
