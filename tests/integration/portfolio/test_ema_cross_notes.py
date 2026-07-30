"""EmaCross emits its own half of the decision trail (spec §I.2), on REAL records.

The engine can say why a name won a slot. It cannot say which rule fired or at what
price, because it never sees an EMA — so the strategy attaches a `note` to each event
and the engine joins the two.

Anchored on the same real MRPL July 2026 episode used throughout crossover v2:
the golden cross (P* 163.88, close-confirmed on the 17th) and the fast-EMA exit
(sustained break on the 28th, after the 27th recovered).

Read-only against the live DB.
"""

from __future__ import annotations

from datetime import date

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


def _note(ev: pd.DataFrame, kind: str) -> str:
    return str(ev[ev["event"] == kind].iloc[0]["note"])


@pytest.mark.integration
def test_every_event_carries_a_note() -> None:
    ev = EmaCross(13, 34, intraday=True, exit="fast_ema").events(
        _panel(date(2026, 7, 10), date(2026, 7, 29))
    )
    assert "note" in ev.columns
    assert bool(ev["note"].notna().all())
    assert bool((ev["note"].str.len() > 20).all())


@pytest.mark.integration
def test_intraday_entry_note_names_the_cross_and_the_level() -> None:
    ev = EmaCross(13, 34, intraday=True, entry_confirm="intraday").events(
        _panel(date(2026, 7, 10), date(2026, 7, 20))
    )
    note = _note(ev, "entry")
    assert "EMA13" in note and "EMA34" in note
    assert "163.88" in note  # the real provisional cross level that day
    assert "intraday" in note.lower()


@pytest.mark.integration
def test_close_confirmed_entry_note_says_the_close_confirmed_it() -> None:
    ev = EmaCross(13, 34, intraday=True, entry_confirm="close").events(
        _panel(date(2026, 7, 10), date(2026, 7, 20))
    )
    note = _note(ev, "entry")
    assert "confirm" in note.lower()
    assert "173.33" in note  # the 17th's real close, the first that confirmed


@pytest.mark.integration
def test_fast_ema_exit_note_names_the_ema_level_and_the_lock() -> None:
    ev = EmaCross(13, 34, intraday=True, exit="fast_ema").events(
        _panel(date(2026, 7, 10), date(2026, 7, 29))
    )
    note = _note(ev, "exit")
    assert "EMA13" in note
    assert "167.17" in note  # prior close's confirmed EMA13 on the 28th
    assert "15:15" in note or "close" in note.lower()


@pytest.mark.integration
def test_death_cross_exit_note_names_the_cross_not_the_ema_break() -> None:
    # 2018-11-22: the real death cross, P* 74.83, low 72.52, close 72.86.
    ev = EmaCross(13, 34, intraday=True, exit="death_cross").events(
        _panel(date(2018, 10, 8), date(2018, 11, 26))
    )
    note = _note(ev, "exit")
    assert "below" in note.lower()
    assert "74.8" in note
