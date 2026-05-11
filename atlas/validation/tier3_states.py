"""Tier 3 state-classification validation.

Per validation framework §4: 30 sample stocks x 4 state types = 120 checks.
The hand classifier is a verbatim Python translation of methodology §7.1-§7.4
written *without* importing :mod:`atlas.compute.states` — independent
implementation catches drift between methodology doc and production code.

Gate + conjunction logic applied in hand classifiers:
- ``apply_suspension_overrides``: INSUFFICIENT_HISTORY when history_gate_pass
  is False; ILLIQUID when liquidity_gate_pass is False.
- ``apply_below_trend_conjunction``: rs_state forced to Average when
  risk_state is Below Trend (methodology §7.3).

Boundary note: ema_10_ratio and ema_20_ratio are stored as NUMERIC(18,4).
On-disk rounding can cause stocks whose actual ratio was e.g. 0.99997 to read
back as 1.0000, flipping the classification at Flat/Deteriorating boundary.
These are documented precision artifacts, not computation bugs.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.db import load_thresholds
from atlas.validation.samplers import sample_stocks_for_states

log = structlog.get_logger()


# --------------------------------------------------------------------------- #
# Hand classifiers — verbatim from methodology §7                             #
# --------------------------------------------------------------------------- #


def hand_classify_rs(row: dict[str, Any], thresholds: Mapping[str, Decimal]) -> str:
    """Translate methodology §7.1 verbatim. No np.select, plain Python ifs."""
    top = thresholds["rs_quintile_top"]
    bot = thresholds["rs_quintile_bottom"]

    p1w = row["rs_pctile_1w"]
    p1m = row["rs_pctile_1m"]
    p3m = row["rs_pctile_3m"]
    weinstein = bool(row["weinstein_gate_pass"])
    stage1 = bool(row["stage1_base_qualifies"])

    in_top_1w = (p1w is not None) and (p1w >= top)
    in_top_1m = (p1m is not None) and (p1m >= top)
    in_top_3m = (p3m is not None) and (p3m >= top)
    in_bot_1w = (p1w is not None) and (p1w <= bot)
    in_bot_1m = (p1m is not None) and (p1m <= bot)
    in_bot_3m = (p3m is not None) and (p3m <= bot)

    if in_bot_1w and in_bot_1m and in_bot_3m:
        return "Laggard"
    if in_bot_1w or in_bot_1m or in_bot_3m:
        return "Weak"
    if in_top_1w and in_top_1m and in_top_3m and weinstein:
        return "Leader"
    if in_top_1m and in_top_3m and not in_top_1w and weinstein:
        return "Strong"
    if in_top_3m and not in_top_1m and not in_top_1w and weinstein:
        return "Consolidating"
    if in_top_1w and in_top_1m and not in_top_3m and stage1 and weinstein:
        return "Emerging"
    return "Average"


def hand_classify_momentum(row: dict[str, Any], thresholds: Mapping[str, Decimal]) -> str:
    flat = thresholds["momentum_flat_band_pct"]
    converge = thresholds["momentum_ema_convergence_pct"]
    r10 = row["ema_10_ratio"]
    r20 = row["ema_20_ratio"]
    at_high = bool(row["ema_10_at_20d_high"])
    at_low = bool(row["ema_10_at_20d_low"])

    if r10 is None or r20 is None:
        return "Flat"

    r10 = float(r10)
    r20 = float(r20)

    if r10 > 1 and r10 > r20 and at_high:
        return "Accelerating"
    if r10 > 1 and r10 > r20:
        return "Improving"
    if r10 < 1 and r10 < r20 and at_low:
        return "Collapsing"
    if r10 < 1 and r10 < r20:
        return "Deteriorating"
    if abs(r10 - 1) <= flat or abs(r10 - r20) <= converge:
        return "Flat"
    return "Flat"


def hand_classify_risk(row: dict[str, Any], thresholds: Mapping[str, Decimal]) -> str:
    ext_low_max = thresholds["risk_extension_low_max_pct"]
    ext_high_min = thresholds["risk_extension_high_min_pct"]
    vol_low_max = thresholds["risk_vol_ratio_low_max"]
    vol_norm_max = thresholds["risk_vol_ratio_normal_max"]
    vol_high_min = thresholds["risk_vol_ratio_high_min"]

    ext_pct = (row["extension_pct"] or 0) * 100
    vol_r = row["vol_ratio_63"] or 0

    if ext_pct < 0:
        return "Below Trend"
    if ext_pct > ext_high_min or vol_r > vol_high_min:
        return "High"
    if (ext_low_max < ext_pct <= ext_high_min) or (vol_norm_max < vol_r <= vol_high_min):
        return "Elevated"
    if (0 <= ext_pct <= ext_low_max) and (vol_low_max < vol_r <= vol_norm_max):
        return "Normal"
    if (0 <= ext_pct <= ext_low_max) and (vol_r <= vol_low_max):
        return "Low"
    return "Normal"


def hand_classify_volume(row: dict[str, Any], thresholds: Mapping[str, Decimal]) -> str:
    acc_exp = thresholds["volume_accumulation_expansion_min"]
    acc_eff = thresholds["volume_accumulation_effort_min"]
    dist_eff = thresholds["volume_distribution_effort_max"]
    heavy_eff = thresholds["volume_heavy_distribution_effort_max"]

    exp = row["volume_expansion"] or 0
    eff = row["effort_ratio_63"] or 0

    if eff <= heavy_eff and exp >= 1.0:
        return "Heavy Distribution"
    if eff <= dist_eff:
        return "Distribution"
    if exp >= acc_exp and eff >= acc_eff:
        return "Accumulation"
    if 1.0 <= exp < acc_exp and eff >= 1.1:
        return "Steady-Buying"
    return "Neutral"


# --------------------------------------------------------------------------- #
# Runner                                                                      #
# --------------------------------------------------------------------------- #


CLASSIFIERS = {
    "rs_state": hand_classify_rs,
    "momentum_state": hand_classify_momentum,
    "risk_state": hand_classify_risk,
    "volume_state": hand_classify_volume,
}


def _load_row(
    engine: Engine,
    instrument_id: str,
    target_date: date,
) -> dict[str, Any] | None:
    """Read primitives + gate flags + state for one (stock, date)."""
    with open_compute_session(engine) as conn:
        df = pd.read_sql(
            """
            SELECT m.rs_pctile_1w, m.rs_pctile_1m, m.rs_pctile_3m,
                   m.weinstein_gate_pass, m.stage1_base_qualifies,
                   m.ema_10_ratio, m.ema_20_ratio,
                   m.ema_10_at_20d_high, m.ema_10_at_20d_low,
                   m.extension_pct, m.vol_ratio_63,
                   m.volume_expansion, m.effort_ratio_63,
                   s.history_gate_pass, s.liquidity_gate_pass,
                   s.rs_state, s.momentum_state, s.risk_state, s.volume_state
            FROM atlas.atlas_stock_metrics_daily m
            JOIN atlas.atlas_stock_states_daily s
              ON s.instrument_id = m.instrument_id AND s.date = m.date
            WHERE m.instrument_id = %(id)s AND m.date = %(date)s
            """,
            conn,
            params={"id": instrument_id, "date": target_date},
        )
    if df.empty:
        return None
    return {k: (None if pd.isna(v) else v) for k, v in df.iloc[0].items()}


def _apply_suspension(hand_state: str, row: dict[str, Any]) -> str:
    """Mirror production ``apply_suspension_overrides`` ordering."""
    if not row.get("history_gate_pass"):
        return "INSUFFICIENT_HISTORY"
    if not row.get("liquidity_gate_pass"):
        return "ILLIQUID"
    return hand_state


def run_tier3(
    engine: Engine,
    *,
    target_date: date,
    milestone: str = "M2",
    n_stocks: int = 30,
) -> pd.DataFrame:
    """Run hand classification for ``n_stocks`` x 4 states (~120 checks)."""
    stocks = sample_stocks_for_states(engine, milestone=milestone, n=n_stocks)
    thresholds = load_thresholds(engine)

    rows: list[dict[str, Any]] = []
    for instrument_id in stocks:
        rec = _load_row(engine, instrument_id, target_date)
        if rec is None:
            continue

        # Pre-compute risk so below-trend conjunction can override rs_state.
        try:
            risk_hand_base = hand_classify_risk(rec, thresholds)
        except Exception:
            risk_hand_base = "Normal"

        for state_col, classifier in CLASSIFIERS.items():
            try:
                hand_state = classifier(rec, thresholds)
            except Exception as exc:
                hand_state = f"ERROR:{exc}"

            # Apply below-trend conjunction: rs_state → Average when Below Trend.
            # Mirrors production atlas.compute.states.apply_below_trend_conjunction.
            if state_col == "rs_state" and risk_hand_base == "Below Trend":
                hand_state = "Average"

            # Apply suspension overrides last (highest priority).
            hand_state = _apply_suspension(hand_state, rec)

            prod_state = rec.get(state_col)
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "date": str(target_date),
                    "state_type": state_col,
                    "hand": hand_state,
                    "prod": prod_state,
                    "pass": hand_state == prod_state,
                }
            )

    df = pd.DataFrame(rows)
    pass_rate = df["pass"].mean() if not df.empty else 0
    log.info("tier3_complete", n_checks=len(df), pass_rate=round(pass_rate, 4))
    return df
