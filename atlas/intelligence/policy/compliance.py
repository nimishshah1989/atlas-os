# allow-large: single-responsibility; 6 rule fns + 2 dataclasses + 1 public fn; LOC is docs
"""Policy-compliance check for atlas.intelligence.policy.

Given a portfolio's holdings and its effective Policy, returns all constraint
breaches as ComplianceBreach records. Empty list = fully compliant.

Six rules (C7):
    max_per_stock   — any holding.weight_pct > policy.max_per_stock_pct
    max_per_sector  — sector sum(weight_pct) > policy.max_per_sector_pct
    max_small_cap   — sum(weight_pct where is_small_cap) > policy.max_small_cap_pct
    min_holdings    — len(holdings) < policy.min_holdings
    max_positions   — len(holdings) > policy.max_positions
    cash_floor      — (100 − sum(all weight_pct)) < policy.cash_floor_pct

All checks are strict (>/<). A value exactly at a limit is not a breach.
Pure function — no DB access, no I/O. Decimal throughout.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from atlas.intelligence.policy.policy import Policy

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Holding:
    """A portfolio holding with the fields required for compliance checking.

    Fields:
        instrument_id: Identifier for the holding (used in breach messages).
        weight_pct:    Current weight as whole-number percent (Decimal).
                       Must be >= 0. Whole book weights need not sum to 100
                       (uninvested cash is the residual).
        sector:        Sector name — used for max_per_sector aggregation.
        is_small_cap:  True if this holding is classified as small-cap.
                       The max_small_cap rule sums all is_small_cap=True weights.
                       bool chosen over a cap_tier string because the check only
                       needs a binary split; callers map cap_tier at the call site.
    """

    instrument_id: str
    weight_pct: Decimal
    sector: str
    is_small_cap: bool


@dataclass(frozen=True)
class ComplianceBreach:
    """A single policy constraint breach.

    Fields:
        rule:    Rule identifier. One of:
                     'max_per_stock', 'max_per_sector', 'max_small_cap',
                     'min_holdings', 'max_positions', 'cash_floor'
        message: Human-readable description of the breach.
        actual:  The measured value that violated the limit (Decimal).
        limit:   The policy limit that was exceeded (Decimal).
    """

    rule: str
    message: str
    actual: Decimal
    limit: Decimal


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def check_compliance(
    holdings: list[Holding],
    policy: Policy,
) -> list[ComplianceBreach]:
    """Check a portfolio's holdings against every Policy constraint.

    Evaluates all six rules and returns the complete list of breaches in a
    deterministic order: max_per_stock (one per offending holding, in input
    order), max_per_sector (one per offending sector, in sector-first-seen
    order), max_small_cap, min_holdings, max_positions, cash_floor.

    Returns an empty list if and only if the portfolio is fully compliant.

    Args:
        holdings: Current portfolio holdings. May be empty (an empty book
                  triggers a min_holdings breach for any policy that requires
                  at least one holding).
        policy:   Effective Policy for the portfolio (house default merged with
                  any portfolio-level overrides).

    Returns:
        List of ComplianceBreach. Order within a rule type is stable but not
        semantically significant. Empty = fully compliant.
    """
    breaches: list[ComplianceBreach] = []

    # --- Rule 1: max_per_stock -----------------------------------------------
    breaches.extend(_check_max_per_stock(holdings, policy))

    # --- Rule 2: max_per_sector ----------------------------------------------
    breaches.extend(_check_max_per_sector(holdings, policy))

    # --- Rule 3: max_small_cap -----------------------------------------------
    sc_breach = _check_max_small_cap(holdings, policy)
    if sc_breach is not None:
        breaches.append(sc_breach)

    # --- Rule 4: min_holdings ------------------------------------------------
    mh_breach = _check_min_holdings(holdings, policy)
    if mh_breach is not None:
        breaches.append(mh_breach)

    # --- Rule 5: max_positions ------------------------------------------------
    mp_breach = _check_max_positions(holdings, policy)
    if mp_breach is not None:
        breaches.append(mp_breach)

    # --- Rule 6: cash_floor --------------------------------------------------
    cf_breach = _check_cash_floor(holdings, policy)
    if cf_breach is not None:
        breaches.append(cf_breach)

    return breaches


# ---------------------------------------------------------------------------
# Internal rule implementations
# ---------------------------------------------------------------------------


def _check_max_per_stock(
    holdings: list[Holding],
    policy: Policy,
) -> list[ComplianceBreach]:
    """One breach per holding whose weight exceeds policy.max_per_stock_pct."""
    limit = policy.max_per_stock_pct
    result: list[ComplianceBreach] = []
    for h in holdings:
        if h.weight_pct > limit:
            result.append(
                ComplianceBreach(
                    rule="max_per_stock",
                    message=(
                        f"{h.instrument_id} weight {h.weight_pct}% exceeds "
                        f"per-stock cap {limit}%"
                    ),
                    actual=h.weight_pct,
                    limit=limit,
                )
            )
    return result


def _check_max_per_sector(
    holdings: list[Holding],
    policy: Policy,
) -> list[ComplianceBreach]:
    """One breach per sector whose summed weight exceeds policy.max_per_sector_pct."""
    limit = policy.max_per_sector_pct
    sector_totals: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for h in holdings:
        sector_totals[h.sector] += h.weight_pct

    result: list[ComplianceBreach] = []
    for sector, total in sector_totals.items():
        if total > limit:
            result.append(
                ComplianceBreach(
                    rule="max_per_sector",
                    message=(
                        f"Sector {sector!r} total {total}% exceeds " f"per-sector cap {limit}%"
                    ),
                    actual=total,
                    limit=limit,
                )
            )
    return result


def _check_max_small_cap(
    holdings: list[Holding],
    policy: Policy,
) -> ComplianceBreach | None:
    """One breach if small-cap total weight exceeds policy.max_small_cap_pct."""
    limit = policy.max_small_cap_pct
    small_cap_total = sum(
        (h.weight_pct for h in holdings if h.is_small_cap),
        _ZERO,
    )
    if small_cap_total > limit:
        return ComplianceBreach(
            rule="max_small_cap",
            message=(f"Small-cap total {small_cap_total}% exceeds " f"small-cap cap {limit}%"),
            actual=small_cap_total,
            limit=limit,
        )
    return None


def _check_min_holdings(
    holdings: list[Holding],
    policy: Policy,
) -> ComplianceBreach | None:
    """One breach if holding count is below policy.min_holdings."""
    count = len(holdings)
    limit = Decimal(str(policy.min_holdings))
    actual = Decimal(str(count))
    if actual < limit:
        return ComplianceBreach(
            rule="min_holdings",
            message=(f"Portfolio has {count} holdings, below minimum {policy.min_holdings}"),
            actual=actual,
            limit=limit,
        )
    return None


def _check_max_positions(
    holdings: list[Holding],
    policy: Policy,
) -> ComplianceBreach | None:
    """One breach if holding count exceeds policy.max_positions."""
    count = len(holdings)
    limit = Decimal(str(policy.max_positions))
    actual = Decimal(str(count))
    if actual > limit:
        return ComplianceBreach(
            rule="max_positions",
            message=(f"Portfolio has {count} positions, above maximum {policy.max_positions}"),
            actual=actual,
            limit=limit,
        )
    return None


def _check_cash_floor(
    holdings: list[Holding],
    policy: Policy,
) -> ComplianceBreach | None:
    """One breach if residual cash is below policy.cash_floor_pct.

    invested = sum of all weight_pct
    cash     = 100 − invested
    breach   when cash < policy.cash_floor_pct  (strict less-than)
    """
    invested = sum((h.weight_pct for h in holdings), _ZERO)
    cash = _HUNDRED - invested
    limit = policy.cash_floor_pct
    if cash < limit:
        return ComplianceBreach(
            rule="cash_floor",
            message=(
                f"Residual cash {cash}% is below cash floor {limit}% "
                f"(invested {invested}% of 100%)"
            ),
            actual=cash,
            limit=limit,
        )
    return None
