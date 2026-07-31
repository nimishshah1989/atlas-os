"""FIFO lot matching for realized P&L. Pure — no I/O.

Matches each sell against the oldest open lots first, which is what the PMS
backoffice does; any other order produces numbers that are plausible and wrong.

An unmatched sell returns realized_pnl=None, NOT zero and NOT the full proceeds.
BJ53 has 16 pre-format rows with no ISIN, so their buys are invisible to us —
booking those sells as pure gain would invent profit that never happened.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

_PAISE = Decimal("0.01")
_LTCG_DAYS = 365

# Rows that OPEN a lot, each at its own stated price.
#
# BONUS enters at zero cost — it cost nothing, so the whole eventual sale price is gain.
#
# CORPUS_IN is a securities transfer-IN, NOT cash. Verified 2026-07-31 across all
# three books: every one of the 17 CORPUS_IN rows carries a real quantity and a real
# price (BJ53's 9 are its opening book at inception 2020-09-28; JR100PASS received
# NIFTYBEES/BANKBEES/ITBEES/LIQUIDCASE on 2024-05-15), and none lacks either field.
# Excluding it left those positions with no cost basis, so 42 of 991 real sells
# booked no P&L at all. A cash-only corpus row would carry no ISIN and is filtered
# out upstream before it ever reaches this function.
_OPENING = {"BUY", "BONUS", "CORPUS_IN"}


def match_fifo(txns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One result row per SELL, in date order. Input must be one instrument."""
    lots: list[list[Any]] = []  # [qty_remaining, price, buy_date], oldest first
    results: list[dict[str, Any]] = []

    for t in sorted(txns, key=lambda r: (r["txn_date"], r["txn_type"])):
        kind = str(t["txn_type"]).strip().upper()
        if kind in _OPENING:
            lots.append([t["quantity"], t["price"], t["txn_date"]])
            continue
        if kind != "SELL":
            continue

        to_match = t["quantity"]
        proceeds_gain = Decimal("0")
        oldest_matched: dt.date | None = None

        while to_match > 0 and lots:
            lot = lots[0]
            take = min(to_match, lot[0])
            proceeds_gain += (t["price"] - lot[1]) * take
            if oldest_matched is None:
                oldest_matched = lot[2]
            lot[0] -= take
            to_match -= take
            if lot[0] == 0:
                lots.pop(0)

        matched = t["quantity"] - to_match
        days = (t["txn_date"] - oldest_matched).days if oldest_matched else None
        results.append(
            {
                "txn_date": t["txn_date"],
                "qty": t["quantity"],
                "matched_qty": matched,
                "unmatched_qty": to_match,
                # None, never 0 — an unmatched sell is unknown, not break-even.
                "realized_pnl": (
                    proceeds_gain.quantize(_PAISE) if matched == t["quantity"] else None
                ),
                "holding_days": days,
                "tax_bucket": (
                    None if days is None else ("STCG" if days <= _LTCG_DAYS else "LTCG")
                ),
            }
        )

    return results
