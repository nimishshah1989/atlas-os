"""Layer 1: convert raw metric arrays to state arrays using genome thresholds.

All inputs are numpy arrays. No DB calls. No pandas. Pure numpy operations
so vectorbt can batch thousands of genomes efficiently.

RS state:  0=Laggard, 1=Weak, 2=Average, 3=Strong, 4=Leader
Regime:    0=Risk-Off, 1=Cautious, 2=Constructive, 3=Risk-On
Vol state: 0=Normal, 1=Elevated, 2=High
Momentum:  0=Decelerating, 1=Neutral, 2=Accelerating
"""

from __future__ import annotations

from typing import overload

import numpy as np

from atlas.trading.genome import Layer1Perception

# ---------------------------------------------------------------------------
# State integer constants (exported for callers)
# ---------------------------------------------------------------------------
RS_LAGGARD, RS_WEAK, RS_AVERAGE, RS_STRONG, RS_LEADER = 0, 1, 2, 3, 4
REGIME_RISK_OFF, REGIME_CAUTIOUS, REGIME_CONSTRUCTIVE, REGIME_RISK_ON = 0, 1, 2, 3
VOL_NORMAL, VOL_ELEVATED, VOL_HIGH = 0, 1, 2
MOM_DECELERATING, MOM_NEUTRAL, MOM_ACCELERATING = 0, 1, 2


def derive_rs_state(rs_pctile: np.ndarray, layer1: Layer1Perception) -> np.ndarray:
    """Map RS percentile array to RS state integers.

    Args:
        rs_pctile: shape (n_stocks, n_days) — blended RS percentile rank 0–100
        layer1: genome Layer1Perception with cutoff thresholds

    Returns:
        int8 array of same shape with RS state values 0–4
    """
    out = np.full(rs_pctile.shape, RS_LAGGARD, dtype=np.int8)
    out = np.where(rs_pctile >= layer1.rs_weak_cutoff_pct, RS_WEAK, out)
    out = np.where(rs_pctile >= layer1.rs_average_cutoff_pct, RS_AVERAGE, out)
    out = np.where(rs_pctile >= layer1.rs_strong_cutoff_pct, RS_STRONG, out)
    out = np.where(rs_pctile >= layer1.rs_leader_cutoff_pct, RS_LEADER, out)
    return out.astype(np.int8)


def derive_regime_state(
    breadth_pct: np.ndarray, vix: np.ndarray, layer1: Layer1Perception
) -> np.ndarray:
    """Map market breadth + VIX to regime state integer per day.

    NaN VIX is treated as not calm: breadth still controls cautious/constructive
    but risk_on requires valid + calm VIX.

    Args:
        breadth_pct: shape (n_days,) — % of universe above 50-day MA
        vix: shape (n_days,) — VIX value, NaN-safe

    Returns:
        int8 array shape (n_days,) with regime state 0–3
    """
    vix_valid = ~np.isnan(vix)
    vix_calm = vix_valid & (vix < layer1.regime_risk_on_vix_ceiling)

    out = np.full(breadth_pct.shape, REGIME_RISK_OFF, dtype=np.int8)
    out = np.where(breadth_pct >= layer1.regime_cautious_breadth_pct, REGIME_CAUTIOUS, out)
    out = np.where(
        breadth_pct >= layer1.regime_constructive_breadth_pct,
        REGIME_CONSTRUCTIVE,
        out,
    )
    # Risk-On requires breadth AND valid calm VIX
    out = np.where(
        (breadth_pct >= layer1.regime_risk_on_breadth_pct) & vix_calm,
        REGIME_RISK_ON,
        out,
    )
    return out.astype(np.int8)


def derive_vol_state(vol_ratio: np.ndarray, layer1: Layer1Perception) -> np.ndarray:
    """Map vol_ratio (short-window vol / long-window vol) to vol state.

    Args:
        vol_ratio: shape (n_stocks, n_days)

    Returns:
        int8 array of same shape with vol state 0–2
    """
    out = np.full(vol_ratio.shape, VOL_NORMAL, dtype=np.int8)
    out = np.where(vol_ratio >= layer1.vol_elevated_ratio, VOL_ELEVATED, out)
    out = np.where(vol_ratio >= layer1.vol_high_ratio, VOL_HIGH, out)
    return out.astype(np.int8)


def derive_momentum_state(ema_ratio: np.ndarray, layer1: Layer1Perception) -> np.ndarray:
    """Map EMA ratio (short EMA / long EMA) to momentum state.

    Args:
        ema_ratio: shape (n_stocks, n_days) — e.g. EMA20/EMA63 (ema_20_ratio column)

    Returns:
        int8 array of same shape with momentum state 0–2
    """
    out = np.full(ema_ratio.shape, MOM_NEUTRAL, dtype=np.int8)
    out = np.where(ema_ratio >= layer1.momentum_accel_ema_ratio, MOM_ACCELERATING, out)
    out = np.where(ema_ratio <= layer1.momentum_decel_ema_ratio, MOM_DECELERATING, out)
    return out.astype(np.int8)


def compute_blended_rs_pctile(
    rs_arrays: dict[str, np.ndarray],
    weights: dict[str, float],
) -> np.ndarray:
    """Weighted blend of multi-timeframe RS percentile arrays.

    Args:
        rs_arrays: {'1w': ndarray, '1m': ndarray, '3m': ndarray}
                   each shape (n_stocks, n_days)
        weights: genome rs_timeframe_weights, sum=1.0

    Returns:
        float32 array shape (n_stocks, n_days)
    """
    if rs_arrays.keys() != weights.keys():
        raise ValueError(f"rs_arrays keys {set(rs_arrays)} != weights keys {set(weights)}")
    blended = np.zeros_like(next(iter(rs_arrays.values())), dtype=np.float32)
    for tf, arr in rs_arrays.items():
        blended += weights.get(tf, 0.0) * arr.astype(np.float32)
    return blended


@overload
def compute_rs_velocity(
    rs_short_or_state: np.ndarray,
    rs_long_or_lookback: np.ndarray,
    layer1: Layer1Perception,
) -> dict[str, int]: ...


@overload
def compute_rs_velocity(
    rs_short_or_state: np.ndarray,
    rs_long_or_lookback: int,
    layer1: None = ...,
) -> tuple[np.ndarray, np.ndarray]: ...


def compute_rs_velocity(
    rs_short_or_state: np.ndarray,
    rs_long_or_lookback: np.ndarray | int,
    layer1: Layer1Perception | None = None,  # pyright: ignore[reportUnusedParameter] — reserved for per-layer1 thresholds
) -> dict[str, int] | tuple[np.ndarray, np.ndarray]:
    """Compute RS velocity direction, or (for state arrays) days-in-state + direction.

    Two calling conventions are supported:

    1. Short-vs-long RS arrays (new, returns dict):
       ``compute_rs_velocity(rs_short, rs_long, layer1)``
       Compares mean of short-term RS array to mean of long-term RS array and
       returns ``{"direction": 1 | 0 | -1}`` where 1=improving, 0=stable, -1=declining.

    2. State-array + lookback (legacy, returns tuple of arrays):
       ``compute_rs_velocity(rs_state, lookback)``
       Returns ``(days_in_state, direction)`` arrays of the same shape as rs_state.

    Args:
        rs_short_or_state: RS percentile array (short window) or int8 state array
        rs_long_or_lookback: RS percentile array (long window) or int lookback days
        layer1: Layer1Perception instance (required for new calling convention)
    """
    if isinstance(rs_long_or_lookback, np.ndarray):
        # New calling convention: compare short vs long RS arrays
        rs_short = rs_short_or_state.astype(np.float32)
        rs_long = rs_long_or_lookback.astype(np.float32)
        diff = np.nanmean(rs_short) - np.nanmean(rs_long)
        direction = int(np.sign(diff))
        return {"direction": direction}

    # Legacy calling convention: state array + integer lookback
    rs_state = rs_short_or_state
    lookback = int(rs_long_or_lookback)
    n_stocks, n_days = rs_state.shape
    days_in_state = np.ones((n_stocks, n_days), dtype=np.int16)
    direction_arr = np.zeros((n_stocks, n_days), dtype=np.int8)

    for d in range(1, n_days):
        same = rs_state[:, d] == rs_state[:, d - 1]
        days_in_state[:, d] = np.where(same, days_in_state[:, d - 1] + 1, 1)

    for d in range(lookback, n_days):
        past = rs_state[:, d - lookback]
        curr = rs_state[:, d]
        direction_arr[:, d] = np.sign(curr.astype(np.int16) - past.astype(np.int16)).astype(np.int8)

    return days_in_state, direction_arr
