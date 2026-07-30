#!/usr/bin/env python3
"""Compare rule variants for one book over real history — read-only, no DB writes.

Crossover v2 leaves two rules genuinely undecided, and neither can be settled by
argument or by a single name:

  * entry_confirm — take the intraday breach, or wait for the close to confirm?
    On real MRPL the gap is 9.2% of entry, in FAVOUR of not waiting. One name is
    not evidence.
  * exit — close on the death cross, or on price losing the fast EMA?

So both ship as params and this replays the grid over the stored 8 years. Every
number comes from a real replay of real records (rule #0); nothing is written back,
so running this can never disturb a live book or a stored curve.

    python scripts/foundation/portfolio_sweep.py --portfolio-id <uuid> --years 8

Read the trade COUNT next to the return. A variant that wins on return while firing
4x the trades is buying that return with whipsaw the FM has to live through daily.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from copy import deepcopy
from typing import cast

import _db
import pandas as pd
from portfolio_data import load_cost_tax, load_portfolio
from portfolio_run import run_window

from atlas.portfolio.tax import enrich_trades

ENTRY_CONFIRMS = ("intraday", "close")
EXITS = ("death_cross", "fast_ema")


def _summary(navs: pd.DataFrame, trades: pd.DataFrame, rates) -> dict:
    nav = navs.set_index("date")["nav"].astype(float)
    peak = nav.cummax()
    days = (cast(dt.date, nav.index[-1]) - cast(dt.date, nav.index[0])).days or 1
    total = nav.iloc[-1] / nav.iloc[0] - 1
    out = {
        "total_return_pct": round(total * 100, 1),
        "cagr_pct": round(((nav.iloc[-1] / nav.iloc[0]) ** (365.25 / days) - 1) * 100, 1),
        "max_dd_pct": round(float(((nav - peak) / peak).min()) * 100, 1),
        "n_trades": len(trades),
    }
    sells = trades[trades["side"] == "sell"] if not trades.empty else trades
    if not sells.empty:
        enriched = enrich_trades(trades, rates)
        closed = enriched[enriched["side"] == "sell"]
        pnl = pd.Series(pd.to_numeric(closed["realized_pnl"], errors="coerce")).dropna()
        if not pnl.empty:
            out["n_closed"] = len(pnl)
            out["win_rate_pct"] = round(float((pnl > 0).mean()) * 100, 1)
            out["avg_hold_days"] = round(
                float(
                    pd.Series(pd.to_numeric(closed["holding_days"], errors="coerce"))
                    .dropna()
                    .mean()
                ),
                0,
            )
    return out


def sweep(portfolio_id: str, years: float) -> list[dict]:
    base = load_portfolio(portfolio_id)
    _costs, rates, _el = load_cost_tax()
    eod = _db.eod_cutoff()
    start = eod - dt.timedelta(days=int(years * 365))
    rows = []
    for confirm in ENTRY_CONFIRMS:
        for exit_rule in EXITS:
            p = deepcopy(base)
            params = p["params"] if isinstance(p["params"], dict) else json.loads(p["params"])
            # intraday detection is what makes either rule expressible at all
            params.update({"intraday": True, "entry_confirm": confirm, "exit": exit_rule})
            p["params"] = params
            trades, navs = run_window(p, start, eod, "backtest", risk_managed=True)
            if navs.empty:
                print(f"  {confirm}/{exit_rule}: no NAV rows — skipped", flush=True)
                continue
            row = {"entry_confirm": confirm, "exit": exit_rule, **_summary(navs, trades, rates)}
            rows.append(row)
            print(f"  {confirm:<9} {exit_rule:<12} {row}", flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay rule variants for one book (read-only)")
    ap.add_argument("--portfolio-id", required=True)
    ap.add_argument("--years", type=float, default=8)
    a = ap.parse_args()

    p = load_portfolio(a.portfolio_id)
    print(f"=== {p['name']} — {a.years:g}y grid, real records, nothing written ===", flush=True)
    rows = sweep(a.portfolio_id, a.years)
    if not rows:
        raise SystemExit("no variant produced a NAV series")
    df = pd.DataFrame(rows).sort_values("total_return_pct", ascending=False)
    print("\n" + df.to_string(index=False))
    best = df.iloc[0]
    print(
        f"\nHighest return: entry_confirm={best['entry_confirm']} exit={best['exit']} "
        f"({best['total_return_pct']}% over {a.years:g}y, "
        f"max drawdown {best['max_dd_pct']}%, {best['n_trades']} trades). "
        "Return alone does not decide this — weigh the drawdown and the trade count."
    )


if __name__ == "__main__":
    main()
