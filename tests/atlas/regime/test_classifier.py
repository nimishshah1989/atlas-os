"""Tests for atlas.regime.classifier.classify — the 4-state regime engine.

Highest-blast-radius pure function (drives the landing-page verdict and gates
daily signal generation) and had zero tests. Covers each state, the
conservative-first ordering, and the VIX-NaN guard.
"""

from __future__ import annotations

import math

from atlas.regime.classifier import (
    RegimeInputs,
    RegimeState,
    RegimeThresholds,
    classify,
)

TH = RegimeThresholds()  # v6 launch defaults


def _inputs(
    z: float = 0.0,
    breadth: float = 0.80,
    vix: float = 0.50,
    dispersion: float = 0.0,
) -> RegimeInputs:
    """Benign defaults → Risk-On unless a field is pushed across a threshold."""
    return RegimeInputs(
        smallcap_rs_z=z,
        breadth_pct_above_200dma=breadth,
        vix_percentile=vix,
        cross_sectional_dispersion=dispersion,
    )


class TestRiskOn:
    def test_all_benign_is_risk_on(self) -> None:
        assert classify(_inputs()) == RegimeState.RISK_ON


class TestRiskOff:
    def test_extreme_smallcap_weakness(self) -> None:
        assert classify(_inputs(z=-2.0)) == RegimeState.RISK_OFF

    def test_breadth_collapse(self) -> None:
        assert classify(_inputs(breadth=0.20)) == RegimeState.RISK_OFF

    def test_extreme_vix(self) -> None:
        assert classify(_inputs(vix=0.90)) == RegimeState.RISK_OFF


class TestBelowTrend:
    def test_moderate_smallcap_weakness(self) -> None:
        # z = -1.0 trips Below-Trend but not Risk-Off (-2.0).
        assert classify(_inputs(z=-1.0)) == RegimeState.BELOW_TREND

    def test_eroding_breadth(self) -> None:
        # breadth 0.40 trips Below-Trend but not Risk-Off (0.20).
        assert classify(_inputs(breadth=0.40)) == RegimeState.BELOW_TREND


class TestElevated:
    def test_rising_vix(self) -> None:
        assert classify(_inputs(vix=0.70)) == RegimeState.ELEVATED

    def test_high_dispersion(self) -> None:
        assert classify(_inputs(dispersion=0.02)) == RegimeState.ELEVATED


class TestConservativeFirstOrdering:
    def test_risk_off_beats_below_trend(self) -> None:
        # Extreme smallcap (Risk-Off) AND eroding breadth (Below-Trend) →
        # the more restrictive Risk-Off wins.
        assert classify(_inputs(z=-2.5, breadth=0.35)) == RegimeState.RISK_OFF

    def test_below_trend_beats_elevated(self) -> None:
        # Eroding breadth (Below-Trend) AND high dispersion (Elevated) →
        # Below-Trend wins (checked first).
        assert classify(_inputs(breadth=0.35, dispersion=0.05)) == RegimeState.BELOW_TREND


class TestVixNaNGuard:
    def test_invalid_vix_skips_risk_off_vix_leg(self) -> None:
        # VIX would trip Risk-Off, but vix_valid=False disables the leg; all
        # other legs benign → Risk-On (a missing VIX must NOT force risk-off).
        out = classify(_inputs(vix=0.99), vix_valid=False)
        assert out == RegimeState.RISK_ON

    def test_invalid_vix_still_allows_breadth_risk_off(self) -> None:
        # Non-VIX legs still fire even when VIX is unavailable.
        out = classify(_inputs(breadth=0.15, vix=float("nan")), vix_valid=False)
        assert out == RegimeState.RISK_OFF

    def test_nan_vix_with_valid_flag_does_not_crash(self) -> None:
        # Defensive: NaN vix with vix_valid=True — the comparison is False, so
        # it simply doesn't trip the VIX legs (no exception).
        out = classify(_inputs(vix=math.nan), vix_valid=True)
        assert out in set(RegimeState)
