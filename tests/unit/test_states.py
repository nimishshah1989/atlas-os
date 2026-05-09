"""Unit tests for state classifiers in ``atlas.compute.states``.

Boundary fixtures: each test passes a row that lands precisely at a state
boundary (top quintile, bottom quintile, Weinstein gate edge, etc.) and
asserts the expected label. These catch off-by-one in classifier ordering.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.compute.states import (
    apply_below_trend_conjunction,
    apply_suspension_overrides,
    classify_momentum_state,
    classify_risk_state,
    classify_rs_state,
    classify_volume_state,
)

THRESHOLDS = {
    "rs_quintile_top": 0.80,
    "rs_quintile_bottom": 0.20,
    "momentum_flat_band_pct": 0.02,
    "momentum_ema_convergence_pct": 0.01,
    "risk_extension_low_max_pct": 25.0,
    "risk_extension_high_min_pct": 40.0,
    "risk_vol_ratio_low_max": 1.0,
    "risk_vol_ratio_normal_max": 1.25,
    "risk_vol_ratio_high_min": 1.6,
    "volume_accumulation_expansion_min": 1.2,
    "volume_accumulation_effort_min": 1.3,
    "volume_distribution_effort_max": 0.8,
    "volume_heavy_distribution_effort_max": 0.6,
}


def _row(**kwargs) -> pd.DataFrame:
    """Single-row frame populated with sensible defaults for every classifier."""
    base = {
        "rs_pctile_1w": 0.5,
        "rs_pctile_1m": 0.5,
        "rs_pctile_3m": 0.5,
        "weinstein_gate_pass": True,
        "stage1_base_qualifies": False,
        "ema_10_ratio": 1.0,
        "ema_20_ratio": 1.0,
        "ema_10_at_20d_high": False,
        "ema_10_at_20d_low": False,
        "extension_pct": 0.10,
        "vol_ratio_63": 1.0,
        "volume_expansion": 1.0,
        "effort_ratio_63": 1.0,
        "history_gate_pass": True,
        "liquidity_gate_pass": True,
    }
    base.update(kwargs)
    return pd.DataFrame([base])


# --------------------------------------------------------------------------- #
# RS state                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_rs_state_leader_requires_top_quintile_all_three_and_weinstein() -> None:
    df = _row(rs_pctile_1w=0.95, rs_pctile_1m=0.95, rs_pctile_3m=0.95)
    out = classify_rs_state(df, THRESHOLDS)
    assert out["rs_state"].iloc[0] == "Leader"


@pytest.mark.unit
def test_rs_state_laggard_takes_priority_over_weak() -> None:
    df = _row(rs_pctile_1w=0.05, rs_pctile_1m=0.05, rs_pctile_3m=0.05)
    out = classify_rs_state(df, THRESHOLDS)
    assert out["rs_state"].iloc[0] == "Laggard"


@pytest.mark.unit
def test_rs_state_weak_when_one_window_in_bottom() -> None:
    df = _row(rs_pctile_1w=0.10, rs_pctile_1m=0.5, rs_pctile_3m=0.5)
    out = classify_rs_state(df, THRESHOLDS)
    assert out["rs_state"].iloc[0] == "Weak"


@pytest.mark.unit
def test_rs_state_strong_without_weinstein_falls_to_average() -> None:
    df = _row(rs_pctile_1m=0.95, rs_pctile_3m=0.95, weinstein_gate_pass=False)
    out = classify_rs_state(df, THRESHOLDS)
    assert out["rs_state"].iloc[0] == "Average"


@pytest.mark.unit
def test_rs_state_emerging_requires_stage1_base() -> None:
    no_base = _row(
        rs_pctile_1w=0.95, rs_pctile_1m=0.95, rs_pctile_3m=0.5, stage1_base_qualifies=False
    )
    assert classify_rs_state(no_base, THRESHOLDS)["rs_state"].iloc[0] == "Average"

    with_base = _row(
        rs_pctile_1w=0.95, rs_pctile_1m=0.95, rs_pctile_3m=0.5, stage1_base_qualifies=True
    )
    assert classify_rs_state(with_base, THRESHOLDS)["rs_state"].iloc[0] == "Emerging"


# --------------------------------------------------------------------------- #
# Risk state                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_risk_below_trend_when_negative_extension() -> None:
    df = _row(extension_pct=-0.05)
    assert classify_risk_state(df, THRESHOLDS)["risk_state"].iloc[0] == "Below Trend"


@pytest.mark.unit
def test_risk_high_when_extension_or_vol_above_threshold() -> None:
    over_ext = _row(extension_pct=0.45)  # 45% > 40 threshold
    assert classify_risk_state(over_ext, THRESHOLDS)["risk_state"].iloc[0] == "High"

    over_vol = _row(extension_pct=0.10, vol_ratio_63=1.7)
    assert classify_risk_state(over_vol, THRESHOLDS)["risk_state"].iloc[0] == "High"


@pytest.mark.unit
def test_risk_low_when_inside_low_band() -> None:
    df = _row(extension_pct=0.05, vol_ratio_63=0.9)
    assert classify_risk_state(df, THRESHOLDS)["risk_state"].iloc[0] == "Low"


@pytest.mark.unit
def test_below_trend_conjunction_forces_rs_to_average() -> None:
    df = pd.DataFrame([{"risk_state": "Below Trend", "rs_state": "Strong"}])
    out = apply_below_trend_conjunction(df)
    assert out["rs_state"].iloc[0] == "Average"


# --------------------------------------------------------------------------- #
# Momentum / volume                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_momentum_accelerating_at_20d_high() -> None:
    df = _row(ema_10_ratio=1.05, ema_20_ratio=1.02, ema_10_at_20d_high=True)
    assert classify_momentum_state(df, THRESHOLDS)["momentum_state"].iloc[0] == "Accelerating"


@pytest.mark.unit
def test_momentum_flat_inside_band() -> None:
    # r10 == r20 means no directional dominance — falls through to Flat via
    # the EMA-converged predicate (|r10 - r20| <= 0.01).
    df = _row(ema_10_ratio=1.005, ema_20_ratio=1.005)
    assert classify_momentum_state(df, THRESHOLDS)["momentum_state"].iloc[0] == "Flat"


@pytest.mark.unit
def test_volume_heavy_distribution() -> None:
    df = _row(volume_expansion=1.3, effort_ratio_63=0.5)
    assert classify_volume_state(df, THRESHOLDS)["volume_state"].iloc[0] == "Heavy Distribution"


@pytest.mark.unit
def test_volume_accumulation() -> None:
    df = _row(volume_expansion=1.5, effort_ratio_63=1.5)
    assert classify_volume_state(df, THRESHOLDS)["volume_state"].iloc[0] == "Accumulation"


# --------------------------------------------------------------------------- #
# Suspension overrides                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_suspension_priority_history_over_liquidity() -> None:
    df = pd.DataFrame(
        [
            {
                "rs_state": "Leader",
                "momentum_state": "Improving",
                "risk_state": "Low",
                "volume_state": "Accumulation",
                "history_gate_pass": False,
                "liquidity_gate_pass": False,
            }
        ]
    )
    out = apply_suspension_overrides(df)
    # History fail wins (most-specific) over liquidity fail
    assert out["rs_state"].iloc[0] == "INSUFFICIENT_HISTORY"
    assert out["momentum_state"].iloc[0] == "INSUFFICIENT_HISTORY"


@pytest.mark.unit
def test_suspension_dislocation_lowest_priority() -> None:
    df = pd.DataFrame(
        [
            {
                "rs_state": "Leader",
                "momentum_state": "Improving",
                "risk_state": "Low",
                "volume_state": "Accumulation",
                "history_gate_pass": True,
                "liquidity_gate_pass": True,
            }
        ]
    )
    dislocation = pd.Series([True], index=df.index)
    out = apply_suspension_overrides(df, market_dislocation=dislocation)
    assert out["rs_state"].iloc[0] == "DISLOCATION_SUSPENDED"


# --------------------------------------------------------------------------- #
# RS momentum ratio regression — ETF price vs Nifty level                     #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_etf_momentum_improving_not_flat_when_ema10_above_ema20() -> None:
    """Regression: ETF-priced instruments must not collapse to Flat because ETF price < Nifty.

    add_rs_momentum previously divided ema_10_stock by ema_10_benchmark (price ratio),
    so ETFs at ~₹200 always produced r10 ≈ 0.009 < 1.  The fix computes
    r10 = ema10_stock/ema20_stock and r20 = ema10_benchmark/ema20_benchmark.
    """
    from atlas.compute.primitives import add_rs_momentum

    df = pd.DataFrame(
        [
            # Earlier row so the test row is not at the 20-day high (avoids
            # the vacuously-true at_20d_high single-row edge case).
            {
                "instrument_id": "ETF_TEST",
                "date": pd.Timestamp("2024-01-01"),
                "ema_10_stock": 210.0,
                "ema_20_stock": 196.0,
                "ema_10_benchmark": 22200.0,
                "ema_20_benchmark": 21950.0,
            },
            {
                "instrument_id": "ETF_TEST",
                "date": pd.Timestamp("2024-01-02"),
                "ema_10_stock": 205.0,
                "ema_20_stock": 198.0,
                "ema_10_benchmark": 22100.0,
                "ema_20_benchmark": 22000.0,
            },
        ]
    )
    df_with_ratios = add_rs_momentum(df)
    mask = df_with_ratios["date"] == pd.Timestamp("2024-01-02")
    row = df_with_ratios.loc[mask].copy()
    # r10 = 205/198 ≈ 1.035 > 1; r20 = 22100/22000 ≈ 1.0045; r10 > r20 → Improving
    result = classify_momentum_state(row, THRESHOLDS)
    assert result["momentum_state"].iloc[0] == "Improving"
