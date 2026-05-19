"""Vol targeting, trend gates, drawdown circuit breaker, and sqrt slippage.

Four primitives per spec §7.3-7.5, §7.7. No DB access — pure math functions
operating on caller-supplied data.

All functions are deterministic and stateless. The caller (simulator.py or
lab.py) is responsible for supplying the correct input series.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger()

# Spec §7.3 constants
_DEFAULT_TARGET_VOL: float = 0.12  # 12% annualized
_GROSS_FLOOR: float = 0.30
_GROSS_CEILING: float = 1.10

# Spec §7.4 circuit breaker thresholds
_DD_HALT_ENTRY: float = -0.08  # -8%
_DD_TIGHTEN: float = -0.14  # -14%
_DD_LIQUIDATE: float = -0.20  # -20%
_DD_EMERGENCY_CASH: float = -0.25  # -25%

# Spec §7.7 slippage constants (bps)
_SLIPPAGE_MARKET_IMPACT_COEFF: float = 30.0
_SLIPPAGE_EXPLICIT_COSTS: float = 15.0  # STT 10 + exchange/GST/SEBI/stamp 5
_SLIPPAGE_FIXED: float = 5.0
_SLIPPAGE_CAP_BPS: float = 100.0


def vol_targeted_gross(
    realized_portfolio_vol: float,
    regime_gross_multiplier: float,
    target_vol: float = _DEFAULT_TARGET_VOL,
    floor: float = _GROSS_FLOOR,
    ceiling: float = _GROSS_CEILING,
) -> float:
    """Compute vol-targeted gross exposure.

    Formula (spec §7.3):
        vol_scalar = target_vol / realized_portfolio_vol
        gross = clip(vol_scalar × regime_gross_multiplier, [floor, ceiling])

    When realized_vol = 0 (degenerate/cold-start), vol_scalar -> inf,
    clipped to ceiling.

    Args:
        realized_portfolio_vol: Recent realized portfolio vol (annualized, e.g. 0.15).
        regime_gross_multiplier: Regime-driven multiplier from compute_regime().
        target_vol: Target annualized vol (default 12%).
        floor: Minimum gross (default 0.30).
        ceiling: Maximum gross (default 1.10).

    Returns:
        Gross exposure scalar in [floor, ceiling].
    """
    if realized_portfolio_vol <= 0:
        log.warning(
            "risk.vol_targeted_gross.zero_vol",
            realized_portfolio_vol=realized_portfolio_vol,
            note="Clipping vol_scalar to ceiling",
        )
        vol_scalar = float("inf")
    else:
        vol_scalar = target_vol / realized_portfolio_vol

    gross = vol_scalar * regime_gross_multiplier
    gross_clipped = float(np.clip(gross, floor, ceiling))

    log.debug(
        "risk.vol_targeted_gross",
        realized_vol=realized_portfolio_vol,
        regime_mult=regime_gross_multiplier,
        vol_scalar=vol_scalar if not math.isinf(vol_scalar) else "inf",
        gross_before_clip=gross if not math.isinf(gross) else "inf",
        gross_after_clip=gross_clipped,
    )

    return gross_clipped


def per_name_trend_gate(close_series: pd.Series, ma_200: float) -> bool:
    """Entry gate: most recent close >= 200dMA.

    Args:
        close_series: pandas Series of daily closes (any length).
        ma_200: The 200-day moving average value for this name.

    Returns:
        True if the name passes the trend gate (last close >= ma_200).
        False if it fails or if close_series is empty.
    """
    if close_series.empty:
        return False
    last_close = float(close_series.iloc[-1])
    passes = last_close >= ma_200
    return passes


@dataclass(frozen=True)
class BreakerAction:
    """Circuit breaker state and recommended portfolio adjustments.

    state: One of 'normal', 'halt_entry', 'tighten', 'liquidate', 'emergency_cash'.
    new_gross_target: Recommended gross exposure target (None if no change from state).
    new_trailing_stop_pct: Recommended trailing stop percentage (None if no change).
    """

    state: Literal["normal", "halt_entry", "tighten", "liquidate", "emergency_cash"]
    new_gross_target: float | None
    new_trailing_stop_pct: float | None


def dd_circuit_breaker(equity_curve: pd.Series, current_dd: float) -> BreakerAction:
    """Evaluate drawdown circuit breaker against the equity curve.

    Thresholds per spec §7.4:
      -8%  → halt_entry (stop new entries; tighten stops on existing)
      -14% → tighten (trailing stop 15% → 10%; exit rank cutoff 50 → 35)
      -20% → liquidate (gross equity slashed to 30%)
      -25% → emergency_cash (gross to 0 for 20 days; requires user override to re-engage)

    The current_dd is expected as a negative fraction (e.g. -0.10 for -10%).
    Thresholds are evaluated most-severe-first.

    Args:
        equity_curve: pd.Series of portfolio NAV (indexed by date). Used to
                      compute peak and current drawdown if needed for logging.
        current_dd: Current drawdown as a negative fraction, e.g. -0.10.

    Returns:
        BreakerAction with state and recommended adjustments.
    """
    # Sanity: peak-to-current from equity_curve (for logging/validation)
    if not equity_curve.empty:
        running_max = equity_curve.cummax()
        dd_from_curve = float((equity_curve.iloc[-1] / running_max.iloc[-1]) - 1)
    else:
        dd_from_curve = 0.0

    dd = float(current_dd)

    if dd <= _DD_EMERGENCY_CASH:
        action = BreakerAction(
            state="emergency_cash",
            new_gross_target=0.0,
            new_trailing_stop_pct=None,
        )
    elif dd <= _DD_LIQUIDATE:
        action = BreakerAction(
            state="liquidate",
            new_gross_target=0.30,
            new_trailing_stop_pct=None,
        )
    elif dd <= _DD_TIGHTEN:
        action = BreakerAction(
            state="tighten",
            new_gross_target=None,
            new_trailing_stop_pct=0.10,
        )
    elif dd <= _DD_HALT_ENTRY:
        action = BreakerAction(
            state="halt_entry",
            new_gross_target=None,
            new_trailing_stop_pct=None,
        )
    else:
        action = BreakerAction(
            state="normal",
            new_gross_target=None,
            new_trailing_stop_pct=None,
        )

    log.info(
        "risk.dd_circuit_breaker",
        current_dd=dd,
        dd_from_curve=round(dd_from_curve, 4),
        state=action.state,
        new_gross_target=action.new_gross_target,
        new_trailing_stop_pct=action.new_trailing_stop_pct,
    )

    return action


def slippage_bps(order_value: float, adv_20d: float) -> float:
    """Estimate round-trip slippage in basis points using square-root model.

    Formula (spec §7.7):
        slippage = 5 + 30 × sqrt(order_value / adv_20d) + 15
        (capped at 100 bps)

    The +15 bps covers explicit costs: STT (10) + exchange/GST/SEBI/stamp (5).
    The 5 bps is the fixed bid-ask component.
    The 30 × sqrt(...) is the price impact (market impact coefficient).

    When adv_20d = 0 (illiquid or missing), returns the cap (100 bps).
    When order_value = 0, returns explicit costs only (20 bps), capped.

    Args:
        order_value: Order size in rupees.
        adv_20d: 20-day average daily value traded in rupees.

    Returns:
        Estimated slippage in basis points, capped at 100.
    """
    if adv_20d <= 0:
        log.warning(
            "risk.slippage_bps.zero_adv",
            order_value=order_value,
            adv_20d=adv_20d,
            note="Returning slippage cap",
        )
        return _SLIPPAGE_CAP_BPS

    if order_value < 0:
        order_value = abs(order_value)

    participation = order_value / adv_20d
    raw_bps = (
        _SLIPPAGE_FIXED
        + _SLIPPAGE_MARKET_IMPACT_COEFF * math.sqrt(participation)
        + _SLIPPAGE_EXPLICIT_COSTS
    )
    capped = min(raw_bps, _SLIPPAGE_CAP_BPS)

    log.debug(
        "risk.slippage_bps",
        order_value=order_value,
        adv_20d=adv_20d,
        participation=round(participation, 6),
        raw_bps=round(raw_bps, 2),
        capped_bps=capped,
    )

    return capped
