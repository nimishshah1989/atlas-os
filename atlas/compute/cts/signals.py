from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import numpy as np
import pandas as pd

from atlas.compute.cts.primitives import add_atr14, add_trp, add_volume_ratio
from atlas.compute.cts.stage import classify_stage

_DEFAULT_PPC_WEIGHTS: dict[str, float] = {
    "trp": 0.35,
    "vol": 0.35,
    "rs": 0.20,
    "stage": 0.10,
}


def detect_signals(
    df: pd.DataFrame,
    *,
    thresholds: Mapping[str, Decimal],
    ppc_weights: dict[str, float] | None = None,
    group_col: str = "instrument_id",
) -> pd.DataFrame:
    """Detect PPC, NPC, and Contraction signals on the input OHLCV universe.

    Input DataFrame must have: instrument_id, date, open, high, low,
    close, volume, rs_pctile_cross_sector (float 0–1).

    Appends: is_ppc, ppc_strength, is_npc, npc_strength, is_contraction,
    is_trigger_bar, trigger_level, atr_14, atr_slope, trp, avg_trp,
    trp_ratio, vol_ratio, stage, sma_150, sma_150_slope, is_stage1b,
    pp_vol_threshold, is_pp_volume, cts_conviction_score, cts_action_confidence.

    All boolean columns default to False on insufficient history (< 14 bars).
    ppc_strength / npc_strength are float in [0, 1], masked to pd.NA when the
    corresponding signal is False.

    Quality gates (PPC): stage==2, rs_pctile_cross_sector >= cts_ppc_rs_min,
    Morales pocket-pivot volume, close within cts_ppc_high_proximity_pct% of
    52-bar highest high.

    Quality gates (NPC): stage >= cts_npc_stage_max (3 or 4),
    rs_pctile_cross_sector <= cts_npc_rs_max, Morales pocket-pivot volume.
    """
    # Import inside function body to avoid circular import at module level
    from atlas.compute.cts.primitives import add_pocket_pivot_volume as _add_ppv

    weights = ppc_weights or _DEFAULT_PPC_WEIGHTS
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError(f"ppc_weights must sum to 1.0, got {sum(weights.values()):.6f}")

    out = add_trp(df, group_col=group_col)
    out = add_volume_ratio(out, group_col=group_col)
    out = add_atr14(out, group_col=group_col)
    out = classify_stage(out, thresholds=thresholds, group_col=group_col)

    # Add Morales pocket-pivot volume
    pp_vol_window = (
        int(thresholds["cts_ppc_pp_vol_window"]) if "cts_ppc_pp_vol_window" in thresholds else 10
    )
    out = _add_ppv(out, group_col=group_col, window=pp_vol_window)

    # Threshold extraction — float() at boundary; arithmetic uses float, not Decimal
    ppc_range = float(thresholds["cts_ppc_range_multiplier"])
    ppc_close = float(thresholds["cts_ppc_close_pct"])
    npc_range = float(thresholds["cts_npc_range_multiplier"])
    npc_close = float(thresholds["cts_npc_close_pct"])
    con_bars = int(thresholds["cts_contraction_bars"])
    con_res = float(thresholds["cts_contraction_resistance_pct"])
    con_high_bars = int(thresholds["cts_contraction_highest_high_bars"])

    # Quality filter thresholds
    ppc_stage_min = int(thresholds["cts_ppc_stage_min"]) if "cts_ppc_stage_min" in thresholds else 2
    npc_stage_max = int(thresholds["cts_npc_stage_max"]) if "cts_npc_stage_max" in thresholds else 3
    ppc_rs_min = float(thresholds["cts_ppc_rs_min"]) if "cts_ppc_rs_min" in thresholds else 0.60
    npc_rs_max = float(thresholds["cts_npc_rs_max"]) if "cts_npc_rs_max" in thresholds else 0.40
    ppc_proximity_pct = (
        float(thresholds["cts_ppc_high_proximity_pct"])
        if "cts_ppc_high_proximity_pct" in thresholds
        else 15.0
    )

    # --- Candle geometry (vectorised) ---
    candle_range = (out["high"] - out["low"]).replace(0, pd.NA)
    # close_pct: fraction of bar range where close landed
    close_pct = (out["close"] - out["low"]) / candle_range

    # --- RS series (used in PPC and NPC gates) ---
    rs_col = "rs_pctile_cross_sector"
    rs_series = (
        out[rs_col].fillna(0.0) if rs_col in out.columns else pd.Series(0.0, index=out.index)
    )

    # --- 52-bar highest high for proximity gate ---
    out["_high_52bar"] = out.groupby(group_col, observed=True)["high"].transform(
        lambda s: s.rolling(52, min_periods=20).max()
    )
    within_proximity = out["close"] >= out["_high_52bar"] * (1 - ppc_proximity_pct / 100)

    # --- PPC detection ---
    # Pocket Pivot Candle: wide range, close in upper portion, Morales volume, green,
    # Stage 2, strong RS, within 15% of 52-bar high
    out["is_ppc"] = (
        (out["trp_ratio"] >= ppc_range)
        & (close_pct >= ppc_close)
        & out["is_pp_volume"].fillna(False)
        & (out["close"] > out["open"])
        & (out["stage"] == ppc_stage_min)
        & (rs_series >= ppc_rs_min)
        & within_proximity.fillna(False)
    ).fillna(False)

    # --- NPC detection ---
    # Negative Pivot Candle: wide range, close in lower portion, Morales volume, red,
    # Stage 3 or 4, weak RS
    out["is_npc"] = (
        (out["trp_ratio"] >= npc_range)
        & (close_pct <= npc_close)
        & out["is_pp_volume"].fillna(False)
        & (out["close"] < out["open"])
        & (
            pd.Series(pd.to_numeric(out["stage"], errors="coerce"), index=out.index)
            .fillna(0)
            .astype(int)
            >= npc_stage_max
        )
        & (rs_series <= npc_rs_max)
    ).fillna(False)

    # --- Strength composites (float in [0, 1]) ---
    # Each component normalised to [0, 1]
    trp_component = (out["trp_ratio"] / 3.0).clip(0, 1)
    vol_component = (out["vol_ratio"] / 4.0).clip(0, 1)
    rs_component = (
        out[rs_col].clip(0, 1) if rs_col in out.columns else pd.Series(0.0, index=out.index)
    )
    stage2_component = (out["stage"] == 2).astype(float)
    stage4_component = (out["stage"] == 4).astype(float)

    raw_ppc_strength = (
        weights["trp"] * trp_component
        + weights["vol"] * vol_component
        + weights["rs"] * rs_component
        + weights["stage"] * stage2_component
    )
    raw_npc_strength = (
        weights["trp"] * trp_component
        + weights["vol"] * vol_component
        + weights["rs"] * (1.0 - rs_component)
        + weights["stage"] * stage4_component
    )

    # Mask strength values — only meaningful when the signal fires
    out["ppc_strength"] = raw_ppc_strength.where(out["is_ppc"], other=pd.NA)
    out["npc_strength"] = raw_npc_strength.where(out["is_npc"], other=pd.NA)

    # --- Contraction detection (per-group rolling) ---
    out = _add_contraction(out, con_bars=con_bars, con_res=con_res, con_high_bars=con_high_bars)

    # --- Conviction score ---
    out = _add_conviction_score(out)

    # Clean up temp column
    out.drop(columns=["_high_52bar"], inplace=True, errors="ignore")

    return out


def _add_conviction_score(df: pd.DataFrame) -> pd.DataFrame:
    """Append cts_conviction_score (0-100) and cts_action_confidence (bool).

    Stock-level only. Sector (+10) and regime (+10) bonuses are injected in
    backfill_cts_bulk.py after sector pivot is computed. Max here = 80.

    Stage component (0-30):  stage==2 → 30, is_stage1b → 15, stage==3 → 5
    Signal component (0-30): ppc_strength * 30 (only when is_ppc is True)
    RS component (0-20):     rs_pctile_cross_sector * 20
    """
    out = df.copy()

    # Stage component
    stage_pts = pd.Series(0.0, index=out.index)
    stage_pts[out["stage"] == 2] = 30.0
    is_stage1b = (
        out["is_stage1b"] if "is_stage1b" in out.columns else pd.Series(False, index=out.index)
    )
    stage_pts[is_stage1b.fillna(False)] = 15.0
    stage_pts[out["stage"] == 3] = 5.0

    # Signal component: only on PPC bars
    signal_pts = out["ppc_strength"].fillna(0.0) * 30.0

    # RS component
    rs_col = "rs_pctile_cross_sector"
    rs_pts = (
        out[rs_col].fillna(0.0) * 20.0 if rs_col in out.columns else pd.Series(0.0, index=out.index)
    )

    out["cts_conviction_score"] = (stage_pts + signal_pts + rs_pts).clip(0, 80)

    rs_ok = (
        out[rs_col].fillna(0.0) >= 0.60
        if rs_col in out.columns
        else pd.Series(False, index=out.index)
    )
    out["cts_action_confidence"] = (
        (out["stage"] == 2)
        & out["is_ppc"].fillna(False)
        & rs_ok
        & (out["cts_conviction_score"] >= 45)  # 45/80 before sector+regime bonus
    )
    return out


def _add_contraction(
    df: pd.DataFrame,
    *,
    con_bars: int,
    con_res: float,
    con_high_bars: int,
) -> pd.DataFrame:
    """Append is_contraction, is_trigger_bar, trigger_level.

    Three conditions per group (vectorised rolling within group):
    1. atr_slope < 0 OR atr_slope is NaN (ATR compressing or insufficient history)
       — fillna(0) means unknown ATR direction doesn't block the signal on short
       histories; on adequate history the real slope is decisive.
    2. >= 60% of bar-to-bar range transitions are narrowing over con_bars window
    3. close within con_res% of con_high_bars highest high

    is_trigger_bar mirrors is_contraction (trigger = first contraction bar).
    trigger_level = bar high on trigger bar, NaN otherwise.
    """
    out = df.copy()

    def _contraction_for_group(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()

        # Condition 1: volatility compressing
        # fillna(0): NaN atr_slope (pre-history) becomes 0, so 0 < 0 = False → cond_atr not met.
        # In practice the con_high_bars window is the binding constraint,
        # so contraction cannot fire before ATR history is established anyway.
        cond_atr = g["atr_slope"].fillna(0) < 0

        bar_range = g["high"] - g["low"]

        def _narrowing_count(window: np.ndarray) -> float:
            """Count how many bar-to-bar transitions are narrowing (or flat +5% tolerance)."""
            if len(window) < 2:
                return 0.0
            return float(np.sum(window[1:] <= window[:-1] * 1.05))

        # Condition 2: range tightening — ≥60% of transitions in window are narrowing
        narrowing = bar_range.rolling(con_bars, min_periods=con_bars).apply(
            _narrowing_count, raw=True
        )
        cond_narrow = narrowing >= (con_bars - 1) * 0.6

        # Condition 3: price proximity to highest high (resistance coiling)
        highest_high = g["high"].rolling(con_high_bars, min_periods=con_high_bars).max()
        dist_pct = (highest_high - g["close"]) / highest_high.replace(0, pd.NA) * 100
        cond_prox = dist_pct <= con_res

        is_con = cond_atr & cond_narrow & cond_prox
        g["is_contraction"] = is_con.fillna(False)
        g["is_trigger_bar"] = g["is_contraction"]
        g["trigger_level"] = np.where(g["is_contraction"], g["high"], np.nan)
        return g

    # pandas 3.0 removed include_groups=True. The groupby column is excluded
    # from g inside the apply function. Restore it from out's index after apply.
    result = out.groupby("instrument_id", group_keys=False, observed=True).apply(
        _contraction_for_group
    )
    if "instrument_id" not in result.columns:
        result["instrument_id"] = out.loc[result.index, "instrument_id"].values
    result = result.reset_index(drop=True)
    return result
