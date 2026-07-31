"""Decision-trail prose for booked trades (crossover v2 spec §I).

`portfolio_trades.reason` is a CHECK-constrained KIND ('signal', 'stop', …).
`portfolio_trades.rationale` is the sentence a person reads. Desk fills have carried
one since the desk shipped; the 25,584 strategy trades carried none, so a fill said
"signal" and nothing else.

Split of responsibility:

  * The STRATEGY says which rule fired and at what level — it owns the EMAs, the
    provisional cross price and the 15:15 lock. It hands that over as a note on the
    events frame.
  * This module says why THIS instrument won the slot and why the size is what it is.
    Only the engine holds the ranked candidate list, the open-slot count and the
    cap-vs-cash sizing outcome at the moment of the fill.

Prose carries REASONING only. Numbers that already have their own columns
(realized_pnl, holding_days, cost, tax) are never restated here — two copies of a
number is one copy too many, and they drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Composites render to 1dp, matching how the board prints scores everywhere else.
_SCORE = "{:.1f}"


def _score(v: float) -> str:
    """A composite as text. The engine's no-score sentinel is -inf; printing that, or
    quietly calling it zero, would both misrepresent a name that simply was not
    scored that session."""
    return "unscored" if v == float("-inf") else _SCORE.format(v)


@dataclass(frozen=True)
class Slot:
    """The engine's decision context for one entry, at the moment of the fill.

    Bundled rather than passed loose because these eight facts are one thought — the
    slot competition — and they are only knowable inside `_enter`.
    """

    composite: float
    rank: int
    n_candidates: int
    open_slots: int
    passed_over: list[tuple[str, float]]
    cap_limited: bool
    alloc: Decimal
    cap_pct: Decimal


def slot_clause(slot: Slot) -> str:
    """Why this name took a slot, and why it is this size.

    `passed_over` is the counterfactual — the names that also crossed and did not fit.
    Without it "why ECLERX" has no answer, because the question is only meaningful
    against the names that lost.
    """
    bits = [
        f"Conviction {_score(slot.composite)} — ranked #{slot.rank} of {slot.n_candidates} "
        f"name{'s' if slot.n_candidates != 1 else ''} that crossed, "
        f"{slot.open_slots} slot{'s' if slot.open_slots != 1 else ''} open."
    ]
    if slot.passed_over:
        losers = ", ".join(
            f"{sym} ({_score(c)})" for sym, c in sorted(slot.passed_over, key=lambda p: -p[1])
        )
        bits.append(f"Passed over: {losers}.")
    if slot.cap_limited:
        bits.append(f"Sized to the {slot.cap_pct * 100:.0f}% cap.")
    else:
        bits.append(
            f"Sized to ₹{slot.alloc:,.0f} — cash-limited, not the "
            f"{slot.cap_pct * 100:.0f}% cap; the remaining cash was shared across the "
            "rest of the entries."
        )
    return " ".join(bits)


def stop_clause(
    *,
    kind: str,
    prior_close: Decimal,
    level: Decimal,
    pct: Decimal | None = None,
    entry_price: Decimal | None = None,
) -> str:
    """Why a risk stop fired. Not used by the crossover books, which carry no stop by
    design — but `_book` is shared by the rank and desk books, which do."""
    seen = f"prior close ₹{prior_close:,.2f} fell below ₹{level:,.2f}"
    if kind == "pct" and pct is not None:
        entry = f" (entry ₹{entry_price:,.2f})" if entry_price is not None else ""
        return (
            f"Stop hit: {seen}, more than {pct * 100:.0f}% below entry{entry}. "
            "Sold at this session's close."
        )
    if kind == "trail" and pct is not None:
        return (
            f"Trailing stop hit: {seen}, more than {pct * 100:.0f}% below the peak since "
            "entry. Sold at this session's close."
        )
    return f"EMA stop hit: {seen}, the fast EMA. Sold at this session's close."


def inception_clause(*, weight: Decimal | None) -> str:
    """Why a basket holding exists at all: the FM picked it."""
    if weight is not None:
        return (
            "FM basket pick at inception, sized to its target weight of "
            f"{weight * 100:.0f}% of capital."
        )
    return "FM basket pick at inception, sized to an equal slot."


def join(*parts: str | None) -> str | None:
    """Strategy note + engine clause, skipping whatever is absent."""
    kept = [p.strip() for p in parts if p and p.strip()]
    return " ".join(kept) or None
