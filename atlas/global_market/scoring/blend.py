"""Composite blend for the US platform: weighted mean over PRESENT lenses + tier cut.

Mirrors ``atlas.lenses.compute.composite.compute_composite`` step for step — including
its float arithmetic and two-stage rounding — so the parity test on real
``atlas_foundation`` rows (tests/integration/global_market/test_blend_parity.py) is EXACT,
not approximate. What differs is the contract: the lens set, weights and tiers are
ARGUMENTS (stocks blend four lenses, ETFs five) and there are NO defaults anywhere. A lens
whose weight key is missing raises ``KeyError``; so does a tier missing from ``tiers``.
Every number comes from ``atlas_global.atlas_thresholds`` or not at all.

Scores are not money: the float path is kept deliberately (it is India's), and the result
is quantised to 0.01 ROUND_HALF_UP exactly as India stores it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_Q2 = Decimal("0.01")
NO_SIGNAL_TIER = "BELOW_THRESHOLD"
DEFAULT_ORDER: tuple[str, ...] = ("HIGHEST", "HIGH", "MEDIUM", "WATCH", NO_SIGNAL_TIER)

# (tier, score-key suffix, min-lenses-key suffix) — the flat keys India's
# thresholds_view.nest_thresholds reads (``lens_conviction_high_score`` …).
_TIER_KEYS: tuple[tuple[str, str, str | None], ...] = (
    ("HIGHEST", "highest_score", "highest_min_layers"),
    ("HIGH", "high_score", "high_min_layers"),
    ("MEDIUM", "medium_score", None),
    ("WATCH", "watch_score", None),
)


@dataclass(frozen=True, slots=True)
class BlendResult:
    composite: Decimal | None  # None = no weighted lens present (no signal, NOT a zero)
    conviction_tier: str
    lenses_active: int  # present lenses carrying weight > 0 — the ones that formed composite
    evidence: dict[str, Any] = field(default_factory=dict)


def weights_from_thresholds(
    th: Mapping[str, Decimal],
    lens_names: Sequence[str],
    prefix: str = "lens_weight_",
) -> dict[str, Decimal]:
    """``{lens: weight}`` from the flat ``<prefix><lens>`` keys. KeyError if ANY is missing."""
    missing = [f"{prefix}{lens}" for lens in lens_names if f"{prefix}{lens}" not in th]
    if missing:
        raise KeyError(
            f"atlas_thresholds is missing weight key(s) {missing} — seed them; "
            "blend() has no defaults"
        )
    return {lens: Decimal(str(th[f"{prefix}{lens}"])) for lens in lens_names}


def tiers_from_thresholds(
    th: Mapping[str, Decimal],
    prefix: str = "lens_conviction_",
) -> dict[str, tuple[Decimal, int]]:
    """``{tier: (min_score, min_lenses)}`` from the flat keys. KeyError if ANY is missing.

    ``BELOW_THRESHOLD`` is always ``(0, 0)`` — it is the floor, not a threshold.
    """
    keys = [
        f"{prefix}{suffix}"
        for _tier, score_key, min_key in _TIER_KEYS
        for suffix in (score_key, min_key)
        if suffix
    ]
    missing = [k for k in keys if k not in th]
    if missing:
        raise KeyError(
            f"atlas_thresholds is missing conviction key(s) {missing} — seed them; "
            "blend() has no defaults"
        )
    tiers: dict[str, tuple[Decimal, int]] = {}
    for tier, score_key, min_key in _TIER_KEYS:
        min_lenses = 0
        if min_key:
            raw = Decimal(str(th[f"{prefix}{min_key}"]))
            if raw != raw.to_integral_value():
                raise ValueError(f"{prefix}{min_key} must be a whole number of lenses, got {raw}")
            min_lenses = int(raw)
        tiers[tier] = (Decimal(str(th[f"{prefix}{score_key}"])), min_lenses)
    tiers[NO_SIGNAL_TIER] = (Decimal(0), 0)
    return tiers


def _tier(
    score: float,
    active: int,
    tiers: Mapping[str, tuple[Decimal, int]],
    order: Sequence[str],
) -> str:
    """First tier in ``order`` whose (min_score, min_lenses) is met — India's
    ``_determine_conviction``, minus its silent ``.get(tier, {})`` defaults."""
    for tier in order:
        min_score, min_lenses = tiers[tier]
        if score >= float(min_score) and active >= min_lenses:
            return tier
    return NO_SIGNAL_TIER


def blend(
    lenses: Mapping[str, Decimal | None],
    weights: Mapping[str, Decimal],
    tiers: Mapping[str, tuple[Decimal, int]],
    order: Sequence[str] = DEFAULT_ORDER,
) -> BlendResult:
    """Σ(w·lens) / Σw over the lenses that are PRESENT (not None) and carry weight > 0.

    ``lenses`` is iterated in its own order; pass the canonical lens order for bit-exact
    parity with India (float summation is order-sensitive). A lens name absent from
    ``weights`` — even a None-valued one — is a KeyError: the weight table must know every
    lens the pipeline computes.
    """
    missing = [lens for lens in lenses if lens not in weights]
    if missing:
        raise KeyError(
            f"blend: no weight for lens(es) {missing} — every lens weight must exist in "
            "atlas_thresholds (lens_weight_<lens>); there are no defaults"
        )
    absent_tiers = [tier for tier in order if tier not in tiers]
    if absent_tiers:
        raise KeyError(f"blend: tiers has no entry for {absent_tiers}")

    # Step 1 (India step 1): a present lens → round(float, 4) → 2 dp (default quantize).
    present: dict[str, Decimal] = {}
    for lens, raw in lenses.items():
        if raw is not None:
            present[lens] = Decimal(str(round(float(raw), 4))).quantize(_Q2)

    # Step 2: only weight > 0 forms the composite. (A weight-0 lens present contributes
    # 0.0 to India's sum, so dropping it here is numerically identical for the score;
    # it is NOT counted as active — a lens without weight cannot form conviction.)
    active: dict[str, float] = {}
    for lens in present:
        w = float(weights[lens])
        if w > 0:
            active[lens] = w
    evidence: dict[str, Any] = {
        "lenses_present": list(present),
        "lenses_active_names": list(active),
    }
    total = sum(active.values())
    if not active or total <= 0:
        return BlendResult(None, NO_SIGNAL_TIER, 0, evidence)

    # India: Σ score·(w/Σw) in float, clamped, then round(·,4) → quantize(0.01, HALF_UP).
    avg = sum(float(present[lens]) * (w / total) for lens, w in active.items())
    final = max(0.0, min(100.0, avg))
    evidence["normalized_avg"] = round(avg, 4)
    evidence["weights_used"] = {lens: str(weights[lens]) for lens in active}
    # India cuts the tier on the UNROUNDED float, so 57.996 is MEDIUM even though it
    # displays as 58.00 — mirrored, not "fixed", so parity stays exact.
    tier = _tier(final, len(active), tiers, order)
    composite = Decimal(str(round(final, 4))).quantize(_Q2, ROUND_HALF_UP)
    return BlendResult(composite, tier, len(active), evidence)
