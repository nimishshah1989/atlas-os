"""Sector-target derivation for atlas.intelligence.policy.

Given per-sector engine signals, a Policy, the portfolio's current weights, and
the regime's deployment ceiling, derives a per-sector target weight.

Formula (C6):
    1. raw[i] = pct_stage_2[i] * mean_within_state_rank[i]
    2. total_raw = sum(raw). Degenerate: if total_raw == 0, all targets = 0.
    3. normalized[i] = raw[i] / total_raw
    4. pre_cap[i] = normalized[i] * regime_cap
    5. target[i] = min(pre_cap[i], policy.max_per_sector_pct)
       Rounded to 2 decimal places (ROUND_HALF_UP).
    6. gap[i] = target[i] - current[i]  (can be negative — trim signal)

Invariants guaranteed:
    - sum(targets) <= regime_cap  (capping never adds weight)
    - every target[i] <= policy.max_per_sector_pct
    - gap is NOT clamped; negative gap = the caller must trim this sector

Input field names mirror the real sector-aggregation output from
``atlas.intelligence.aggregations.sector.aggregate_sector_states``:
    - ``pct_stage_2``            — fraction of sector's stocks in Stage 2 (0..1)
    - ``mean_within_state_rank`` — mean within_state_rank for the sector (0..1)

All arithmetic is Decimal end-to-end. Never float.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from atlas.intelligence.policy.policy import Policy

_ZERO = Decimal("0")

# Rounding precision for final target weights (whole-number %, 2 dp).
_TWO_DP = Decimal("0.01")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorSignal:
    """Bottom-up signal for a single sector.

    Fields mirror ``aggregate_sector_states`` output columns:
        - pct_stage_2: fraction [0, 1] of the sector's stocks classified in any
          Stage-2 sub-state (stage_2a + stage_2b + stage_2c).
          None → 0; an empty sector contributes no engine signal.
        - mean_within_state_rank: mean within_state_rank for the sector,
          fraction [0, 1].
          None → 0; an empty sector contributes no engine signal.

    Both fields accept ``None`` as input (the real sector aggregator emits
    ``None`` for sectors that have no classified constituents).  A ``__post_init__``
    coerces ``None`` → ``Decimal("0")`` so all downstream arithmetic is safe.
    An empty sector therefore receives raw weight 0 and target 0, which is
    the correct, honest behaviour (C5: no fabricated signal).
    """

    sector: str
    pct_stage_2: Decimal | None
    mean_within_state_rank: Decimal | None

    def __post_init__(self) -> None:
        """Coerce None fields to Decimal("0") for empty-sector safety.

        Uses ``object.__setattr__`` because the dataclass is frozen.
        """
        if self.pct_stage_2 is None:
            object.__setattr__(self, "pct_stage_2", _ZERO)
        if self.mean_within_state_rank is None:
            object.__setattr__(self, "mean_within_state_rank", _ZERO)


@dataclass(frozen=True)
class SectorTarget:
    """Derived sector target for a single sector.

    Fields:
        sector:  sector name (matches SectorSignal.sector)
        current: current portfolio weight, whole-number pct as Decimal
        target:  derived target weight, whole-number pct as Decimal (2 dp)
        gap:     target - current; negative = trim signal (not clamped)
    """

    sector: str
    current: Decimal
    target: Decimal
    gap: Decimal


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_sector_targets(
    sector_signals: Sequence[SectorSignal],
    policy: Policy,
    current_weights: dict[str, Decimal],
    regime_cap: Decimal,
) -> list[SectorTarget]:
    """Derive per-sector target weights.

    Applies the C6 formula:
        raw = pct_stage_2 * mean_within_state_rank
        normalized = raw / sum(raw)
        pre_cap = normalized * regime_cap
        target = min(pre_cap, max_per_sector_pct), rounded to 2 dp
        gap = target - current

    Degenerate case: if all raw scores are 0 (no sector has Stage-2 stocks or
    all mean_within_state_rank are 0), all targets are 0. Gaps are 0 - current
    (which will be negative for any currently-held sectors — honest trim signal).

    No re-inflation: sectors whose pre_cap already exceeds max_per_sector_pct are
    capped. The freed capacity is NOT redistributed to uncapped sectors. The sum
    of targets will therefore be <= regime_cap (not necessarily equal to it).

    Args:
        sector_signals:  Sequence of SectorSignal, one per sector.
        policy:          Effective Policy for the portfolio.
                         Uses policy.max_per_sector_pct (whole-number %).
        current_weights: Dict mapping sector name -> current portfolio weight
                         (whole-number %). Missing sectors default to Decimal("0").
        regime_cap:      Maximum fraction of the book that may be invested
                         (whole-number %, e.g. Decimal("40") = 40%).

    Returns:
        List of SectorTarget, one per sector, in the same order as sector_signals.
    """
    max_per_sector = policy.max_per_sector_pct

    # Step 1: raw scores.
    # __post_init__ guarantees both fields are Decimal (None → 0) after construction,
    # but pyright reads the annotation (Decimal | None), so we coerce here too.
    raws: list[Decimal] = [
        (sig.pct_stage_2 or _ZERO) * (sig.mean_within_state_rank or _ZERO) for sig in sector_signals
    ]

    total_raw = sum(raws, Decimal("0"))

    # Step 2: degenerate case — no sector has any Stage-2 breadth
    if total_raw == Decimal("0"):
        return [
            _make_target(
                sector=sig.sector,
                target=Decimal("0"),
                current=current_weights.get(sig.sector, Decimal("0")),
            )
            for sig in sector_signals
        ]

    # Steps 3-5: normalize -> scale -> cap
    results: list[SectorTarget] = []
    for sig, raw in zip(sector_signals, raws, strict=False):
        normalized: Decimal = raw / total_raw
        pre_cap: Decimal = normalized * regime_cap
        capped: Decimal = min(pre_cap, max_per_sector)
        target: Decimal = capped.quantize(_TWO_DP, rounding=ROUND_HALF_UP)
        current: Decimal = current_weights.get(sig.sector, Decimal("0"))
        results.append(_make_target(sector=sig.sector, target=target, current=current))

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_target(sector: str, target: Decimal, current: Decimal) -> SectorTarget:
    """Construct a SectorTarget; gap derived from target and current."""
    gap = target - current
    return SectorTarget(
        sector=sector,
        current=current,
        target=target,
        gap=gap,
    )
