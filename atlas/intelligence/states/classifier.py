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
