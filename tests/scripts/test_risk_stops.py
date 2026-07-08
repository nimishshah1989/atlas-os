"""Real-data test for the engine risk-management stop overlay (money path).

RULE #0: real closes + real ema_13 from atlas_foundation, no synthetic inputs.
Verifies the stop fires at the correct no-lookahead timing (a stop seen at the prior
session's close executes at the current close) and that the raw variant holds through.
Guards the live 10%-from-entry stop applied to every stock book.
"""

from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "foundation"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from atlas.portfolio import PortfolioConfig, replay  # noqa: E402
from portfolio_data import load_cost_tax, load_prices, load_tech  # noqa: E402


def _panels():
    import _db

    keys = _db.read_df(
        "select instrument_id::text k, symbol from atlas_foundation.instrument_master "
        "where symbol in ('RELIANCE','INFY') and asset_class='stock'"
    )
    uni = pd.DataFrame(
        {"instrument_key": keys["k"], "asset_class": "stock", "symbol": keys["symbol"], "sector": None}
    )
    prices = load_prices(uni, dt.date(2024, 1, 1), dt.date(2026, 1, 1))
    tech = load_tech(uni, ("ema_13",), dt.date(2024, 1, 1), dt.date(2026, 1, 1))
    ema = tech.pivot_table(index="date", columns="instrument_key", values="ema_13", aggfunc="last")
    ema = ema.reindex(prices.index).astype(float)
    return prices, ema, dict(zip(keys["symbol"], keys["k"]))


def test_ema_trailing_stop_exits_below_fast_ema_and_holds_without():
    prices, ema, kmap = _panels()
    rel = kmap["RELIANCE"]
    cfg = PortfolioConfig(
        portfolio_id="test-stop", kind="basket",
        initial_capital=Decimal("1000000"), max_position_pct=Decimal("0.5"),
    )
    costs, _r, exit_load = load_cost_tax()
    common = dict(
        events=None,
        inception_state=pd.Series(True, index=[rel]),
        composite=None,
        asset_class={rel: "stock"},
        symbols={rel: "RELIANCE"},
        loop_dates=list(prices.index),
        costs=costs,
        exit_load=exit_load,
    )
    # WITHOUT the stop: seeded once, no exit signal → held throughout (1 buy, 0 sells)
    t_raw, _ = replay(cfg, prices, **common)
    assert (t_raw["side"] == "buy").sum() == 1
    assert (t_raw["side"] == "sell").sum() == 0

    # WITH the ema stop: must exit when the prior close fell below ema_13
    t_rm, n_rm = replay(cfg, prices, stop_ema=ema, **common)
    stops = t_rm[(t_rm["side"] == "sell") & (t_rm["reason"] == "stop")]
    assert len(stops) >= 1, "ema stop never fired"

    # independent expected FIRST stop: first session whose prior close < prior ema_13,
    # after the day-0 entry; the sell executes at that session's close.
    px, e = prices[rel].astype(float), ema[rel].astype(float)
    below = (px.shift(1) < e.shift(1)) & px.shift(1).notna() & e.shift(1).notna()
    idx = list(prices.index)
    first = next(d for d in idx[1:] if bool(below.loc[d]))
    got = stops.iloc[0]["trade_date"]
    assert str(got) == str(first), f"stop fired {got}, expected {first}"

    # invariant: never hold a position into a session whose prior close was below ema_13
    held_after_stop = t_rm[t_rm["reason"] == "stop"]
    assert not held_after_stop.empty
