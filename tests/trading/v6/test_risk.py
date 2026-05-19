"""Tests for atlas/trading/v6/risk.py.

All functions are pure math — no DB. Tests use exact values and boundary checks.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from atlas.trading.v6.risk import (
    dd_circuit_breaker,
    per_name_trend_gate,
    slippage_bps,
    vol_targeted_gross,
)

# ---------------------------------------------------------------------------
# vol_targeted_gross
# ---------------------------------------------------------------------------


def test_vol_targeted_gross_normal_case():
    """realized=0.16, regime=1.0, target=0.12 → vol_scalar=0.75 → gross=0.75."""
    result = vol_targeted_gross(
        realized_portfolio_vol=0.16,
        regime_gross_multiplier=1.0,
        target_vol=0.12,
    )
    assert abs(result - 0.75) < 1e-9


def test_vol_targeted_gross_clips_to_ceiling():
    """Low vol → vol_scalar > 1 → clipped to ceiling 1.10."""
    result = vol_targeted_gross(
        realized_portfolio_vol=0.06,  # very low vol
        regime_gross_multiplier=1.10,
        target_vol=0.12,
    )
    # vol_scalar = 0.12 / 0.06 = 2.0; 2.0 × 1.10 = 2.20 → clipped to 1.10
    assert result == 1.10


def test_vol_targeted_gross_clips_to_floor():
    """High vol + low regime → clipped to floor 0.30."""
    result = vol_targeted_gross(
        realized_portfolio_vol=0.40,  # high vol
        regime_gross_multiplier=0.20,  # crash regime
        target_vol=0.12,
    )
    # vol_scalar = 0.12 / 0.40 = 0.30; 0.30 × 0.20 = 0.06 → clipped to 0.30
    assert result == 0.30


def test_vol_targeted_gross_zero_vol_clips_to_ceiling():
    """realized_vol = 0 → infinite vol_scalar → clipped to ceiling."""
    result = vol_targeted_gross(
        realized_portfolio_vol=0.0,
        regime_gross_multiplier=1.0,
    )
    assert result == 1.10


def test_vol_targeted_gross_negative_vol_treated_as_zero():
    """Negative realized vol (degenerate input) → clipped to ceiling."""
    result = vol_targeted_gross(
        realized_portfolio_vol=-0.05,
        regime_gross_multiplier=1.0,
    )
    assert result == 1.10


def test_vol_targeted_gross_exact_target_vol():
    """realized_vol = target_vol, regime=1.0 → gross = 1.0."""
    result = vol_targeted_gross(
        realized_portfolio_vol=0.12,
        regime_gross_multiplier=1.0,
        target_vol=0.12,
    )
    assert abs(result - 1.0) < 1e-9


def test_vol_targeted_gross_calm_regime_slight_overinvest():
    """regime_mult = 1.10 with moderate vol → result ≤ 1.10 (ceiling)."""
    result = vol_targeted_gross(
        realized_portfolio_vol=0.12,
        regime_gross_multiplier=1.10,
        target_vol=0.12,
    )
    # vol_scalar = 1.0; 1.0 × 1.10 = 1.10 (at ceiling, not above)
    assert abs(result - 1.10) < 1e-9


def test_vol_targeted_gross_result_always_in_bounds():
    """Result is always in [floor, ceiling] for various inputs."""
    test_cases = [
        (0.05, 0.20),
        (0.10, 0.80),
        (0.15, 1.00),
        (0.20, 1.10),
        (0.30, 0.55),
        (0.50, 0.35),
    ]
    for vol, regime_mult in test_cases:
        result = vol_targeted_gross(vol, regime_mult)
        assert (
            0.30 <= result <= 1.10
        ), f"Out of bounds for vol={vol}, regime={regime_mult}: {result}"


# ---------------------------------------------------------------------------
# per_name_trend_gate
# ---------------------------------------------------------------------------


def test_per_name_trend_gate_above_ma_passes():
    """close > ma_200 → True (passes gate)."""
    series = pd.Series([100.0, 101.0, 102.0])
    assert per_name_trend_gate(series, ma_200=95.0) is True


def test_per_name_trend_gate_at_ma_passes():
    """close == ma_200 → True (passes — spec says >=)."""
    series = pd.Series([100.0, 95.0])
    assert per_name_trend_gate(series, ma_200=95.0) is True


def test_per_name_trend_gate_below_ma_fails():
    """close < ma_200 → False (fails gate)."""
    series = pd.Series([90.0, 80.0])
    assert per_name_trend_gate(series, ma_200=95.0) is False


def test_per_name_trend_gate_empty_series_fails():
    """Empty series → False (fail-closed: cannot pass without data)."""
    series = pd.Series([], dtype=float)
    assert per_name_trend_gate(series, ma_200=95.0) is False


def test_per_name_trend_gate_uses_last_value():
    """Gate uses the last value in the series, not the min or mean."""
    # Series starts below, ends above
    series = pd.Series([80.0, 85.0, 90.0, 100.0])
    assert per_name_trend_gate(series, ma_200=95.0) is True

    # Series starts above, ends below
    series2 = pd.Series([100.0, 95.0, 90.0, 80.0])
    assert per_name_trend_gate(series2, ma_200=95.0) is False


# ---------------------------------------------------------------------------
# dd_circuit_breaker
# ---------------------------------------------------------------------------


def _equity_curve(n: int = 100, final_nav: float = 1.0) -> pd.Series:
    """Generate a simple equity curve with given final NAV."""
    # Starts at 1.0, ends at final_nav
    idx = pd.date_range("2024-01-01", periods=n)
    vals = np.linspace(1.0, final_nav, n)
    return pd.Series(vals, index=idx)


def test_dd_circuit_breaker_normal_no_drawdown():
    """current_dd = 0 → state = 'normal'."""
    curve = _equity_curve(final_nav=1.0)
    action = dd_circuit_breaker(curve, current_dd=0.0)
    assert action.state == "normal"
    assert action.new_gross_target is None
    assert action.new_trailing_stop_pct is None


def test_dd_circuit_breaker_small_dd_normal():
    """current_dd = -0.05 (less than -8%) → state = 'normal'."""
    curve = _equity_curve(final_nav=0.95)
    action = dd_circuit_breaker(curve, current_dd=-0.05)
    assert action.state == "normal"


def test_dd_circuit_breaker_halt_entry_at_8pct():
    """current_dd = -0.08 (exactly at halt threshold) → halt_entry."""
    curve = _equity_curve(final_nav=0.92)
    action = dd_circuit_breaker(curve, current_dd=-0.08)
    assert action.state == "halt_entry"
    assert action.new_gross_target is None
    assert action.new_trailing_stop_pct is None


def test_dd_circuit_breaker_halt_entry_between_8_and_14():
    """current_dd = -0.10 (-8% to -14% range) → halt_entry."""
    curve = _equity_curve(final_nav=0.90)
    action = dd_circuit_breaker(curve, current_dd=-0.10)
    assert action.state == "halt_entry"


def test_dd_circuit_breaker_tighten_at_14pct():
    """current_dd = -0.14 (exactly at tighten threshold) → tighten."""
    curve = _equity_curve(final_nav=0.86)
    action = dd_circuit_breaker(curve, current_dd=-0.14)
    assert action.state == "tighten"
    assert action.new_trailing_stop_pct == 0.10


def test_dd_circuit_breaker_tighten_between_14_and_20():
    """current_dd = -0.17 (-14% to -20% range) → tighten."""
    curve = _equity_curve(final_nav=0.83)
    action = dd_circuit_breaker(curve, current_dd=-0.17)
    assert action.state == "tighten"
    assert action.new_gross_target is None
    assert action.new_trailing_stop_pct == 0.10


def test_dd_circuit_breaker_liquidate_at_20pct():
    """current_dd = -0.20 (exactly at liquidate threshold) → liquidate."""
    curve = _equity_curve(final_nav=0.80)
    action = dd_circuit_breaker(curve, current_dd=-0.20)
    assert action.state == "liquidate"
    assert action.new_gross_target == 0.30


def test_dd_circuit_breaker_liquidate_between_20_and_25():
    """current_dd = -0.22 (-20% to -25% range) → liquidate."""
    curve = _equity_curve(final_nav=0.78)
    action = dd_circuit_breaker(curve, current_dd=-0.22)
    assert action.state == "liquidate"
    assert action.new_gross_target == 0.30


def test_dd_circuit_breaker_emergency_cash_at_25pct():
    """current_dd = -0.25 (exactly at emergency threshold) → emergency_cash."""
    curve = _equity_curve(final_nav=0.75)
    action = dd_circuit_breaker(curve, current_dd=-0.25)
    assert action.state == "emergency_cash"
    assert action.new_gross_target == 0.0


def test_dd_circuit_breaker_emergency_cash_beyond_25pct():
    """current_dd = -0.35 (beyond -25%) → emergency_cash."""
    curve = _equity_curve(final_nav=0.65)
    action = dd_circuit_breaker(curve, current_dd=-0.35)
    assert action.state == "emergency_cash"
    assert action.new_gross_target == 0.0


def test_dd_circuit_breaker_empty_curve():
    """Empty equity_curve still works via current_dd parameter."""
    curve = pd.Series([], dtype=float)
    action = dd_circuit_breaker(curve, current_dd=-0.10)
    assert action.state == "halt_entry"


def test_dd_circuit_breaker_returns_frozen_dataclass():
    """BreakerAction is immutable (frozen dataclass)."""
    curve = _equity_curve()
    action = dd_circuit_breaker(curve, current_dd=0.0)
    with pytest.raises((AttributeError, TypeError)):
        action.state = "emergency_cash"  # type: ignore[misc]


def test_dd_circuit_breaker_severity_ordering():
    """More negative dd → higher severity state. Monotonic ordering."""
    curve = _equity_curve()
    states_in_order = [
        dd_circuit_breaker(curve, dd).state for dd in [-0.05, -0.08, -0.14, -0.20, -0.25]
    ]
    expected = ["normal", "halt_entry", "tighten", "liquidate", "emergency_cash"]
    assert states_in_order == expected


# ---------------------------------------------------------------------------
# slippage_bps
# ---------------------------------------------------------------------------


def test_slippage_bps_zero_order_value():
    """order_value = 0 → sqrt(0) = 0 → 5 + 0 + 15 = 20 bps."""
    result = slippage_bps(order_value=0.0, adv_20d=1_000_000)
    assert abs(result - 20.0) < 1e-9


def test_slippage_bps_100pct_participation():
    """order_value = adv_20d → participation=1.0 → 5 + 30 + 15 = 50 bps."""
    adv = 10_000_000
    result = slippage_bps(order_value=adv, adv_20d=adv)
    assert abs(result - 50.0) < 1e-9


def test_slippage_bps_25pct_participation():
    """order_value = 25% of adv → sqrt(0.25) = 0.5 → 5 + 15 + 15 = 35 bps."""
    adv = 10_000_000
    result = slippage_bps(order_value=adv * 0.25, adv_20d=adv)
    assert abs(result - 35.0) < 1e-9


def test_slippage_bps_capped_at_100():
    """Huge order relative to ADV → capped at 100 bps."""
    adv = 100_000  # very illiquid
    order = 100_000_000  # 1000x ADV
    result = slippage_bps(order_value=order, adv_20d=adv)
    assert result == 100.0


def test_slippage_bps_zero_adv_returns_cap():
    """adv_20d = 0 → cannot compute; returns cap (100 bps)."""
    result = slippage_bps(order_value=1_000_000, adv_20d=0)
    assert result == 100.0


def test_slippage_bps_negative_adv_returns_cap():
    """adv_20d < 0 → degenerate; returns cap."""
    result = slippage_bps(order_value=1_000_000, adv_20d=-1)
    assert result == 100.0


def test_slippage_bps_negative_order_value_treated_as_absolute():
    """Negative order_value (sell) → same as positive (absolute value)."""
    adv = 10_000_000
    result_buy = slippage_bps(order_value=adv * 0.25, adv_20d=adv)
    result_sell = slippage_bps(order_value=-adv * 0.25, adv_20d=adv)
    assert abs(result_buy - result_sell) < 1e-9


def test_slippage_bps_formula_components():
    """Manual formula check: 5 + 30*sqrt(ratio) + 15, capped at 100."""
    order_val = 500_000
    adv = 20_000_000
    ratio = order_val / adv  # 0.025
    expected = 5.0 + 30.0 * math.sqrt(ratio) + 15.0
    expected = min(expected, 100.0)
    result = slippage_bps(order_val, adv)
    assert abs(result - expected) < 1e-9


def test_slippage_bps_always_at_least_explicit_costs():
    """Minimum slippage >= 20 bps (5 fixed + 15 explicit) when adv > 0."""
    result = slippage_bps(order_value=1.0, adv_20d=1_000_000_000)  # tiny order
    assert result >= 20.0
