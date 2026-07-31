"""Entry confirmation asserted on REAL MRPL records (rule #0), crossover v2 spec §A.

MRPL's July 2026 golden cross is the case that makes the two buy rules disagree by
9.2% of entry, so both ship as a per-book param and the 8-year re-run decides:

    date        high    close   P*/confirm state          intraday   close-confirm
    2026-07-16  178.40  157.47  breached P* 163.88,
                                closed with ema13 154.89
                                < ema34 155.44             ENTRY      alert only
    2026-07-17  178.00  173.33  ema13 157.52 > ema34
                                156.46 — first confirm     -          ENTRY

The 16th ran 9% intraday on ~25x volume and gave it all back by the close. Buying it
(intraday) captured ₹157.47 before the stock gapped to a ₹175.49 open and never
returned. Refusing it (close-confirm) entered at the 20th's ₹172.00 open instead.
Which is right is an empirical question across 8 years, not a matter of taste.

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
def test_intraday_confirmation_enters_on_the_breakout_day() -> None:
    panel = _panel(date(2026, 7, 10), date(2026, 7, 20))
    assert not panel.empty, "expected real MRPL rows for the July 2026 window"

    ev = EmaCross(fast=13, slow=34, intraday=True, entry_confirm="intraday").events(panel)

    # the spike day itself, even though it closed weak
    assert _dates(ev, "entry") == [date(2026, 7, 16)]


@pytest.mark.integration
def test_close_confirmation_waits_for_the_close_to_actually_confirm() -> None:
    panel = _panel(date(2026, 7, 10), date(2026, 7, 20))

    ev = EmaCross(fast=13, slow=34, intraday=True, entry_confirm="close").events(panel)

    # the 16th only alerts — its close left ema13 BELOW ema34. The 17th is the
    # first close where the cross is real.
    assert _dates(ev, "entry") == [date(2026, 7, 17)]


@pytest.mark.integration
def test_close_confirmation_does_not_double_fire_while_the_cross_persists() -> None:
    # ema13 stays above ema34 for the whole rest of July, so the confirmed state
    # must open the position ONCE, not on every subsequent day.
    panel = _panel(date(2026, 7, 10), date(2026, 7, 29))

    ev = EmaCross(fast=13, slow=34, intraday=True, entry_confirm="close").events(panel)

    assert _dates(ev, "entry") == [date(2026, 7, 17)]
