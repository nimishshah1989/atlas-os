"""Decision logic for the 5-min crossover monitor (spec §C), pure — no Kite, no DB.

The monitor's whole job is deciding, for one name on one tick: is this a fresh
provisional breach, the 15:15 confirmation of an armed sell, a disarm, or nothing.

Levels are REAL MRPL records (rule #0):
  * 2026-07-16 buy level P* = 163.88, from the 15th's confirmed EMAs
    (ema13 154.46 UNDER ema34 155.32 — the setup a golden cross needs).
  * 2026-07-28 sell level = the 27th's confirmed EMA13, 167.17 (fast_ema book) —
    the day the break actually sustained. The 27th itself broke intraday to 161.50
    and recovered to close 169.75, which is the case the lock exists to reject.

The false-positive case is REAL KALYANKJIL at 2026-07-31: ema13 570.02 already ABOVE
ema34 495.07, which puts P* at ₹-254.45. Every quote clears a negative level, so a
monitor that looks only at the level buys a name that never crossed anything.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

import pytest

from atlas.portfolio.monitor import Tick, decide

pytestmark = pytest.mark.unit


def _tick(**kw) -> Tick:
    base = dict(
        held=False,
        fast_below_slow=True,
        buy_level=Decimal("163.88"),
        sell_level=Decimal("167.17"),
        quote=Decimal("160.00"),
        now=time(11, 0),
        already=frozenset(),
    )
    return Tick(**{**base, **kw})


def test_a_quote_through_the_buy_level_arms_a_provisional_buy() -> None:
    d = decide(_tick(quote=Decimal("165.10")))
    assert d == ("buy", "provisional")


def test_a_quote_below_the_buy_level_does_nothing_for_an_unheld_name() -> None:
    assert decide(_tick(quote=Decimal("160.00"))) is None


def test_a_name_whose_fast_ema_is_already_above_the_slow_never_arms_a_buy() -> None:
    # Real KALYANKJIL 2026-07-31: ema13 570.02 over ema34 495.07, so there is no cross
    # left to make and P* is ₹-254.45. Quoting 620.00 clears that level trivially — the
    # level alone cannot tell a golden cross from a name that crossed weeks ago.
    d = decide(_tick(fast_below_slow=False, buy_level=Decimal("-254.45"), quote=Decimal("620.00")))
    assert d is None


def test_a_held_name_still_sells_when_its_fast_ema_is_above_the_slow() -> None:
    # The buy gate must not mute exits: every held name is by definition one whose fast
    # EMA already crossed above, and that is exactly the state a stop has to fire from.
    d = decide(_tick(held=True, fast_below_slow=False, quote=Decimal("161.50")))
    assert d == ("sell", "provisional")


def test_a_held_name_breaking_the_sell_level_arms_a_provisional_sell() -> None:
    d = decide(_tick(held=True, quote=Decimal("161.50")))
    assert d == ("sell", "provisional")


def test_an_unheld_name_never_produces_a_sell() -> None:
    # you cannot sell what the book does not hold, however far price falls
    assert decide(_tick(held=False, quote=Decimal("100.00"))) is None


def test_a_held_name_is_not_re_bought() -> None:
    assert decide(_tick(held=True, quote=Decimal("999.00"))) is None


def test_the_same_stage_does_not_fire_twice_in_a_day() -> None:
    # 78 ticks a day; without this the FM gets 78 identical messages
    armed = frozenset({("sell", "provisional")})
    assert decide(_tick(held=True, quote=Decimal("161.50"), already=armed)) is None


def test_at_1515_a_still_broken_sell_confirms() -> None:
    armed = frozenset({("sell", "provisional")})
    d = decide(_tick(held=True, quote=Decimal("162.29"), now=time(15, 15), already=armed))
    assert d == ("sell", "confirmed")


def test_at_1515_a_recovered_sell_disarms_instead_of_trading() -> None:
    # real MRPL 2026-07-27: broke to 161.50 intraday, back to 169.75. No trade.
    armed = frozenset({("sell", "provisional")})
    d = decide(_tick(held=True, quote=Decimal("169.75"), now=time(15, 15), already=armed))
    assert d == ("sell", "disarmed")


def test_nothing_confirms_at_1515_if_it_never_armed() -> None:
    d = decide(_tick(held=True, quote=Decimal("162.29"), now=time(15, 15)))
    # it breached for the first time AT the lock — that is a provisional, not a fill
    assert d == ("sell", "provisional")


def test_buys_are_never_confirmed_by_the_monitor() -> None:
    # a buy confirms on the CLOSE, which the monitor cannot see. It only ever arms one.
    armed = frozenset({("buy", "provisional")})
    d = decide(_tick(quote=Decimal("165.10"), now=time(15, 15), already=armed))
    assert d is None
