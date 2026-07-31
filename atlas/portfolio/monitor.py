"""Decision logic for the 5-min crossover monitor (spec §C). Pure — no Kite, no DB.

One tick, one name, one answer: is this a fresh provisional breach, the 15:15
confirmation of an armed sell, a disarm, or nothing at all.

Two rules do most of the work here and both exist for a reason the FM felt:

  * **A buy is never confirmed by the monitor.** A buy confirms on the CLOSE, which no
    intraday tick can see. The monitor arms it and stops; the nightly path confirms.
    Anything else would tell the FM a trade is happening on evidence that does not exist
    yet.
  * **The same (direction, stage) fires once per day.** There are 78 ticks in a session.
    Without this the FM's phone gets 78 identical messages and the channel becomes
    something he mutes — which costs him the one message that mattered.

The 15:15 lock is the FM's rule: a break that recovers before then is an alert, not a
trade. Real MRPL 2026-07-27 broke to ₹161.50 intraday and closed at ₹169.75 — under a
one-condition rule that is a sale, and it would have been wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal

# The FM's lock. NSE closes 15:30, so this is the last 15-min bar before the close —
# late enough to mean something, early enough to still act on that close.
LOCK = time(15, 15)


@dataclass(frozen=True)
class Tick:
    """Everything knowable about one name at one instant."""

    held: bool
    buy_level: Decimal  # P*, from the PRIOR close's confirmed EMAs
    sell_level: Decimal  # P* or the fast EMA, per the book's exit rule
    quote: Decimal
    now: time
    already: frozenset[tuple[str, str]]  # (direction, stage) pairs already fired today


def decide(t: Tick) -> tuple[str, str] | None:
    """(direction, stage) to record and send, or None to stay quiet."""
    if t.held:
        broken = t.quote <= t.sell_level
        armed = ("sell", "provisional") in t.already

        # At the lock an ALREADY-ARMED sell resolves one way or the other.
        if armed and t.now >= LOCK:
            return ("sell", "confirmed") if broken else ("sell", "disarmed")
        if broken and not armed:
            # First breach of the day — including one that happens AT the lock, which is
            # still only an alert: it never had time to sustain.
            return ("sell", "provisional")
        return None

    # Not held: the only thing that can happen is arming a buy. The monitor cannot
    # confirm it, because confirmation is a property of the close.
    if t.quote >= t.buy_level and ("buy", "provisional") not in t.already:
        return ("buy", "provisional")
    return None
