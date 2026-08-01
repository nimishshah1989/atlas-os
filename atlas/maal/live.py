"""Mark the MaaL books to the live quote. Pure — no I/O.

A position with no quote is REPORTED, never silently valued at zero or dropped. A
missing mark on one name would otherwise quietly understate the whole book, and a
plausible-but-wrong number is the worst kind for a figure the desk reads mid-session.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

_PAISE = Decimal("0.01")


def live_pnl(
    positions: list[dict[str, Any]],
    ltp_by_isin: dict[str, Decimal],
) -> dict[str, Any]:
    """Mark positions to `ltp_by_isin`. Returns value, cost, unrealized, and the gaps."""
    market_value = Decimal("0")
    cost = Decimal("0")
    unquoted: list[str] = []

    for p in positions:
        ltp = ltp_by_isin.get(p["isin"])
        if ltp is None:
            unquoted.append(p["isin"])
            continue
        market_value += p["quantity"] * ltp
        cost += p["quantity"] * p["avg_cost"]

    return {
        "market_value": market_value.quantize(_PAISE),
        "cost": cost.quantize(_PAISE),
        "unrealized": (market_value - cost).quantize(_PAISE),
        "unquoted": unquoted,
    }
