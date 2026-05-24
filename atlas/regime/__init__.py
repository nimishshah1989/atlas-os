"""atlas.regime — rule-based 4-state market regime classifier (#44).

Public API:

* :class:`RegimeState` — the 4 canonical regime states (Risk-On / Elevated /
  Below-Trend / Risk-Off), wire-format strings that match the
  ``atlas.atlas_regime_state`` enum from migration 080.
* :class:`RegimeInputs` — frozen dataclass holding the 4 input drivers
  (``smallcap_rs_z``, ``breadth_pct_above_200dma``, ``vix_percentile``,
  ``cross_sectional_dispersion``).
* :class:`RegimeThresholds` — frozen dataclass of cutoffs. v6 launch uses
  the hardcoded fallback defaults; Phase 0.5h-prime sweep (#16) produces
  the real values via held-out OOS optimisation per CONTEXT.md
  §"Regime classifier thresholds".
* :func:`classify` — the pure classification function. Conservative-first
  ordering (Risk-Off > Below-Trend > Elevated > Risk-On default) per the
  global ``np.select`` rule.
* :func:`compute_daily_regime` — the daily cron entrypoint. Reads from
  ``de_index_prices`` + ``atlas_scorecard_daily``, computes the 4 inputs,
  calls ``classify``, INSERT/UPSERTs ``atlas.atlas_regime_daily``.

Rule-based, NOT ML — per CEO plan §3 and eng review eureka (saves a 5/10
innovation token; the methodology lock proves this is sufficient).
"""

from __future__ import annotations

from atlas.regime.classifier import (
    RegimeInputs,
    RegimeState,
    RegimeThresholds,
    classify,
)
from atlas.regime.cron import RegimeWriteResult, compute_daily_regime

__all__ = [
    "RegimeInputs",
    "RegimeState",
    "RegimeThresholds",
    "RegimeWriteResult",
    "classify",
    "compute_daily_regime",
]
