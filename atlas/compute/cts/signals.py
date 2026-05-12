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
    trp_ratio, vol_ratio, stage, sma_150, sma_150_slope, is_stage1b.

    All boolean columns default to False on insufficient history (< 14 bars).
    ppc_strength / npc_strength are float in [0, 1], masked to pd.NA when the
    corresponding signal is False.
    """
    weights = ppc_weights or _DEFAULT_PPC_WEIGHTS

    out = add_trp(df, group_col=group_col)
    out = add_volume_ratio(out, group_col=group_col)
    out = add_atr14(out, group_col=group_col)
    out = classify_stage(out, thresholds=thresholds, group_col=group_col)

    # Threshold extraction — float() at boundary; arithmetic uses float, not Decimal
    ppc_range = float(thresholds["cts_ppc_range_multiplier"])
    ppc_close = float(thresholds["cts_ppc_close_pct"])
    ppc_vol = float(thresholds["cts_ppc_volume_multiplier"])
    npc_range = float(thresholds["cts_npc_range_multiplier"])
    npc_close = float(thresholds["cts_npc_close_pct"])
    npc_vol = float(thresholds["cts_npc_volume_multiplier"])
    con_bars = int(thresholds["cts_contraction_bars"])
    con_res = float(thresholds["cts_contraction_resistance_pct"])

    # --- Candle geometry (vectorised) ---
    candle_range = (out["high"] - out["low"]).replace(0, pd.NA)
    # close_pct: fraction of bar range where close landed
    close_pct = (out["close"] - out["low"]) / candle_range

    # --- PPC detection ---
    # Pocket Pivot Candle: wide range, close in upper portion, heavy volume, green
    out["is_ppc"] = (
        (out["trp_ratio"] >= ppc_range)
        & (close_pct >= ppc_close)
        & (out["vol_ratio"] >= ppc_vol)
        & (out["close"] > out["open"])
    ).fillna(False)

    # --- NPC detection ---
    # Negative Pivot Candle: wide range, close in lower portion, heavy volume, red
    out["is_npc"] = (
        (out["trp_ratio"] >= npc_range)
        & (close_pct <= npc_close)
        & (out["vol_ratio"] >= npc_vol)
        & (out["close"] < out["open"])
    ).fillna(False)

    # --- Strength composites (float in [0, 1]) ---
    rs_col = "rs_pctile_cross_sector" if "rs_pctile_cross_sector" in out.columns else None

    # Each component normalised to [0, 1]
    trp_component = (out["trp_ratio"] / 3.0).clip(0, 1)
    vol_component = (out["vol_ratio"] / 4.0).clip(0, 1)
    rs_component = out[rs_col].clip(0, 1) if rs_col else pd.Series(0.0, index=out.index)
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
    out = _add_contraction(out, con_bars=con_bars, con_res=con_res)
    return out


def _add_contraction(
    df: pd.DataFrame,
    *,
    con_bars: int,
    con_res: float,
) -> pd.DataFrame:
    """Append is_contraction, is_trigger_bar, trigger_level.

    Three conditions per group (vectorised rolling within group):
    1. atr_slope < 0 OR atr_slope is NaN (ATR compressing or insufficient history)
       — fillna(0) means unknown ATR direction doesn't block the signal on short
       histories; on adequate history the real slope is decisive.
    2. >= 60% of bar-to-bar range transitions are narrowing over con_bars window
    3. close within con_res% of 50-bar highest high

    is_trigger_bar mirrors is_contraction (trigger = first contraction bar).
    trigger_level = bar high on trigger bar, NaN otherwise.
    """
    out = df.copy()

    def _contraction_for_group(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()

        # Condition 1: volatility compressing
        # fillna(0) → unknown ATR slope treated as "not declining" only when truly NaN
        # (pre-ATR history). When history is sufficient, real slope is used.
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
        cond_narrow = narrowing >= con_bars * 0.6

        # Condition 3: price proximity to 50-bar highest high (resistance coiling)
        highest_high = g["high"].rolling(50, min_periods=50).max()
        dist_pct = (highest_high - g["close"]) / highest_high.replace(0, pd.NA) * 100
        cond_prox = dist_pct <= con_res

        is_con = cond_atr & cond_narrow & cond_prox
        g["is_contraction"] = is_con.fillna(False)
        g["is_trigger_bar"] = g["is_contraction"]
        g["trigger_level"] = np.where(g["is_contraction"], g["high"], np.nan)
        return g

    result = (
        out.groupby("instrument_id", group_keys=False, observed=True)
        .apply(_contraction_for_group, include_groups=False)
        .reset_index(drop=True)
    )
    return result
