"""Load the currently-active signal weight set per tier from atlas_signal_weights.

A "weight set" is the collection of (signal_name, weight, flipped) tuples
that defines the conviction composite for one (tier, regime) combination.
A row is "active" when ``effective_to IS NULL``; a unique index enforces at
most one active row per (tier, regime, signal).

The version string we emit (``weight_set_version``) is the ISO timestamp of
the most-recent ``approved_at`` we see for that tier. It is stored on every
conviction row so we can later trace which weight set produced which score.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = structlog.get_logger()

_TIERS: Final[tuple[str, ...]] = (
    "tier_1_megacap",
    "tier_2_largecap",
    "tier_3_uppermid",
    "tier_4_lowermid",
    "tier_5_smallcap",
)


@dataclass(frozen=True)
class TierWeightSet:
    """The active weight set for one (tier, regime) combination."""

    tier: str
    regime: str
    holdout_ic: Decimal | None
    signals: list[tuple[str, Decimal, bool]]
    weight_set_version: str


def load_active_weights(engine: Engine, regime: str = "all") -> dict[str, TierWeightSet]:
    """Load currently-active weight sets per tier for the given regime.

    Returns a dict keyed by tier name. Empty dict if no weights are seeded
    for that regime (caller should treat this as a hard error).
    """
    sql = text("""
        SELECT tier, regime, signal_name, weight, flipped,
               holdout_ic, approved_at
        FROM atlas.atlas_signal_weights
        WHERE effective_to IS NULL
          AND regime = :regime
        ORDER BY tier, weight DESC
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"regime": regime}).fetchall()

    by_tier: dict[str, list[tuple[str, Decimal, bool]]] = {}
    holdout_by_tier: dict[str, Decimal | None] = {}
    latest_approval: dict[str, str] = {}

    for r in rows:
        tier = r[0]
        by_tier.setdefault(tier, []).append((r[2], Decimal(str(r[3])), bool(r[4])))
        if r[5] is not None and tier not in holdout_by_tier:
            holdout_by_tier[tier] = Decimal(str(r[5]))
        latest_approval[tier] = f"{tier}@{r[6].isoformat()}"

    result: dict[str, TierWeightSet] = {}
    for tier in _TIERS:
        if tier in by_tier:
            result[tier] = TierWeightSet(
                tier=tier,
                regime=regime,
                holdout_ic=holdout_by_tier.get(tier),
                signals=by_tier[tier],
                weight_set_version=latest_approval[tier],
            )

    log.info("active_weights_loaded", regime=regime, n_tiers=len(result))
    return result
