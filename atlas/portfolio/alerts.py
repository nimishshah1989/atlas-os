"""Telegram message bodies for the crossover books (spec §E). Pure text, no I/O.

The FM hears about a crossover three times instead of once after the fill:

    provisional  the 5-min feed breached the level. NOT a trade — say so loudly, because
                 this is the message most likely to be misread as one.
    confirmed    the close (buys) or the 15:15 quote (sells) held it. It will execute,
                 and the message says when and against what price.
    booked       it executed. Carries the decision trail so the "why" arrives with the
                 "what", instead of living only on a page nobody opens at 20:00.

Every line-one names its BOOK. The twin 13/34 books alert on the same symbol on the same
day with opposite verdicts — that is the whole reason for running both, and without the
book name it reads as the system contradicting itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

# Colour is never the only signal here — the words carry it too, same rule the board
# uses for gains and losses.
_PROVISIONAL = "🟡"
_BOOKED = "✅"


def _qty(q: Decimal) -> str:
    """476, not 476.0 — stocks trade in whole units and the decimal tail reads as noise.
    Fund units are genuinely fractional, so those keep their decimals."""
    return str(int(q)) if q == q.to_integral_value() else str(q.normalize())


def provisional(*, book: str, symbol: str, side: str, level: Decimal, quote: Decimal) -> str:
    """Fired the moment the 5-min feed breaches. The FM must not read this as a fill."""
    direction = "above" if side == "buy" else "below"
    gate = "the close confirms" if side == "buy" else "it holds below at 15:15"
    return (
        f"{_PROVISIONAL} <b>{book} — {side.upper()} SIGNAL (PROVISIONAL)</b>\n"
        f"{symbol} · ₹{quote:,.2f} broke {direction} ₹{level:,.2f}\n"
        f"<i>Not a trade yet.</i> It only executes if {gate}."
    )


def confirmed(*, book: str, symbol: str, side: str, level: Decimal, quote: Decimal) -> str:
    """Buys confirm at the close and fill tomorrow; sells confirm at 15:15 and fill today."""
    if side == "buy":
        return (
            f"🟢 <b>{book} — BUY CONFIRMED</b>\n"
            f"{symbol} · the close at ₹{quote:,.2f} confirmed the cross "
            f"(level ₹{level:,.2f})\n"
            f"Executing at the <b>next open</b>."
        )
    return (
        f"🔴 <b>{book} — SELL CONFIRMED</b>\n"
        f"{symbol} · still below ₹{level:,.2f} at the <b>15:15</b> lock (₹{quote:,.2f})\n"
        f"Executing at <b>today's close</b>."
    )


def booked(*, book: str, trade: Mapping[str, Any]) -> str:
    """The authoritative message: it happened, at this price, for this reason.

    Takes the booked trade ROW rather than eight loose arguments — the caller always has
    one, and threading the fields apart just creates somewhere for them to drift.
    """
    verb = "BOUGHT" if trade["side"] == "buy" else "SOLD"
    lines = [
        f"{_BOOKED} <b>{book} — {verb}</b>",
        f"{trade['symbol']} · {_qty(Decimal(str(trade['qty'])))} "
        f"@ ₹{Decimal(str(trade['price'])):,.2f} · {trade['trade_date']}",
    ]
    if trade.get("rationale"):
        lines.append(f"<i>{trade['rationale']}</i>")
    return "\n".join(lines)
