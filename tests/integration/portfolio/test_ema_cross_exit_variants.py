"""Twin exit rules asserted on REAL MRPL records (rule #0), crossover v2 spec §A.

The 13/34 rulebook runs as two books with identical entries and different closes.
July 2026 gives a clean real divergence on MRPL (instrument 8d8188fd…). The sell
rule is TWO conditions — breached intraday AND still below at the 15:15 lock, which
the daily-bar backtest proxies with the close (spec §"three honest divergences" #2):

    date        low     close   prev_ema13   breached?   sustained at close?
    2026-07-24  168.61  175.95  165.20       no          no
    2026-07-27  161.50  169.75  166.74       YES         NO   <- recovered, NO sell
    2026-07-28  159.30  162.29  167.17       YES         YES  <- sells here
    2026-07-29  159.00  160.03  166.47       YES         YES  (already flat)

The 27th is the load-bearing case: a real intraday breach that recovered by the
close. A one-condition rule would sell there and be wrong. Meanwhile EMA13 never
crosses below EMA34 anywhere in this window, so the death-cross book is STILL long —
which is why MRPL sits in the live book today, and its death-cross trigger on the
29th was ₹121.22, 26.8% below the EMA13 trigger.

Levels come from the PRIOR close's confirmed EMAs, never the forming day's — the
same no-lookahead convention the entry level P* already uses.

test_death_cross_events_are_identical_with_and_without_the_param is AC2: a
regression PIN, not a feature test. It exists to fail loudly if wiring the
fast-EMA exit ever perturbs the default path that 9 live books depend on.

Read-only against the live DB.
"""

from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.portfolio.strategies import EmaCross

_MRPL = "8d8188fd-7c78-4850-b5e5-32aec989dda1"

_SQL = text(
    """
    select t.instrument_id::text as instrument_key, t.date,
           t.ema_13, t.ema_34,
           o.high_adj as high, o.low_adj as low, o.close_adj as close
    from atlas_foundation.technical_daily t
    join atlas_foundation.ohlcv_stock o
      on o.instrument_id = t.instrument_id and o.date = t.date
    where t.instrument_id::text = :k and t.date between :a and :b
    order by t.date
    """
)


def _panel(a: date, b: date) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(_SQL, conn, params={"k": _MRPL, "a": a, "b": b})


def _dates(ev: pd.DataFrame, kind: str) -> list[date]:
    rows = ev[ev["event"] == kind]
    return [cast(date, pd.Timestamp(d).date()) for d in rows["date"]]


@pytest.mark.integration
def test_fast_ema_exit_fires_the_day_price_loses_the_fast_ema() -> None:
    panel = _panel(date(2026, 7, 10), date(2026, 7, 29))
    assert not panel.empty, "expected real MRPL rows for the July 2026 window"

    ev = EmaCross(fast=13, slow=34, intraday=True, exit="fast_ema").events(panel)

    # Sells on the 28th, NOT the 27th: the 27th breached intraday (low 161.50 vs
    # prior EMA13 166.74) but recovered to close at 169.75, so the 15:15 lock never
    # held. One exit, on the first day the break actually sustained.
    assert _dates(ev, "exit") == [date(2026, 7, 28)]


@pytest.mark.integration
def test_fast_ema_exit_ignores_an_intraday_break_that_recovers_by_the_close() -> None:
    # The 27th in isolation: a real breach that recovered. Cutting the window at the
    # 27th must yield NO exit at all — proof the sustain check is doing the work and
    # not just happening to pick a later date.
    panel = _panel(date(2026, 7, 10), date(2026, 7, 27))

    ev = EmaCross(fast=13, slow=34, intraday=True, exit="fast_ema").events(panel)

    # exactly one entry (date is the BUY rule's business, pinned in its own test)
    assert len(_dates(ev, "entry")) == 1
    assert _dates(ev, "exit") == []


@pytest.mark.integration
def test_death_cross_variant_is_still_holding_over_the_same_window() -> None:
    # Same real panel, same entry, but EMA13 never crosses below EMA34 — so the
    # death-cross book takes no exit at all. This is why MRPL sits in the live book.
    panel = _panel(date(2026, 7, 10), date(2026, 7, 29))

    ev = EmaCross(fast=13, slow=34, intraday=True, exit="death_cross").events(panel)

    # exactly one entry (date is the BUY rule's business, pinned in its own test)
    assert len(_dates(ev, "entry")) == 1
    assert _dates(ev, "exit") == []


@pytest.mark.integration
def test_death_cross_events_are_identical_with_and_without_the_param() -> None:
    """AC2 — the default path provably does not move.

    Eight years of real MRPL history, covering many entry/exit episodes, in both
    detection modes. Passing an explicit exit="death_cross" must be a no-op versus
    omitting it entirely.
    """
    panel = _panel(date(2018, 1, 1), date(2026, 7, 29))
    assert len(panel) > 1500, f"expected ~8y of real MRPL rows, got {len(panel)}"

    for intraday in (False, True):
        before = EmaCross(fast=13, slow=34, intraday=intraday).events(panel)
        after = EmaCross(fast=13, slow=34, intraday=intraday, exit="death_cross").events(panel)
        pd.testing.assert_frame_equal(before, after)
        assert not before.empty, f"expected real events in intraday={intraday} mode"
