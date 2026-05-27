"""Rule-based 4-state regime classifier (#44).

Four states (Risk-On / Elevated / Below-Trend / Risk-Off), four inputs:

* ``smallcap_rs_z`` — rolling z-score of Smallcap-vs-Broad RS line. Negative
  values indicate small caps trailing the broad market (risk-off proxy).
* ``breadth_pct_above_200dma`` — fraction of the M1 universe trading above
  its own 200-day SMA at ``target_date``, in ``[0, 1]``.
* ``vix_percentile`` — where today's VIX sits in the trailing 252-day
  distribution, in ``[0, 1]``. ``NaN`` allowed — see VIX-NaN handling below.
* ``cross_sectional_dispersion`` — standard deviation of recent (e.g. 20-day)
  returns across the M1 universe. High dispersion = stock-pickers' market /
  Elevated.

Conservative-first ordering per the global ``np.select`` rule
(``CONTEXT.md`` §"np.select ordering is conservative-first"):

    Risk-Off  →  Below-Trend  →  Elevated  →  Risk-On (default)

VIX NaN handling per the same global rule
(``vix_valid = vix.notna(); cond = base & (~vix_valid | (vix < threshold))``):
when ``vix_valid=False`` the VIX-dependent legs are skipped — non-VIX legs
can still fire, so Missing VIX does NOT silently force a non-Risk-On state.

Thresholds: v6 launch uses the hardcoded fallback defaults in
:class:`RegimeThresholds`. The Phase 0.5h-prime sweep (#16) replaces them
with values derived from held-out OOS optimisation; once those values land
in ``atlas.atlas_thresholds`` the daily cron passes them through.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RegimeState(StrEnum):
    """The 4 canonical regime states.

    String values match ``atlas.atlas_regime_state`` enum from migration 080
    (``"Risk-On"`` / ``"Elevated"`` / ``"Below-Trend"`` / ``"Risk-Off"``) —
    when written to the DB the ``RegimeState`` value serialises directly to
    the enum's wire form.
    """

    RISK_ON = "Risk-On"
    ELEVATED = "Elevated"
    BELOW_TREND = "Below-Trend"
    RISK_OFF = "Risk-Off"


@dataclass(frozen=True)
class RegimeInputs:
    """The 4 drivers feeding :func:`classify`.

    All values are plain ``float`` per CEO plan Principle 2 (vectorized, lean,
    fast — float is OK for ratios/z-scores). ``vix_percentile`` may carry
    ``float('nan')`` when VIX is unavailable; callers must also pass
    ``vix_valid=False`` to :func:`classify` so the VIX-dependent legs no-op.
    """

    smallcap_rs_z: float
    breadth_pct_above_200dma: float
    vix_percentile: float
    cross_sectional_dispersion: float


@dataclass(frozen=True)
class RegimeThresholds:
    """Cutoffs used by :func:`classify`.

    Defaults are PLACEHOLDER values for v6 launch (per migration 089 + the
    /grill-with-docs Q5 + CONTEXT.md §"Regime classifier thresholds"). The
    Phase 0.5h-prime sweep (#16) produces the real numbers via held-out OOS.

    Semantics (all values inclusive at the boundary where the rule fires):

    - ``smallcap_rs_z_risk_off`` — Risk-Off when ``smallcap_rs_z <= this``
      (extreme small-cap weakness).
    - ``smallcap_rs_z_below_trend`` — Below-Trend when ``smallcap_rs_z <= this``
      (moderate small-cap weakness).
    - ``breadth_risk_off`` — Risk-Off when ``breadth_pct_above_200dma <= this``
      (broad participation collapse).
    - ``breadth_below_trend`` — Below-Trend when
      ``breadth_pct_above_200dma <= this`` (eroding breadth).
    - ``vix_pct_risk_off`` — Risk-Off when ``vix_percentile >= this``
      (extreme vol regime).
    - ``vix_pct_elevated`` — Elevated when ``vix_percentile >= this``
      (rising vol).
    - ``dispersion_elevated`` — Elevated when
      ``cross_sectional_dispersion >= this`` (stock-pickers' market).
    """

    smallcap_rs_z_below_trend: float = -1.0
    smallcap_rs_z_risk_off: float = -2.0
    breadth_below_trend: float = 0.40
    breadth_risk_off: float = 0.20
    vix_pct_elevated: float = 0.70
    vix_pct_risk_off: float = 0.90
    dispersion_elevated: float = 0.02


def classify(
    inputs: RegimeInputs,
    thresholds: RegimeThresholds | None = None,
    vix_valid: bool = True,
) -> RegimeState:
    """Classify the 4 inputs into one of the 4 :class:`RegimeState` values.

    Pure function — same inputs → same output, no I/O, no side effects.

    Conservative-first ordering: the *more* restrictive state wins at the
    boundary. Risk-Off is checked first, then Below-Trend, then Elevated;
    Risk-On is the default.

    VIX NaN handling: if ``vix_valid=False`` the VIX legs are skipped (the
    condition is treated as ``False``). Risk-Off can still fire on the
    smallcap-z or breadth legs alone; Elevated can still fire on the
    dispersion leg alone. A missing VIX therefore never silently forces a
    non-Risk-On classification (per ``CONTEXT.md`` §"VIX NaN requires
    per-condition guards").

    Args:
        inputs: the 4 driver values.
        thresholds: cutoffs. Defaults to :class:`RegimeThresholds` defaults
            (the v6 launch placeholders).
        vix_valid: ``False`` when VIX is unavailable / NaN — disables the
            VIX legs of the Risk-Off and Elevated conditions.

    Returns:
        The classified :class:`RegimeState`.
    """
    th = thresholds if thresholds is not None else RegimeThresholds()

    # Pull values once so the conditions are straight comparisons.
    z = inputs.smallcap_rs_z
    breadth = inputs.breadth_pct_above_200dma
    vix = inputs.vix_percentile
    dispersion = inputs.cross_sectional_dispersion

    # ---- Risk-Off (conservative-first) -------------------------------------
    # Any leg suffices. VIX leg is gated on vix_valid.
    risk_off_smallcap = z <= th.smallcap_rs_z_risk_off
    risk_off_breadth = breadth <= th.breadth_risk_off
    risk_off_vix = vix_valid and (vix >= th.vix_pct_risk_off)
    if risk_off_smallcap or risk_off_breadth or risk_off_vix:
        return RegimeState.RISK_OFF

    # ---- Below-Trend -------------------------------------------------------
    # Smallcap weakness OR breadth erosion. No VIX leg here.
    below_smallcap = z <= th.smallcap_rs_z_below_trend
    below_breadth = breadth <= th.breadth_below_trend
    if below_smallcap or below_breadth:
        return RegimeState.BELOW_TREND

    # ---- Elevated ----------------------------------------------------------
    # Elevated VIX OR high cross-sectional dispersion. VIX leg gated.
    elevated_vix = vix_valid and (vix >= th.vix_pct_elevated)
    elevated_dispersion = dispersion >= th.dispersion_elevated
    if elevated_vix or elevated_dispersion:
        return RegimeState.ELEVATED

    # ---- Default -----------------------------------------------------------
    return RegimeState.RISK_ON


__all__ = [
    "RegimeInputs",
    "RegimeState",
    "RegimeThresholds",
    "classify",
]
