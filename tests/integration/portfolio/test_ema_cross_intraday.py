"""Intraday EMA-cross event detection, asserted on REAL MRPL records (rule #0).

The intraday model fires the crossover on the day the *intraday* price breaches
the provisional-cross level (proxied by the day's adjusted high/low), then fills
at that day's close — instead of waiting for the daily-close confirmation and the
next session.

Two real MRPL episodes anchor it:
  * 2026-07-16 golden cross — opened 163.75, high 178.40 on ~25x volume, breached
    the 163.88 threshold intraday, then closed weak at 157.47 (daily-close EMA
    only confirmed on the 17th). The intraday model must fire the ENTRY on the
    16th, and must NOT re-fire it on the 17th.
  * 2018-11-22 death cross — the intraday low (72.52) breached the down-cross
    level the same day the confirmed close crossed. The intraday model must fire
    the EXIT on the 22nd.

Read-only against the live DB.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from decimal import Decimal

from atlas.db import get_engine
from atlas.portfolio import PortfolioConfig, replay
from atlas.portfolio.strategies import EmaCross

_MRPL = "8d8188fd-7c78-4850-b5e5-32aec989dda1"

_SQL = text(
    """
    select t.instrument_id::text as instrument_key, t.date,
           t.ema_13, t.ema_34,
           o.high_adj as high, o.low_adj as low
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
    return [pd.Timestamp(d).date() for d in rows["date"]]


@pytest.mark.integration
def test_intraday_golden_cross_fires_on_the_breakout_day() -> None:
    panel = _panel(date(2026, 7, 10), date(2026, 7, 20))
    assert not panel.empty, "expected real MRPL rows for the July 2026 window"

    ev = EmaCross(fast=13, slow=34, intraday=True).events(panel)
    entries = _dates(ev, "entry")

    # fires the day the intraday high breached the cross level...
    assert date(2026, 7, 16) in entries
    # ...and NOT again on the 17th (the daily-close-confirmation day) — one entry.
    assert entries == [date(2026, 7, 16)]


@pytest.mark.integration
def test_intraday_death_cross_fires_on_the_breakdown_day() -> None:
    panel = _panel(date(2018, 10, 8), date(2018, 11, 26))
    assert not panel.empty, "expected real MRPL rows for the Oct–Nov 2018 window"

    ev = EmaCross(fast=13, slow=34, intraday=True).events(panel)
    exits = _dates(ev, "exit")

    # an exit can only follow an entry, so this also proves the long was opened.
    assert date(2018, 11, 22) in exits


@pytest.mark.integration
def test_daily_close_mode_still_fires_on_the_confirmation_day() -> None:
    # The default (MF golden-cross) path is unchanged: it fires on the daily-close
    # confirmation date (17th), NOT the intraday-breakout 16th.
    panel = _panel(date(2026, 7, 10), date(2026, 7, 20))
    ev = EmaCross(fast=13, slow=34).events(panel)  # intraday=False
    assert _dates(ev, "entry") == [date(2026, 7, 17)]


_PX_SQL = text(
    """select date, close_adj from atlas_foundation.ohlcv_stock
       where instrument_id::text = :k and date between :a and :b order by date"""
)


def _prices(a: date, b: date) -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql(_PX_SQL, conn, params={"k": _MRPL, "a": a, "b": b})
    df["date"] = [pd.Timestamp(d).date() for d in df["date"]]
    s = pd.Series(
        [Decimal(str(v)) for v in df["close_adj"]], index=pd.Index(df["date"], name="date")
    )
    return pd.DataFrame({_MRPL: s})


def _entry_fill(*, same_day: bool) -> tuple[date, Decimal]:
    prices = _prices(date(2026, 7, 15), date(2026, 7, 20))
    events = pd.DataFrame(
        {"instrument_key": [_MRPL], "date": [date(2026, 7, 16)], "event": ["entry"]}
    )
    cfg = PortfolioConfig(
        portfolio_id="t", kind="strategy",
        initial_capital=Decimal("1000000"), max_position_pct=Decimal("0.08"),
    )
    loop = [d for d in prices.index if d >= date(2026, 7, 16)]
    trades, _ = replay(
        cfg, prices=prices, events=events, inception_state=None, composite=None,
        asset_class={_MRPL: "stock"}, symbols={_MRPL: "MRPL"},
        loop_dates=loop, same_day_fill=same_day,
    )
    row = trades[trades["side"] == "buy"].iloc[0]
    return pd.Timestamp(row["trade_date"]).date(), row["price"]


@pytest.mark.integration
def test_same_day_fill_executes_on_the_crossover_day() -> None:
    # same-day: intraday cross on the 16th fills at the 16th close 157.47
    d, px = _entry_fill(same_day=True)
    assert d == date(2026, 7, 16)
    assert px == Decimal("157.47")


@pytest.mark.integration
def test_next_session_fill_is_the_old_lagged_behavior() -> None:
    # default no-lookahead: fills the NEXT session (the 17th @ 173.33)
    d, px = _entry_fill(same_day=False)
    assert d == date(2026, 7, 17)
    assert px == Decimal("173.33")
