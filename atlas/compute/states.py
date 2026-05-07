"""State classifiers — ``np.select``-based, threshold-driven.

Per methodology §7.1–§7.4 and architecture §5.6.

All thresholds come from ``atlas.atlas_thresholds`` (loaded once via
``atlas.db.load_thresholds``); classifiers receive the dict as a parameter
and never read from the DB themselves. This keeps unit tests trivial — pass
a synthetic threshold dict, get deterministic state labels.

Suspended states (INSUFFICIENT_HISTORY, ILLIQUID, DISLOCATION_SUSPENDED) are
applied last via :func:`apply_suspension_overrides`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# RS state — methodology §7.1                                                 #
# --------------------------------------------------------------------------- #


def classify_rs_state(df: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    """Apply the 7-state RS classification.

    Required columns:
        rs_pctile_1w, rs_pctile_1m, rs_pctile_3m,
        weinstein_gate_pass, stage1_base_qualifies

    Result column: ``rs_state`` ∈ {Leader, Strong, Consolidating, Emerging,
    Average, Weak, Laggard}.

    Threshold keys: ``rs_quintile_top`` (default 0.80),
    ``rs_quintile_bottom`` (default 0.20).
    """
    top = thresholds["rs_quintile_top"]
    bot = thresholds["rs_quintile_bottom"]

    out = df.copy()
    p1w = out["rs_pctile_1w"]
    p1m = out["rs_pctile_1m"]
    p3m = out["rs_pctile_3m"]
    w = out["weinstein_gate_pass"].fillna(False)
    s1 = out["stage1_base_qualifies"].fillna(False)

    in_top_1w = p1w >= top
    in_top_1m = p1m >= top
    in_top_3m = p3m >= top
    in_bot_1w = p1w <= bot
    in_bot_1m = p1m <= bot
    in_bot_3m = p3m <= bot

    # Order matters in np.select — first match wins. Laggard before Weak;
    # Leader/Strong/Consolidating/Emerging require Weinstein gate.
    conditions = [
        in_bot_1w & in_bot_1m & in_bot_3m,
        in_bot_1w | in_bot_1m | in_bot_3m,
        in_top_1w & in_top_1m & in_top_3m & w,
        in_top_1m & in_top_3m & ~in_top_1w & w,
        in_top_3m & ~in_top_1m & ~in_top_1w & w,
        in_top_1w & in_top_1m & ~in_top_3m & s1 & w,
    ]
    choices = ["Laggard", "Weak", "Leader", "Strong", "Consolidating", "Emerging"]
    out["rs_state"] = np.select(conditions, choices, default="Average")
    return out


# --------------------------------------------------------------------------- #
# Momentum state — methodology §7.2                                           #
# --------------------------------------------------------------------------- #


def classify_momentum_state(df: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    """Apply the 5-state momentum classification.

    Required columns: ``ema_10_ratio``, ``ema_20_ratio``, ``ema_10_at_20d_high``,
    ``ema_10_at_20d_low``.

    Threshold keys: ``momentum_flat_band_pct`` (default 0.02),
    ``momentum_ema_convergence_pct`` (default 0.01).
    """
    flat_band = thresholds["momentum_flat_band_pct"]
    converge = thresholds["momentum_ema_convergence_pct"]

    out = df.copy()
    r10 = out["ema_10_ratio"]
    r20 = out["ema_20_ratio"]
    at_high = out["ema_10_at_20d_high"].fillna(False)
    at_low = out["ema_10_at_20d_low"].fillna(False)

    near_1 = (r10 - 1).abs() <= flat_band
    emas_converged = (r10 - r20).abs() <= converge

    conditions = [
        (r10 > 1) & (r10 > r20) & at_high,
        (r10 > 1) & (r10 > r20),
        (r10 < 1) & (r10 < r20) & at_low,
        (r10 < 1) & (r10 < r20),
        near_1 | emas_converged,
    ]
    choices = ["Accelerating", "Improving", "Collapsing", "Deteriorating", "Flat"]
    out["momentum_state"] = np.select(conditions, choices, default="Flat")
    return out


# --------------------------------------------------------------------------- #
# Risk state — methodology §7.3                                               #
# --------------------------------------------------------------------------- #


def classify_risk_state(df: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    """Apply the 5-state risk classification.

    "Below Trend" is terminal: when ``extension_pct < 0`` (price below the
    200-EMA), this state overrides everything else AND the caller forces
    ``rs_state = 'Average'`` per methodology §7.3 (the conjunction rule called
    out in M2 spec patch note dated 2026-05-06).

    Required columns: ``extension_pct``, ``vol_ratio_63``.
    """
    ext_low_max = thresholds["risk_extension_low_max_pct"]
    ext_high_min = thresholds["risk_extension_high_min_pct"]
    vol_low_max = thresholds["risk_vol_ratio_low_max"]
    vol_norm_max = thresholds["risk_vol_ratio_normal_max"]
    vol_high_min = thresholds["risk_vol_ratio_high_min"]

    out = df.copy()
    ext = out["extension_pct"] * 100  # methodology states thresholds in %
    vol_r = out["vol_ratio_63"]

    conditions = [
        ext < 0,
        (ext > ext_high_min) | (vol_r > vol_high_min),
        ((ext > ext_low_max) & (ext <= ext_high_min))
        | ((vol_r > vol_norm_max) & (vol_r <= vol_high_min)),
        (ext >= 0) & (ext <= ext_low_max) & (vol_r > vol_low_max) & (vol_r <= vol_norm_max),
        (ext >= 0) & (ext <= ext_low_max) & (vol_r <= vol_low_max),
    ]
    choices = ["Below Trend", "High", "Elevated", "Normal", "Low"]
    out["risk_state"] = np.select(conditions, choices, default="Normal")
    return out


def apply_below_trend_conjunction(df: pd.DataFrame) -> pd.DataFrame:
    """Force ``rs_state = 'Average'`` whenever ``risk_state = 'Below Trend'``.

    Per methodology §7.3 terminal-classification rule and ``ATLAS_M2`` patch
    note (2026-05-06).
    """
    out = df.copy()
    mask = out["risk_state"] == "Below Trend"
    out.loc[mask, "rs_state"] = "Average"
    return out


# --------------------------------------------------------------------------- #
# Volume state — methodology §7.4                                             #
# --------------------------------------------------------------------------- #


def classify_volume_state(df: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    """Apply the 5-state volume classification.

    Required columns: ``volume_expansion``, ``effort_ratio_63``.
    """
    acc_exp = thresholds["volume_accumulation_expansion_min"]
    acc_eff = thresholds["volume_accumulation_effort_min"]
    dist_eff = thresholds["volume_distribution_effort_max"]
    heavy_eff = thresholds["volume_heavy_distribution_effort_max"]

    out = df.copy()
    exp = out["volume_expansion"]
    eff = out["effort_ratio_63"]

    conditions = [
        (eff <= heavy_eff) & (exp >= 1.0),
        eff <= dist_eff,
        (exp >= acc_exp) & (eff >= acc_eff),
        (exp >= 1.0) & (exp < acc_exp) & (eff >= 1.1),
    ]
    choices = ["Heavy Distribution", "Distribution", "Accumulation", "Steady-Buying"]
    out["volume_state"] = np.select(conditions, choices, default="Neutral")
    return out


# --------------------------------------------------------------------------- #
# Suspension overrides                                                        #
# --------------------------------------------------------------------------- #


SUSPENSION_PRIORITY = ("INSUFFICIENT_HISTORY", "ILLIQUID", "DISLOCATION_SUSPENDED")
"""Ordered most-specific → least-specific. ``np.select`` picks the first match,
so a stock that's both new and illiquid shows ``INSUFFICIENT_HISTORY``."""


def apply_suspension_overrides(
    df: pd.DataFrame,
    *,
    market_dislocation: pd.Series | None = None,
    state_cols: tuple[str, ...] = (
        "rs_state",
        "momentum_state",
        "risk_state",
        "volume_state",
    ),
) -> pd.DataFrame:
    """Override primitive states with suspension labels where gates fail.

    ``market_dislocation`` is a per-row bool Series indexed identically to
    ``df``. M2 backfill passes None (M3 hasn't run yet); from M3 onward the
    nightly pipeline reads this from the previous day's market-regime row.
    """
    out = df.copy()

    history_fail = ~out["history_gate_pass"].fillna(False)
    liquidity_fail = ~out["liquidity_gate_pass"].fillna(False)

    if market_dislocation is None:
        dislocation = pd.Series(False, index=out.index)
    else:
        dislocation = market_dislocation.reindex(out.index).fillna(False).astype(bool)

    for col in state_cols:
        out[col] = np.select(
            [history_fail, liquidity_fail, dislocation],
            list(SUSPENSION_PRIORITY),
            default=out[col].astype(object),
        )
    return out
