"""The decision trail on a real replay (crossover v2 spec §I, AC17-21).

Two REAL instruments compete for ONE slot, using real prices from ohlcv_stock and
real composites from atlas_lens_scores_daily (rule #0). At 2026-07-10 the scores are
GLENMARK 59.00 and MRPL 6.75, so GLENMARK must take the slot and the booked row must
NAME MRPL as the name it beat — that clause is the whole point of §I.4.

max_position_pct=1.0 forces slots=1, which is what creates the competition. Real
books run 0.08 (12 slots).

Read-only against the live DB.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import text

from atlas.db import get_engine
from atlas.portfolio import PortfolioConfig, replay

_MRPL = "8d8188fd-7c78-4850-b5e5-32aec989dda1"
_SIG = date(2026, 7, 10)

_PX = text(
    """select instrument_id::text as k, date, close_adj
       from atlas_foundation.ohlcv_stock
       where instrument_id::text = any(:ks) and date between :a and :b order by date"""
)
_GLEN = text(
    """select instrument_id::text from atlas_foundation.instrument_master
       where symbol = 'GLENMARK' and asset_class = 'stock' limit 1"""
)
_COMP = text(
    """select instrument_id::text as instrument_key, date, composite
       from atlas_foundation.atlas_lens_scores_daily
       where instrument_id::text = any(:ks) and date between :a and :b"""
)


def _fixture():
    with get_engine().connect() as conn:
        glen = conn.execute(_GLEN).scalar()
        assert glen, "expected a real GLENMARK instrument row"
        ks = [_MRPL, str(glen)]
        px = pd.read_sql(_PX, conn, params={"ks": ks, "a": _SIG, "b": date(2026, 7, 20)})
        comp = pd.read_sql(_COMP, conn, params={"ks": ks, "a": _SIG, "b": date(2026, 7, 20)})
    px["date"] = [pd.Timestamp(d).date() for d in px["date"]]
    comp["date"] = [pd.Timestamp(d).date() for d in comp["date"]]
    panel = px.pivot_table(index="date", columns="k", values="close_adj", aggfunc="last")
    panel = panel.sort_index().map(lambda v: None if pd.isna(v) else Decimal(str(v)))
    return panel, comp, str(glen)


@pytest.mark.integration
def test_the_winning_row_names_the_name_it_beat() -> None:
    panel, comp, glen = _fixture()
    assert not comp.empty, "expected real composites for the July 2026 window"

    events = pd.DataFrame(
        {
            "instrument_key": [glen, _MRPL],
            "date": [_SIG, _SIG],
            "event": ["entry", "entry"],
            "note": ["EMA13 crossed above EMA34.", "EMA13 crossed above EMA34."],
        }
    )
    trades, _ = replay(
        PortfolioConfig(
            portfolio_id="t",
            kind="strategy",
            initial_capital=Decimal("1000000"),
            max_position_pct=Decimal("1"),  # one slot -> forces the competition
        ),
        prices=panel,
        events=events,
        inception_state=None,
        composite=comp,
        asset_class={glen: "stock", _MRPL: "stock"},
        symbols={glen: "GLENMARK", _MRPL: "MRPL"},
        loop_dates=[d for d in panel.index if d > _SIG],
    )

    assert len(trades) == 1, "one slot, so exactly one fill"
    row = trades.iloc[0]
    assert row["symbol"] == "GLENMARK", "59.00 must beat 6.75"

    why = row["rationale"]
    assert "EMA13 crossed above EMA34." in why  # the strategy's half
    assert "Conviction 59.0" in why  # AC18
    assert "ranked #1 of 2" in why
    assert "1 slot open" in why
    assert "Passed over: MRPL (6.8)" in why  # AC19 — the counterfactual
    assert float(row["composite_at_signal"]) == pytest.approx(59.0)


@pytest.mark.integration
def test_every_engine_written_trade_carries_a_rationale() -> None:
    """AC17 — no NULL rationale on anything the engine books."""
    panel, comp, glen = _fixture()
    events = pd.DataFrame(
        {
            "instrument_key": [glen, _MRPL],
            "date": [_SIG, _SIG],
            "event": ["entry", "entry"],
        }
    )  # deliberately NO note column — the engine half must still stand alone
    trades, _ = replay(
        PortfolioConfig(
            portfolio_id="t",
            kind="strategy",
            initial_capital=Decimal("1000000"),
            max_position_pct=Decimal("0.5"),
        ),
        prices=panel,
        events=events,
        inception_state=None,
        composite=comp,
        asset_class={glen: "stock", _MRPL: "stock"},
        symbols={glen: "GLENMARK", _MRPL: "MRPL"},
        loop_dates=[d for d in panel.index if d > _SIG],
    )
    assert not trades.empty
    assert bool(trades["rationale"].notna().all())
    assert bool((trades["rationale"].str.len() > 30).all())
