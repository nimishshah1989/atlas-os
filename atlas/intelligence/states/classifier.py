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
    low_252_age_days: int,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 1 (Base): consolidation.

    Caller responsibility: only invoke when NOT in stage 2/3/4. Stage 1 is
    the residual.

    All three must hold:
      - |close - sma_150| / sma_150 < theta_base_tightness  (price hugs the long MA)
      - atr_14 / close < theta_low_vol                       (vol is contracted)
      - low_252_age_days >= theta_min_recovery_days          (past the bottom)
    """
    if any(_is_nan(v) for v in (close, sma_150, atr_14)):
        return False
    if sma_150 <= 0 or close <= 0:
        return False
    tightness = abs(close - sma_150) / sma_150
    low_vol = atr_14 / close
    return (
        tightness < get_threshold(thresholds, "theta_base_tightness", "stage_1")
        and low_vol < get_threshold(thresholds, "theta_low_vol", "stage_1")
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
    volume_today: float,
    volume_50d_avg: float,
    rs_rank_12m: float,
    days_in_stage_2: int,
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 2A (Fresh Breakout). Only fires on transition from Stage 1 or 4."""
    if prior_state not in ("stage_1", "stage_4"):
        return False
    if any(
        _is_nan(v)
        for v in (
            close,
            sma_50,
            sma_150,
            sma_200,
            sma_200_slope,
            volume_today,
            volume_50d_avg,
            rs_rank_12m,
        )
    ):
        return False
    if volume_50d_avg <= 0 or max_close_60d <= 0:
        return False
    return (
        close > sma_50 > sma_150 > sma_200
        and sma_200_slope > 0
        and close >= get_threshold(thresholds, "theta_base_breakout", "stage_2a") * max_close_60d
        and volume_today > get_threshold(thresholds, "theta_vol_mult", "stage_2a") * volume_50d_avg
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
    thresholds: dict[tuple[str, str], ThresholdValue],
) -> bool:
    """Stage 3 (Top): was in stage 2, now showing topping signs.

    Both must hold:
      - topping signal: close < sma_50 OR sma_50_slope < 0
      - distribution_days_25d >= theta_distribution
    """
    if prior_state not in ("stage_2a", "stage_2b", "stage_2c"):
        return False
    if any(_is_nan(v) for v in (close, sma_50, sma_50_slope)):
        return False
    topping_price = close < sma_50 or sma_50_slope < 0
    enough_distribution = distribution_days_25d >= get_threshold(
        thresholds, "theta_distribution", "stage_3"
    )
    return topping_price and enough_distribution
