"""Unit tests for ``atlas.compute.regime``.

Synthetic input frames; no DB. Tests pin classification rules and
the dislocation-override persistence semantics.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from atlas.compute.regime import (
    DEPLOYMENT_MULTIPLIERS,
    apply_dislocation_override,
    classify_regime_state,
)

THRESHOLDS = {
    "regime_risk_on_breadth_min_pct": 60.0,
    "regime_constructive_breadth_min_pct": 50.0,
    "regime_risk_off_breadth_max_pct": 40.0,
    "regime_risk_on_vix_max": 18.0,
    "regime_constructive_vix_max": 22.0,
    "regime_cautious_vix_max": 28.0,
    "regime_near_200ema_band_pct": 2.0,
    "dislocation_vol_multiplier": 4.0,
}


def _input_row(**overrides) -> dict:
    base = {
        "date": date(2024, 6, 1),
        "nifty500_close": 25_000.0,
        "nifty500_ema_50": 24_500.0,
        "nifty500_ema_200": 22_000.0,
        "nifty500_above_ema_50": True,
        "nifty500_above_ema_200": True,
        "pct_above_ema_50": 0.65,
        "pct_above_ema_200": 0.70,
        "india_vix": 14.0,
        "realized_vol_5d_nifty500": 0.10,
        "vol_252_median_nifty500": 0.12,
    }
    base.update(overrides)
    return base


def _input_frame(rows: list[dict]) -> pd.DataFrame:
    """Build the regime_inputs frame with the shape classify_regime_state expects."""
    df = pd.DataFrame(rows)
    return df


# --------------------------------------------------------------------------- #
# classify_regime_state                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_regime_risk_on_when_above_200_breadth_high_vix_low() -> None:
    df = _input_frame([_input_row(pct_above_ema_50=0.70, india_vix=14.0)])
    out = classify_regime_state(df, THRESHOLDS)
    assert out["regime_state"].iloc[0] == "Risk-On"
    assert out["deployment_multiplier"].iloc[0] == pytest.approx(1.0)


@pytest.mark.unit
def test_regime_constructive_band() -> None:
    df = _input_frame([_input_row(pct_above_ema_50=0.55, india_vix=20.0)])
    out = classify_regime_state(df, THRESHOLDS)
    assert out["regime_state"].iloc[0] == "Constructive"
    assert out["deployment_multiplier"].iloc[0] == pytest.approx(0.7)


@pytest.mark.unit
def test_regime_risk_off_below_200_low_breadth_high_vix() -> None:
    df = _input_frame(
        [
            _input_row(
                nifty500_close=20_000.0,
                nifty500_ema_200=22_000.0,
                nifty500_above_ema_50=False,
                nifty500_above_ema_200=False,
                pct_above_ema_50=0.30,
                india_vix=32.0,
            )
        ]
    )
    out = classify_regime_state(df, THRESHOLDS)
    assert out["regime_state"].iloc[0] == "Risk-Off"
    assert out["deployment_multiplier"].iloc[0] == pytest.approx(0.0)


@pytest.mark.unit
def test_regime_cautious_when_near_200ema_band() -> None:
    """Within ±2% of 200-EMA → Cautious regardless of breadth."""
    df = _input_frame(
        [
            _input_row(
                nifty500_close=22_220.0,  # within 1% of 22_000 ema_200
                nifty500_ema_200=22_000.0,
                nifty500_above_ema_50=True,
                nifty500_above_ema_200=True,
                pct_above_ema_50=0.55,
                india_vix=24.0,  # in [22, 28] → Cautious VIX band too
            )
        ]
    )
    out = classify_regime_state(df, THRESHOLDS)
    assert out["regime_state"].iloc[0] == "Cautious"


@pytest.mark.unit
def test_regime_state_warmup_rows_get_null() -> None:
    """When inputs are all NaN we must NOT emit a placeholder regime state."""
    df = _input_frame(
        [
            {
                "date": date(2024, 1, 1),
                "nifty500_close": np.nan,
                "nifty500_ema_200": np.nan,
                "nifty500_above_ema_50": False,
                "nifty500_above_ema_200": False,
                "pct_above_ema_50": np.nan,
                "india_vix": np.nan,
                "realized_vol_5d_nifty500": np.nan,
                "vol_252_median_nifty500": np.nan,
            }
        ]
    )
    out = classify_regime_state(df, THRESHOLDS)
    assert pd.isna(out["regime_state"].iloc[0])
    assert pd.isna(out["deployment_multiplier"].iloc[0])


# --------------------------------------------------------------------------- #
# dislocation override                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_dislocation_fires_when_5d_vol_exceeds_4x_median() -> None:
    """One day with vol = 5x median → dislocation_active for that day + persistence."""
    base = date(2024, 6, 1)
    rows = []
    for i in range(10):
        d = base + timedelta(days=i)
        # Day 5 has the spike.
        if i == 5:
            real_vol = 0.60
            median = 0.10
        else:
            real_vol = 0.10
            median = 0.10
        rows.append(
            {
                "date": d,
                "regime_state": "Risk-On",
                "deployment_multiplier": 1.0,
                "realized_vol_5d_nifty500": real_vol,
                "vol_252_median_nifty500": median,
            }
        )
    df = pd.DataFrame(rows)
    out = apply_dislocation_override(df, THRESHOLDS, persist_days=5)

    # Trigger at i=5; persists via rolling-max for 5 days → days 5,6,7,8,9 active.
    assert bool(out.iloc[4]["dislocation_active"]) is False
    assert bool(out.iloc[5]["dislocation_active"]) is True
    assert bool(out.iloc[9]["dislocation_active"]) is True
    # Day 5 onwards: regime_state replaced
    assert out.iloc[5]["regime_state"] == "DISLOCATION_SUSPENDED"
    assert out.iloc[5]["deployment_multiplier"] == 0.0


@pytest.mark.unit
def test_dislocation_no_op_when_vol_below_threshold() -> None:
    base = date(2024, 6, 1)
    rows = []
    for i in range(5):
        rows.append(
            {
                "date": base + timedelta(days=i),
                "regime_state": "Risk-On",
                "deployment_multiplier": 1.0,
                "realized_vol_5d_nifty500": 0.10,
                "vol_252_median_nifty500": 0.10,
            }
        )
    df = pd.DataFrame(rows)
    out = apply_dislocation_override(df, THRESHOLDS, persist_days=5)
    assert not out["dislocation_active"].any()
    assert (out["regime_state"] == "Risk-On").all()


@pytest.mark.unit
def test_dislocation_null_guard_when_vol_inputs_missing() -> None:
    """Missing realized_vol must not crash; treated as no-trigger."""
    df = pd.DataFrame(
        [
            {
                "date": date(2024, 6, 1),
                "regime_state": "Risk-On",
                "deployment_multiplier": 1.0,
                "realized_vol_5d_nifty500": np.nan,
                "vol_252_median_nifty500": np.nan,
            }
        ]
    )
    out = apply_dislocation_override(df, THRESHOLDS, persist_days=5)
    assert bool(out.iloc[0]["dislocation_active"]) is False
    assert out.iloc[0]["regime_state"] == "Risk-On"


# --------------------------------------------------------------------------- #
# Multipliers map                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_deployment_multipliers_complete() -> None:
    """Every regime state must have a multiplier defined."""
    for state in ("Risk-On", "Constructive", "Cautious", "Risk-Off", "DISLOCATION_SUSPENDED"):
        assert state in DEPLOYMENT_MULTIPLIERS
    assert DEPLOYMENT_MULTIPLIERS["Risk-On"] == 1.0
    assert DEPLOYMENT_MULTIPLIERS["Constructive"] == 0.7
    assert DEPLOYMENT_MULTIPLIERS["Cautious"] == 0.4
    assert DEPLOYMENT_MULTIPLIERS["Risk-Off"] == 0.0
    assert DEPLOYMENT_MULTIPLIERS["DISLOCATION_SUSPENDED"] == 0.0
