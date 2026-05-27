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
    # --- deep-search extension features (Phase 0.5e — Large @ 12m POSITIVE) ---
    # Added 2026-05-24 to support exhaustive single-cell exploration per
    # methodology lock principle 7 ("pick features by what separates TP
    # from FP, not from theory"). All vectorisable from close+volume.
    "rs_residual_3m",
    "rs_residual_12m",
    "dd_from_52w_high",
    "dd_from_3y_high",
    "dd_from_5y_high",
    "dist_above_sma50",
    "dist_above_sma200",
    "sma50_gt_sma200",
    "realized_vol_252d",
    "close_over_60d_high",
    "close_over_30d_high",
    "volume_zscore_60d",
    "pos_months_12m",
    "rs_alignment_count",
    "rs_acceleration_63d",
    "trend_slope_60d",
    # --- deep-search v2 extension features (Phase 0.5g — all 24 cells) ---
    # Added 2026-05-24 to support exhaustive 24-cell exploration. All
    # vectorisable from close+volume; ATR is a daily-range proxy when
    # high/low are not in the cache.
    "rs_residual_1m",
    "realized_vol_20d",
    "vol_regime_60_252",
    "downside_vol_60d",
    "volume_zscore_252d",
    "tv_momentum_21_63",
    "roc_21d",
    "roc_63d",
    "roc_126d",
    "max_consec_pos_months_12m",
    "pos_weeks_12m",
    "dd_recovery_pct",
    "dist_from_52w_low",
    "close_at_52w_high",
    "consecutive_above_sma50",
    "consecutive_above_sma200",
    "rsi_14",
    "bb_pct_20d",
    "atr_pct_14",
    "corr_to_nifty_60d",
    "beta_60d",
    "excess_vol_60d",
    "rs_rank_6m_3m_diff",
    "rs_rank_12m_6m_diff",
    "range_compression_60_252",
    "ulcer_index_60d",
    "momentum_quality_6m",
    "trend_strength_60d",
    "new_high_streak_60d",
    "close_over_252d_high",
    # --- red-team quick-win features (Phase 0.5g — gap closures) ---
    # Added 2026-05-24 to address red-team coverage gaps from
    # /tmp/deep_search_v2/factor_coverage_critique.md. amihud captures
    # illiquidity; OBV/MFI capture money-flow direction missed by raw
    # volume z-scores; bb_squeeze flags compression-then-thrust setups;
    # within-tier ranks fix the cross-tier RS bias (a tiny-cap top-decile
    # is not the same as a large-cap top-decile).
    "amihud_illiq_21d",
    "obv_slope_60d",
    "mfi_14",
    "bb_squeeze_20d",
    "rs_rank_within_tier_3m",
    "rs_rank_within_tier_6m",
    "rs_rank_within_tier_12m",
    # --- sector RS features (Phase 0.5g — sector family) ---
    # Added 2026-05-24 from /tmp/deep_search_v2/sector_rs_features.py
    # with the leave-one-out (LOO) fix applied to cohort means
    # (`(sum - self) / (count - 1)`) per integration plan §5 risk register.
    # Sector mapping pulled from /tmp/deep_search_v2/sector_mapping.csv.
    "sector_rs_6m",
    "sector_rs_12m",
    "sector_rs_rank_6m",
    "sector_breadth_pos",
    "sector_strength_rank",
    "sector_vol_regime",
    "cross_sector_breadth",
)

__all__ = [
    # Allowlist
    "FEATURES",
    # Daily writer
    "ScorecardRow",
    "ScorecardWriteResult",
    # Volatility family
    "add_atr",
    # Trend family
    "add_emas",
    # Path family
    "add_max_drawdown",
    "add_realized_vol",
    "add_returns",
    "add_rs_momentum",
    # Volume family
    "add_volume_primitives",
    "compute_advances_declines",
    "compute_cap_tiers",
    "compute_daily_scorecard",
    # Sector family
    "compute_rs_velocity",
    "derive_family_states",
]
