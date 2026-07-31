"""Post-close buy confirmation (spec §E, the missing 🟢 stage).

The FM's buy rule has three stages and the monitor can only produce two of them: it
arms a provisional on the 5-min feed, but confirmation is a property of the CLOSE,
which no intraday tick can see. So the close-confirmation runs after the EOD compute
lands, promoting today's armed buys to confirmed (they fill at tomorrow's open) or
disarming them.

Real MRPL 2026-07-16/17 is the pair that defines it:
  16th close 157.47 -> ema13 154.89 < ema34 155.44  -> NOT confirmed, disarm
  17th close 173.33 -> ema13 157.52 > ema34 156.46  -> confirmed, fills 20th open
"""

from __future__ import annotations

import pytest

from atlas.portfolio.monitor import buy_confirmed

pytestmark = pytest.mark.unit


def test_the_16th_does_not_confirm() -> None:
    # the spike day: it breached P* intraday but closed with the EMAs still crossed down
    assert buy_confirmed(ema_fast=154.89, ema_slow=155.44) is False


def test_the_17th_confirms() -> None:
    assert buy_confirmed(ema_fast=157.52, ema_slow=156.46) is True


def test_a_missing_ema_never_confirms() -> None:
    # a data gap must not be read as a buy signal — absence of evidence is not
    # evidence, and this one spends money.
    assert buy_confirmed(ema_fast=None, ema_slow=156.46) is False
    assert buy_confirmed(ema_fast=157.52, ema_slow=None) is False


def test_exactly_equal_emas_do_not_confirm() -> None:
    # a cross requires strictly above; equal is the knife edge, not a signal
    assert buy_confirmed(ema_fast=100.0, ema_slow=100.0) is False
