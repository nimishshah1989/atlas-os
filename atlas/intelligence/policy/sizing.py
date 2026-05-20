"""Position-sizing formula for atlas.intelligence.policy.

Given three caps — sector/instrument target gap, per-stock concentration cap,
and the room remaining under the regime deployment cap — this module computes
the suggested position size as the intersection (minimum) of all three.

Formula (C6):
    regime_room = regime_cap - current_invested
    raw         = min(target_gap, max_per_stock, regime_room)
    suggested   = max(raw, Decimal("0"))   # clamp to >= 0

Binding-constraint logic:
    When suggested > 0: the term that equalled raw (first match) is binding.
    When suggested == 0 (clamped):
        - target_gap <= 0   → binding = 'target_gap'
        - regime_room <= 0  → binding = 'regime_cap'
        - (max_per_stock <= 0 is a policy-input error; treated as 'max_per_stock')
        - fallback            → 'none'

All input and output values are whole-number percent as Decimal.
Never float.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_ZERO = Decimal("0")

# Valid binding-constraint literals (documented in chunk spec T3.2).
_BINDING_TARGET_GAP = "target_gap"
_BINDING_MAX_PER_STOCK = "max_per_stock"
_BINDING_REGIME_CAP = "regime_cap"
_BINDING_NONE = "none"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionSizeResult:
    """Result of the position-sizing formula.

    Attributes:
        suggested_pct:      Suggested position size as whole-number percent
                            (Decimal, always >= 0).
        binding_constraint: Which of the three input caps determined the
                            suggestion. One of:
                            - 'target_gap'    — gap between sector/instrument
                              target and current weight was the smallest term
                            - 'max_per_stock' — concentration cap was the
                              smallest term
                            - 'regime_cap'    — remaining room under the
                              regime deployment cap was the smallest term
                            - 'none'          — size was clamped to 0 by
                              a path that does not map cleanly to a single
                              term (degenerate; should not occur with valid
                              policy inputs)
    """

    suggested_pct: Decimal
    binding_constraint: str


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def suggest_position_size(
    target_gap: Decimal,
    max_per_stock: Decimal,
    regime_cap: Decimal,
    current_invested: Decimal,
) -> PositionSizeResult:
    """Suggest a position size as the intersection of three caps.

    The three caps are evaluated simultaneously; the smallest non-negative
    value wins.  If any cap would produce a non-positive result the
    suggestion is clamped to zero.

    Args:
        target_gap:        How far the sector/instrument is below its target
                           (whole-number percent, Decimal).  Can be zero or
                           negative when the position is already at/above target.
        max_per_stock:     Policy's per-stock concentration cap (whole-number
                           percent, Decimal, must be > 0 for a well-formed policy).
        regime_cap:        Maximum invested percentage allowed by the current
                           market regime (whole-number percent, Decimal).
        current_invested:  How much of the book is already invested as of this
                           decision (whole-number percent, Decimal).

    Returns:
        PositionSizeResult with:
            suggested_pct       — the suggested size (>= 0, Decimal)
            binding_constraint  — which cap was the binding term (str)
    """
    regime_room: Decimal = regime_cap - current_invested
    raw: Decimal = min(target_gap, max_per_stock, regime_room)

    if raw <= _ZERO:
        # Result is clamped to zero.  Identify the term that drove it there.
        binding = _clamp_binding(target_gap=target_gap, regime_room=regime_room, raw=raw)
        return PositionSizeResult(suggested_pct=_ZERO, binding_constraint=binding)

    # raw > 0 — identify which term equalled raw (first match wins).
    if raw == target_gap:
        binding = _BINDING_TARGET_GAP
    elif raw == max_per_stock:
        binding = _BINDING_MAX_PER_STOCK
    else:
        # raw == regime_room (the only remaining possibility when all are positive)
        binding = _BINDING_REGIME_CAP

    return PositionSizeResult(suggested_pct=raw, binding_constraint=binding)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp_binding(target_gap: Decimal, regime_room: Decimal, raw: Decimal) -> str:
    """Determine the binding constraint when the raw result is <= 0.

    Priority:
        1. target_gap <= 0  → gap was already non-positive; it pulled raw to <= 0
           regardless of the other two terms.
        2. regime_room <= 0 → book is at/over the regime deployment cap.
        3. raw == max_per_stock path is impossible here because max_per_stock
           is always > 0 for a well-formed policy, so raw <= 0 only when at
           least one of the first two conditions holds.
        4. Fallback: 'none' (should be unreachable with valid inputs).
    """
    if target_gap <= _ZERO:
        return _BINDING_TARGET_GAP
    if regime_room <= _ZERO:
        return _BINDING_REGIME_CAP
    # max_per_stock <= 0 (degenerate policy input)
    if raw <= _ZERO:
        return _BINDING_MAX_PER_STOCK
    return _BINDING_NONE
