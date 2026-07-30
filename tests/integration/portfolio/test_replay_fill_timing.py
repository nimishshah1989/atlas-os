"""Per-side fill timing in replay(), asserted on REAL MRPL records (rule #0), spec §B.

Crossover v2 fills the two sides on different clocks, which the old single
``same_day_fill`` bool cannot express:

  * entries at the NEXT session's OPEN — the confirming close is the signal, so the
    earliest honest price is tomorrow's open.
  * exits at THAT session's CLOSE — the 15:15 lock already decided, and waiting for
    the next open risks a gap down.

Real MRPL July 2026 prices used below:

    date        open_adj   close_adj
    2026-07-17    175.49     173.33
    2026-07-20    172.00     174.49   <- next-open entry lands here
    2026-07-28    163.00     162.29   <- same-close exit lands here

The two equivalence tests are AC5: the pre-v2 ``same_day_fill`` bool must keep
producing byte-identical fills, because 19 live books' stored backtest curves were
generated through it.

NOTE ON AC5 SCOPE: this asserts the PARAMETER FORMS are equivalent, which is where
my change could break things. Re-running all 19 books' backtests and diffing the
stored NAV series is the separate backtest-rebuild step, verified there.

Read-only against the live DB.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.portfolio import PortfolioConfig, replay

_MRPL = "8d8188fd-7c78-4850-b5e5-32aec989dda1"

_SQL = text(
    """select date, open_adj, close_adj from atlas_foundation.ohlcv_stock
       where instrument_id::text = :k and date between :a and :b order by date"""
)


def _panels(a: date, b: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(close panel, open panel) — both Decimal, date-indexed, one column per key."""
    with get_engine().connect() as conn:
        df = pd.read_sql(_SQL, conn, params={"k": _MRPL, "a": a, "b": b})
    idx = pd.Index([pd.Timestamp(d).date() for d in df["date"]], name="date")

    def panel(col: str) -> pd.DataFrame:
        return pd.DataFrame({_MRPL: pd.Series([Decimal(str(v)) for v in df[col]], index=idx)})

    return panel("close_adj"), panel("open_adj")


_CFG = PortfolioConfig(
    portfolio_id="t",
    kind="strategy",
    initial_capital=Decimal("1000000"),
    max_position_pct=Decimal("0.08"),
)


def _run(event: str, event_date: date, first_loop: date, **kw) -> pd.DataFrame:
    prices, opens = _panels(date(2026, 7, 14), date(2026, 7, 29))
    events = pd.DataFrame({"instrument_key": [_MRPL], "date": [event_date], "event": [event]})
    start_positions = {_MRPL: Decimal("100")} if event == "exit" else None
    trades, _ = replay(
        _CFG,
        prices=prices,
        events=events,
        inception_state=None,
        composite=None,
        asset_class={_MRPL: "stock"},
        symbols={_MRPL: "MRPL"},
        start_positions=start_positions,
        loop_dates=[d for d in prices.index if d >= first_loop],
        open_prices=opens,
        **kw,
    )
    return trades


def _one(trades: pd.DataFrame, side: str) -> tuple[date, Decimal]:
    row = trades[trades["side"] == side].iloc[0]
    return cast(date, pd.Timestamp(row["trade_date"]).date()), cast(Decimal, row["price"])


@pytest.mark.integration
def test_next_open_entry_fills_at_the_following_sessions_open() -> None:
    # signal on the 17th -> fills the 20th at its OPEN 172.00 (not the 20th close
    # 174.49, which is what the live book actually paid, and not the 17th close).
    d, px = _one(_run("entry", date(2026, 7, 17), date(2026, 7, 17), entry_fill="next_open"), "buy")
    assert d == date(2026, 7, 20)
    assert px == Decimal("172.00")


@pytest.mark.integration
def test_same_close_exit_fills_at_that_sessions_close() -> None:
    # the 15:15 lock decided on the 28th -> sell at the 28th close 162.29
    d, px = _one(_run("exit", date(2026, 7, 28), date(2026, 7, 27), exit_fill="same_close"), "sell")
    assert d == date(2026, 7, 28)
    assert px == Decimal("162.29")


@pytest.mark.integration
def test_next_open_entry_without_an_open_panel_fails_loudly() -> None:
    # A silent fall back to the close would misprice every entry in the book and
    # look like it worked. It must raise instead.
    prices, _ = _panels(date(2026, 7, 14), date(2026, 7, 29))
    events = pd.DataFrame(
        {"instrument_key": [_MRPL], "date": [date(2026, 7, 17)], "event": ["entry"]}
    )
    with pytest.raises(ValueError, match="open_prices"):
        replay(
            _CFG,
            prices=prices,
            events=events,
            inception_state=None,
            composite=None,
            asset_class={_MRPL: "stock"},
            symbols={_MRPL: "MRPL"},
            loop_dates=[d for d in prices.index if d >= date(2026, 7, 17)],
            entry_fill="next_open",
            open_prices=None,
        )


@pytest.mark.integration
def test_legacy_same_day_fill_false_equals_next_close_on_both_sides() -> None:
    """AC5 — the pre-v2 default form is byte-identical to the explicit enums."""
    legacy = _run("entry", date(2026, 7, 17), date(2026, 7, 17), same_day_fill=False)
    explicit = _run(
        "entry",
        date(2026, 7, 17),
        date(2026, 7, 17),
        entry_fill="next_close",
        exit_fill="next_close",
    )
    pd.testing.assert_frame_equal(legacy, explicit)
    assert _one(legacy, "buy") == (date(2026, 7, 20), Decimal("174.49"))


@pytest.mark.integration
def test_legacy_same_day_fill_true_equals_same_close_on_both_sides() -> None:
    """AC5 — the intraday form is byte-identical to the explicit enums."""
    legacy = _run("entry", date(2026, 7, 17), date(2026, 7, 17), same_day_fill=True)
    explicit = _run(
        "entry",
        date(2026, 7, 17),
        date(2026, 7, 17),
        entry_fill="same_close",
        exit_fill="same_close",
    )
    pd.testing.assert_frame_equal(legacy, explicit)
    assert _one(legacy, "buy") == (date(2026, 7, 17), Decimal("173.33"))
