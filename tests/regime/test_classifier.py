"""Tests for ``atlas.regime.classifier`` — rule-based 4-state regime (#44).

Covers:

* Each of the 4 states fires on the correct synthetic inputs.
* Conservative-first ordering — Risk-Off beats Below-Trend beats Elevated.
* VIX-NaN fallback — disabling the VIX leg never silently forces a
  non-Risk-On state.
* :func:`classify` is pure (same inputs → same output).
* Threshold override via the :class:`RegimeThresholds` dataclass works.
* Boundary semantics — inclusive ``<=`` / ``>=``.
"""

from __future__ import annotations

import pytest

from atlas.regime.classifier import (
    RegimeInputs,
    RegimeState,
    RegimeThresholds,
    classify,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _benign_inputs(**overrides: float) -> RegimeInputs:
    """Inputs that classify to Risk-On under the default thresholds.

    Each driver sits comfortably in the middle of the safe band:
        - smallcap_rs_z = 0.0      (no small-cap weakness)
        - breadth = 0.65           (broad participation)
        - vix_percentile = 0.40    (sub-elevated)
        - dispersion = 0.01        (sub-elevated)
    """
    base = {
        "smallcap_rs_z": 0.0,
        "breadth_pct_above_200dma": 0.65,
        "vix_percentile": 0.40,
        "cross_sectional_dispersion": 0.01,
    }
    base.update(overrides)
    return RegimeInputs(**base)


# ---------------------------------------------------------------------------
# Each state fires on the right driver
# ---------------------------------------------------------------------------


def test_risk_on_default_when_all_drivers_benign() -> None:
    assert classify(_benign_inputs()) is RegimeState.RISK_ON


def test_risk_off_fires_on_smallcap_z() -> None:
    """smallcap_rs_z <= -2.0 → Risk-Off, even with everything else benign."""
    state = classify(_benign_inputs(smallcap_rs_z=-2.5))
    assert state is RegimeState.RISK_OFF


def test_risk_off_fires_on_breadth_collapse() -> None:
    state = classify(_benign_inputs(breadth_pct_above_200dma=0.15))
    assert state is RegimeState.RISK_OFF


def test_risk_off_fires_on_extreme_vix() -> None:
    state = classify(_benign_inputs(vix_percentile=0.95))
    assert state is RegimeState.RISK_OFF


def test_below_trend_fires_on_moderate_smallcap_weakness() -> None:
    state = classify(_benign_inputs(smallcap_rs_z=-1.2))
    assert state is RegimeState.BELOW_TREND


def test_below_trend_fires_on_eroding_breadth() -> None:
    state = classify(_benign_inputs(breadth_pct_above_200dma=0.35))
    assert state is RegimeState.BELOW_TREND


def test_elevated_fires_on_high_vix_percentile() -> None:
    state = classify(_benign_inputs(vix_percentile=0.75))
    assert state is RegimeState.ELEVATED


def test_elevated_fires_on_high_dispersion() -> None:
    state = classify(_benign_inputs(cross_sectional_dispersion=0.03))
    assert state is RegimeState.ELEVATED


# ---------------------------------------------------------------------------
# Conservative-first ordering
# ---------------------------------------------------------------------------


def test_conservative_ordering_risk_off_beats_below_trend() -> None:
    """If Risk-Off AND Below-Trend conditions both fire, Risk-Off wins."""
    inputs = _benign_inputs(
        smallcap_rs_z=-2.5,  # Risk-Off leg
        breadth_pct_above_200dma=0.35,  # Below-Trend leg
    )
    assert classify(inputs) is RegimeState.RISK_OFF


def test_conservative_ordering_risk_off_beats_elevated() -> None:
    inputs = _benign_inputs(
        breadth_pct_above_200dma=0.15,  # Risk-Off
        vix_percentile=0.75,  # Elevated leg too
        cross_sectional_dispersion=0.03,  # Elevated leg too
    )
    assert classify(inputs) is RegimeState.RISK_OFF


def test_conservative_ordering_below_trend_beats_elevated() -> None:
    """Smallcap weakness OR breadth erosion shadows the Elevated leg."""
    inputs = _benign_inputs(
        smallcap_rs_z=-1.5,  # Below-Trend
        vix_percentile=0.80,  # Elevated would otherwise fire
    )
    assert classify(inputs) is RegimeState.BELOW_TREND


# ---------------------------------------------------------------------------
# VIX-NaN handling — must NOT silently force a non-Risk-On state
# ---------------------------------------------------------------------------


def test_vix_nan_does_not_force_risk_off_when_other_legs_silent() -> None:
    """With vix_valid=False and benign non-VIX drivers, regime = Risk-On.

    This is the load-bearing global rule: a missing VIX must never silently
    classify a calm market as a non-Risk-On regime.
    """
    inputs = _benign_inputs(vix_percentile=float("nan"))
    state = classify(inputs, vix_valid=False)
    assert state is RegimeState.RISK_ON


def test_vix_nan_still_allows_risk_off_via_smallcap() -> None:
    """Non-VIX Risk-Off legs still fire when vix_valid=False."""
    inputs = _benign_inputs(
        smallcap_rs_z=-2.5,
        vix_percentile=float("nan"),
    )
    state = classify(inputs, vix_valid=False)
    assert state is RegimeState.RISK_OFF


def test_vix_nan_still_allows_elevated_via_dispersion() -> None:
    """Elevated still fires on dispersion when VIX is invalid."""
    inputs = _benign_inputs(
        vix_percentile=float("nan"),
        cross_sectional_dispersion=0.05,
    )
    state = classify(inputs, vix_valid=False)
    assert state is RegimeState.ELEVATED


def test_vix_at_risk_off_threshold_does_not_fire_when_vix_invalid() -> None:
    """Even with vix_percentile numerically at the threshold, vix_valid=False
    disables the VIX leg."""
    inputs = _benign_inputs(vix_percentile=0.99)  # would normally fire Risk-Off
    state = classify(inputs, vix_valid=False)
    assert state is RegimeState.RISK_ON


# ---------------------------------------------------------------------------
# Threshold override + purity
# ---------------------------------------------------------------------------


def test_threshold_override_changes_classification() -> None:
    """A tighter Below-Trend cutoff should fire on previously-benign z."""
    inputs = _benign_inputs(smallcap_rs_z=-0.5)
    default_state = classify(inputs)
    assert default_state is RegimeState.RISK_ON

    tight = RegimeThresholds(smallcap_rs_z_below_trend=-0.4)
    tight_state = classify(inputs, thresholds=tight)
    assert tight_state is RegimeState.BELOW_TREND


def test_classify_is_pure() -> None:
    """Same inputs → same output, with no hidden state."""
    inputs = _benign_inputs(smallcap_rs_z=-1.0)
    out1 = classify(inputs)
    out2 = classify(inputs)
    out3 = classify(inputs)
    assert out1 is out2 is out3


def test_regime_state_string_values_match_enum_wire_format() -> None:
    """Wire-format values must match ``atlas_regime_state`` enum in migration 080."""
    assert RegimeState.RISK_ON.value == "Risk-On"
    assert RegimeState.ELEVATED.value == "Elevated"
    assert RegimeState.BELOW_TREND.value == "Below-Trend"
    assert RegimeState.RISK_OFF.value == "Risk-Off"


# ---------------------------------------------------------------------------
# Boundary semantics — <= / >= are inclusive
# ---------------------------------------------------------------------------


def test_smallcap_z_at_risk_off_threshold_inclusive() -> None:
    """``smallcap_rs_z == -2.0`` exactly should fire Risk-Off."""
    inputs = _benign_inputs(smallcap_rs_z=-2.0)
    assert classify(inputs) is RegimeState.RISK_OFF


def test_breadth_at_risk_off_threshold_inclusive() -> None:
    inputs = _benign_inputs(breadth_pct_above_200dma=0.20)
    assert classify(inputs) is RegimeState.RISK_OFF


def test_vix_at_risk_off_threshold_inclusive() -> None:
    inputs = _benign_inputs(vix_percentile=0.90)
    assert classify(inputs) is RegimeState.RISK_OFF


def test_dispersion_at_elevated_threshold_inclusive() -> None:
    inputs = _benign_inputs(cross_sectional_dispersion=0.02)
    assert classify(inputs) is RegimeState.ELEVATED


# ---------------------------------------------------------------------------
# Just-above thresholds remain in higher state — sanity narrow margin
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("driver_value", "expected"),
    [
        (-1.99, RegimeState.BELOW_TREND),  # just above Risk-Off cutoff
        (-1.0, RegimeState.BELOW_TREND),  # exact Below-Trend cutoff
        (-0.99, RegimeState.RISK_ON),  # just past Below-Trend cutoff
    ],
)
def test_smallcap_z_neighbour_thresholds(driver_value: float, expected: RegimeState) -> None:
    inputs = _benign_inputs(smallcap_rs_z=driver_value)
    assert classify(inputs) is expected
