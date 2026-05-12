"""SP04 Stage 3 — conviction composite production module.

Public surface:

- ``weight_loader`` — load currently-active weight sets per tier
- ``tier_assignment`` — compute liquidity tier for each instrument per date
- ``composer`` — produce ``conviction_score`` per (instrument, date)
- ``persistence`` — UPSERT to atlas_stock_conviction_daily +
  atlas_tier_membership_daily

See ``docs/phase2/plans/2026-05-12-sp04-stage3-conviction-production.md``.
"""

from atlas.intelligence.conviction.weight_loader import (
    TierWeightSet,
    load_active_weights,
)

__all__ = ["TierWeightSet", "load_active_weights"]
