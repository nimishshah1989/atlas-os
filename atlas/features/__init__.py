"""v6 canonical feature library — wrapper over ``atlas.compute``.

This package is the **v6-canonical** entry point for feature computation,
organized by the five scorecard families locked in design plan §02:

* :mod:`atlas.features.trend`       — trend / momentum primitives
* :mod:`atlas.features.volatility`  — realized vol, ATR
* :mod:`atlas.features.volume`      — per-instrument volume + breadth aggregates
* :mod:`atlas.features.path`        — drawdown, returns, formation
* :mod:`atlas.features.sector`      — sector relative-strength / velocity

Wrapper pattern (NOT a destructive rename)
------------------------------------------
Every callable here is a thin re-export of a pure feature-compute function
from ``atlas/compute/``.  No feature math is duplicated, no behaviour is
changed.  v5 callers continue to import from ``atlas.compute.*``; v6 callers
import from ``atlas.features.*``.  Both paths resolve to the same function
objects (verified by identity checks in ``tests/features/test_v6_surface.py``).

Why a wrapper and not a rename?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``atlas/compute/`` modules mix *feature computation* with *pipeline
  orchestration* (``backfill_*``, ``run_daily_*``, ``_write_*``).  v6 only
  wants the pure feature math surfaced — orchestration stays where it lives.
* A non-destructive lift keeps every v5 caller working unchanged while v6
  modules (decisions, regime, signals, cells) migrate to the new import path
  on their own schedule.
* The ``FEATURES`` tuple below is the SOURCE OF TRUTH for
  ``atlas_cell_definitions.rule_dsl`` Pydantic ``Literal[...]`` validation
  (per /grill Q4).  Centralising the allowlist here — rather than scattered
  across compute modules — is the load-bearing reason this package exists.

The ``FEATURES`` allowlist
--------------------------
``FEATURES`` is the 6 locked methodology features (per CONTEXT.md "29-feature
library" — those that ship as first-class columns on
``atlas.atlas_scorecard_daily`` via migration 080) plus reasonable extensions
already wired through ``atlas/compute/``.  The list grows as Phase 0.5g's
24-framework discovery validates additional features (issue #25).
"""

from __future__ import annotations

from typing import Final

from atlas.features.path import add_max_drawdown, add_returns
from atlas.features.scorecard_writer import (
    ScorecardRow,
    ScorecardWriteResult,
    compute_cap_tiers,
    compute_daily_scorecard,
    derive_family_states,
)
from atlas.features.sector import compute_rs_velocity
from atlas.features.trend import add_emas, add_rs_momentum
from atlas.features.volatility import add_atr, add_realized_vol
from atlas.features.volume import add_volume_primitives, compute_advances_declines

# The canonical v6 feature allowlist.
#
# ORDER: the 6 locked methodology features (per CONTEXT.md + migration 080)
# appear first, in their methodology-doc order, followed by extension features
# already implemented in ``atlas/compute/`` and surfaced through this package.
#
# This tuple is ``Final`` — it is the SOURCE OF TRUTH for
# ``atlas_cell_definitions.rule_dsl`` ``Literal[...]`` validation. Adding a
# feature here is a deliberate methodology decision, not a casual edit.
FEATURES: Final[tuple[str, ...]] = (
    # --- 6 locked methodology features (migration 080 first-class columns) ---
    "rs_residual_6m",
    "log_med_tv_60d",
    "realized_vol_60d",
    "formation_max_dd",
    "listing_age_days",
    "log_price",
    # --- extension features already computed in atlas/compute/ ---
    "ema_20",
    "ema_50",
    "ema_200",
    "atr_14",
    "max_drawdown",
    "rs_momentum",
    "rs_velocity",
    "volume_zscore",
)

__all__ = [
    # Allowlist
    "FEATURES",
    # Trend family
    "add_emas",
    "add_rs_momentum",
    # Volatility family
    "add_atr",
    "add_realized_vol",
    # Volume family
    "add_volume_primitives",
    "compute_advances_declines",
    # Path family
    "add_max_drawdown",
    "add_returns",
    # Sector family
    "compute_rs_velocity",
    # Daily writer
    "ScorecardRow",
    "ScorecardWriteResult",
    "compute_cap_tiers",
    "compute_daily_scorecard",
    "derive_family_states",
]
