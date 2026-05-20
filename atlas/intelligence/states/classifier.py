"""State classifier — applies rule-skeleton with DB-loaded θ thresholds.

Per (stock, day) → one of 7 states + within-state rank. Each state has its
own predicate function (classify_uninvestable, classify_stage_4, etc.).
The orchestrator (classify_state_panel, added in Task 1.6) calls them in
priority order and assigns the first matching state.

Tasks 1.4 ships Uninvestable + Stage 4. Task 1.5 adds Stage 1, 2A, 2B, 2C, 3.
Task 1.6 adds the panel orchestrator.
"""

from __future__ import annotations

import math

import pandas as pd

from atlas.intelligence.states.thresholds import ThresholdValue
from atlas.intelligence.states.thresholds import get as get_threshold


def _is_nan(x: float) -> bool:
    """True if x is NaN or None."""
    return x is None or (isinstance(x, float) and math.isnan(x))


def classify_uninvestable(
    liquidity_score: float,
    data_gap_count: int,
    close: float,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Filter: stock unsuitable for trading. Returns True if uninvestable.

    Reasons (any one is sufficient):
      - 50d avg ₹ volume below θ_liq
      - More than θ_gap missing trading days in trailing 252d
      - Close price below θ_min_price (penny-stock filter)
    """
    if liquidity_score < get_threshold(thresholds, "theta_liq", "uninvestable"):
        return True
    if data_gap_count > get_threshold(thresholds, "theta_gap", "uninvestable"):
        return True
    if close < get_threshold(thresholds, "theta_min_price", "uninvestable"):
        return True
    return False


def classify_stage_4(
    close: float,
    sma_150: float,
    sma_200: float,
    sma_150_slope: float,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 4 (Decline): downtrend confirmed.

    All three must hold:
      - close < sma_150 < sma_200 (inverted MA stack)
      - sma_150_slope < 0 (long trend rolling over)
      - close < theta_decline_floor * sma_200 (price meaningfully below long MA)
    """
    if any(_is_nan(v) for v in (close, sma_150, sma_200, sma_150_slope)):
        return False
    floor = get_threshold(thresholds, "theta_decline_floor", "stage_4")
    return close < sma_150 < sma_200 and sma_150_slope < 0 and close < floor * sma_200


def classify_stage_1(
    close: float,
    sma_150: float,
    atr_14: float,
    atr_14_252d_avg: float,
    low_252_age_days: int,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 1 (Base): consolidation.

    Caller responsibility: only invoke when NOT in stage 2/3/4. Stage 1 is
    the residual.

    All three must hold:
      - |close - sma_150| / sma_150 < theta_base_tightness  (price hugs the long MA)
      - atr_14 / atr_14_252d_avg < theta_contraction         (IC-validated: vol contracted vs year)
      - low_252_age_days >= theta_min_recovery_days          (past the bottom)

    IC note: atr_14/atr_14_252d_avg has IR -0.48 at 63d — contraction predicts high forward
    returns. Replaces old atr_14/close (IR -0.18, decorative).
    atr_14_252d_avg NaN-guarded: if unavailable (< 266 days of history), Stage 1 returns False.
    """
    if any(_is_nan(v) for v in (close, sma_150, atr_14)):
        return False
    if sma_150 <= 0 or close <= 0:
        return False
    # NaN or zero denominator guard: without a valid 252d avg, we cannot confirm contraction.
    if _is_nan(atr_14_252d_avg) or atr_14_252d_avg <= 0:
        return False
    tightness = abs(close - sma_150) / sma_150
    contraction_ratio = atr_14 / atr_14_252d_avg
    return (
        tightness < get_threshold(thresholds, "theta_base_tightness", "stage_1")
        and contraction_ratio < get_threshold(thresholds, "theta_contraction", "stage_1")
        and low_252_age_days >= get_threshold(thresholds, "theta_min_recovery_days", "stage_1")
    )


def classify_stage_2a(
    prior_state: str,
    close: float,
    sma_50: float,
    sma_150: float,
    sma_200: float,
    sma_200_slope: float,
    max_close_60d: float,
    rs_rank_12m: float,
    days_in_stage_2: int,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 2A (Fresh Breakout). Only fires on transition from Stage 1 or 4.

    Active gates (IC-validated):
      - prior_state in ("stage_1", "stage_4") — transition gate
      - close > sma_50 > sma_150 > sma_200 — MA stack (uptrend aligned)
      - sma_200_slope > 0 — rising long-term trend
      - rs_rank_12m * 100 >= theta_rs — relative strength filter
      - days_in_stage_2 <= theta_fresh_days — freshness window

    REMOVED gate (Wave 4C Task 3):
      close >= theta_base_breakout * max_close_60d (breakout ratio)
      Reason: IC validation showed IR 0.107/0.145 — below the 0.2 weak floor.
      Top-breakout-ratio quintile underperforms the bottom (mildly anti-predictive).
      theta_base_breakout row kept dormant in atlas_thresholds (no migration needed).
      The breakout_ratio factor in tune_catalog.py is retained as a catalogued factor.
      NOTE: Stage-2A IC re-validation is required (Task 5) before this ships.

    IC note: volume_today/volume_50d_avg had IR 0.15 at 21d — decorative.
    Volume requirement removed in migration 078; volume columns remain in the
    feature DF for other uses (OBV, liquidity_score) but are not checked here.
    """
    if prior_state not in ("stage_1", "stage_4"):
        return False
    if any(_is_nan(v) for v in (close, sma_50, sma_150, sma_200, sma_200_slope, rs_rank_12m)):
        return False
    # max_close_60d is still accepted as a parameter (used by callers / feature panel)
    # but is no longer used as a gate here — the breakout_ratio gate was removed.
    _ = max_close_60d
    return (
        close > sma_50 > sma_150 > sma_200
        and sma_200_slope > 0
        and rs_rank_12m * 100 >= get_threshold(thresholds, "theta_rs", "stage_2a")
        and days_in_stage_2 <= get_threshold(thresholds, "theta_fresh_days", "stage_2a")
    )


def classify_stage_2b(
    in_stage_2: bool,
    days_in_stage_2: int,
    distribution_days_5d: int,
    close: float,
    sma_50: float,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 2B (Confirmed): mid-range of an established Stage 2.

    theta_fresh_days is keyed under ("theta_fresh_days", "stage_2a") by design —
    there is only one fresh_days value in the system; Stage 2B borrows it.
    """
    if not in_stage_2 or _is_nan(close) or _is_nan(sma_50):
        return False
    fresh = get_threshold(thresholds, "theta_fresh_days", "stage_2a")
    confirmed = get_threshold(thresholds, "theta_confirmed_days", "stage_2b")
    return fresh < days_in_stage_2 <= confirmed and distribution_days_5d == 0 and close > sma_50


def classify_stage_2c(
    in_stage_2: bool,
    days_in_stage_2: int,
    close: float,
    sma_50: float,
    atr_14: float,
    atr_14_50d_avg: float,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 2C (Mature): late-stage uptrend; reversion risk rising.

    True if ANY ONE of three signals fires:
      - days_in_stage_2 > theta_confirmed_days  (time-extended)
      - close / sma_50 > theta_extension         (price-extended)
      - atr_14 / atr_14_50d_avg > theta_atr_expansion  (vol-expanded)
    """
    if not in_stage_2:
        return False
    confirmed = get_threshold(thresholds, "theta_confirmed_days", "stage_2b")
    extension = get_threshold(thresholds, "theta_extension", "stage_2c")
    atr_expansion = get_threshold(thresholds, "theta_atr_expansion", "stage_2c")
    overextended = sma_50 > 0 and not _is_nan(close) and (close / sma_50 > extension)
    vol_expanded = (
        atr_14_50d_avg > 0 and not _is_nan(atr_14) and (atr_14 / atr_14_50d_avg > atr_expansion)
    )
    return days_in_stage_2 > confirmed or overextended or vol_expanded


def classify_stage_3(
    prior_state: str,
    close: float,
    sma_50: float,
    sma_50_slope: float,
    distribution_days_25d: int,
    obv_slope_50d: float,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 3 (Top): was in stage 2, now showing topping signs.

    Both must hold:
      - topping signal: close < sma_50 OR sma_50_slope < 0 OR obv_slope_50d < theta_obv_slope_neg
      - distribution_days_25d >= theta_distribution

    IC note: obv_slope_50d has IR -0.43 at 63d (validated_inverse). Falling OBV is
    an alternative topping trigger — a held Stage 2 stock with deteriorating OBV is
    starting to top. Added as an OR to the existing price-condition conjuncts.
    obv_slope_50d NaN-guarded: NaN means the 50-bar warm-up hasn't completed; the OBV
    branch is simply skipped (conservative — requires price signal to trigger Stage 3).
    """
    if prior_state not in ("stage_2a", "stage_2b", "stage_2c"):
        return False
    if any(_is_nan(v) for v in (close, sma_50, sma_50_slope)):
        return False
    obv_neg_threshold = get_threshold(thresholds, "theta_obv_slope_neg", "stage_3")
    # OBV topping: only applies when obv_slope_50d is a valid number.
    obv_topping = (not _is_nan(obv_slope_50d)) and (obv_slope_50d < obv_neg_threshold)
    topping_price = close < sma_50 or sma_50_slope < 0 or obv_topping
    enough_distribution = distribution_days_25d >= get_threshold(
        thresholds, "theta_distribution", "stage_3"
    )
    return topping_price and enough_distribution


# ---------------------------------------------------------------------------
# Panel orchestrator (Task 1.6)
# ---------------------------------------------------------------------------


def _value_or_nan(v: object) -> float:
    """Return float(v) or NaN if v is None, NaN, or unconvertible."""
    if v is None:
        return float("nan")
    try:
        f = float(v)  # type: ignore[arg-type]
        return f
    except (TypeError, ValueError):
        return float("nan")


def classify_state_panel(
    features: pd.DataFrame,
    thresholds: dict[tuple[str, str], ThresholdValue],
    classifier_version: str,
) -> pd.DataFrame:
    """Apply state classifier to a (instrument_id × date) feature panel.

    Required feature columns:
      instrument_id, date, close, sma_50, sma_150, sma_200, sma_50_slope,
      sma_150_slope, sma_200_slope, atr_14, atr_14_50d_avg, atr_14_252d_avg,
      obv_slope_50d, volume, volume_50d_avg, max_close_60d, rs_rank_12m,
      distribution_days_25d, distribution_days_5d, low_252_age_days,
      liquidity_score, data_gap_count.

    New in migration 078:
      atr_14_252d_avg — denominator for Stage 1 contraction check
      obv_slope_50d   — OBV slope for Stage 3 topping signal

    Returns DataFrame with columns:
      instrument_id, date, state, prior_state, state_since_date, dwell_days,
      classifier_version, rs_rank_12m, close_vs_sma_50, close_vs_sma_150,
      close_vs_sma_200, sma_200_slope, volume_ratio_50d, distribution_days.

    Priority order (first match wins):
      Uninvestable → Stage 4 → Stage 3 → Stage 2A → Stage 2C → Stage 2B → Stage 1
    """
    # Process rows per-instrument in chronological order.
    features = features.sort_values(["instrument_id", "date"]).reset_index(drop=True)

    prior_state_per_instr: dict[str, str] = {}
    state_since_per_instr: dict[str, object] = {}
    days_in_stage_2_per_instr: dict[str, int] = {}

    rows = []
    for _, r in features.iterrows():
        iid = r["instrument_id"]
        prior = prior_state_per_instr.get(iid, "stage_1")

        # Carry forward the in-stage-2 day counter.
        prev_days_in_stage_2 = days_in_stage_2_per_instr.get(iid, 0)
        is_currently_in_2 = prior in ("stage_2a", "stage_2b", "stage_2c")
        days_in_stage_2 = prev_days_in_stage_2 + 1 if is_currently_in_2 else 0

        close = _value_or_nan(r["close"])
        sma_50 = _value_or_nan(r["sma_50"])
        sma_150 = _value_or_nan(r["sma_150"])
        sma_200 = _value_or_nan(r["sma_200"])
        sma_50_slope = _value_or_nan(r["sma_50_slope"])
        sma_150_slope = _value_or_nan(r["sma_150_slope"])
        sma_200_slope = _value_or_nan(r["sma_200_slope"])
        atr_14 = _value_or_nan(r["atr_14"])
        atr_14_50d_avg = _value_or_nan(r["atr_14_50d_avg"])
        atr_14_252d_avg = _value_or_nan(r["atr_14_252d_avg"])
        obv_slope_50d = _value_or_nan(r["obv_slope_50d"])
        rs_rank_12m_val = _value_or_nan(r["rs_rank_12m"])
        max_close_60d = _value_or_nan(r["max_close_60d"])
        volume = _value_or_nan(r["volume"])
        volume_50d_avg = _value_or_nan(r["volume_50d_avg"])
        liquidity = _value_or_nan(r["liquidity_score"])
        dist_25 = 0 if pd.isna(r["distribution_days_25d"]) else int(r["distribution_days_25d"])
        dist_5 = 0 if pd.isna(r["distribution_days_5d"]) else int(r["distribution_days_5d"])
        low_age = 0 if pd.isna(r["low_252_age_days"]) else int(r["low_252_age_days"])
        data_gap = 0 if pd.isna(r["data_gap_count"]) else int(r["data_gap_count"])

        # Priority-ordered classification.
        if classify_uninvestable(liquidity, data_gap, close, thresholds):
            state = "uninvestable"
        elif classify_stage_4(close, sma_150, sma_200, sma_150_slope, thresholds):
            state = "stage_4"
        elif classify_stage_3(
            prior, close, sma_50, sma_50_slope, dist_25, obv_slope_50d, thresholds
        ):
            state = "stage_3"
        elif classify_stage_2a(
            prior,
            close,
            sma_50,
            sma_150,
            sma_200,
            sma_200_slope,
            max_close_60d,
            rs_rank_12m_val,
            days_in_stage_2,
            thresholds,
        ):
            state = "stage_2a"
        else:
            trend_ok = (
                not any(_is_nan(v) for v in (close, sma_50, sma_150, sma_200))
                and close > sma_50 > sma_150 > sma_200
            )
            in_stage_2 = is_currently_in_2 and trend_ok
            if classify_stage_2c(
                in_stage_2, days_in_stage_2, close, sma_50, atr_14, atr_14_50d_avg, thresholds
            ):
                state = "stage_2c"
            elif classify_stage_2b(in_stage_2, days_in_stage_2, dist_5, close, sma_50, thresholds):
                state = "stage_2b"
            elif classify_stage_1(close, sma_150, atr_14, atr_14_252d_avg, low_age, thresholds):
                state = "stage_1"
            else:
                state = "stage_1"

        # State-transition bookkeeping.
        current_date = r["date"]
        if state != prior:
            state_since: object = current_date
            days_in_stage_2 = 1 if state in ("stage_2a", "stage_2b", "stage_2c") else 0
        else:
            state_since = state_since_per_instr.get(iid, current_date)

        try:
            dwell = (pd.to_datetime(current_date) - pd.to_datetime(state_since)).days
        except Exception:
            dwell = 0

        # Explanation columns.
        cvs50 = (close / sma_50 - 1) if (not _is_nan(sma_50) and sma_50 > 0) else None
        cvs150 = (close / sma_150 - 1) if (not _is_nan(sma_150) and sma_150 > 0) else None
        cvs200 = (close / sma_200 - 1) if (not _is_nan(sma_200) and sma_200 > 0) else None
        vol_ratio = (
            (volume / volume_50d_avg)
            if (not _is_nan(volume_50d_avg) and volume_50d_avg > 0)
            else None
        )

        rows.append(
            {
                "instrument_id": iid,
                "date": current_date,
                "state": state,
                "prior_state": prior,
                "state_since_date": state_since,
                "dwell_days": int(dwell),
                "classifier_version": classifier_version,
                "rs_rank_12m": None if _is_nan(rs_rank_12m_val) else rs_rank_12m_val,
                "close_vs_sma_50": cvs50,
                "close_vs_sma_150": cvs150,
                "close_vs_sma_200": cvs200,
                "sma_200_slope": None if _is_nan(sma_200_slope) else sma_200_slope,
                "volume_ratio_50d": vol_ratio,
                "distribution_days": dist_25,
            }
        )

        prior_state_per_instr[iid] = state
        state_since_per_instr[iid] = state_since
        days_in_stage_2_per_instr[iid] = days_in_stage_2

    return pd.DataFrame(rows)
