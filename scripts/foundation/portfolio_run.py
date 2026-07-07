#!/usr/bin/env python3
"""Portfolio runner — CLI + engine assembly (create/init/backtest/mark/trade).

DB reads live in portfolio_data; pure strategy/accounting math in
atlas.portfolio. Timing contract (see atlas/portfolio/engine.py): signals
detected at close of session e execute at the close of the next session;
everything anchors to the last complete EOD — never a partial candle.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import _db
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from portfolio_data import (
    _enrich_new_trades,
    load_composite,
    load_cost_tax,
    load_instruments,
    load_portfolio,
    load_prices,
    load_tech,
    load_universe,
    open_entry_dates,
    open_positions,
    stored_live_cash,
)

from atlas.portfolio import PortfolioConfig, get_strategy, replay
from atlas.portfolio.engine import _qty_for
from atlas.portfolio.tax import enrich_trades, summarize

M = "atlas_foundation"


class TradeError(Exception):
    """A refused/impossible manual trade — callers decide whether it is fatal."""


# ── writers ────────────────────────────────────────────────────────────────


def write_results(pid: str, run_type: str, run_id: str, trades: pd.DataFrame, navs: pd.DataFrame):
    if not trades.empty:
        t = trades.copy()
        t["portfolio_id"], t["run_type"], t["run_id"] = pid, run_type, run_id
        with _db.engine().begin() as conn:
            t.to_sql("portfolio_trades", conn, schema=M, if_exists="append", index=False)
    if not navs.empty:
        n = navs.copy()
        n["portfolio_id"], n["run_type"], n["run_id"] = pid, run_type, run_id
        _db.upsert_df(f"{M}.portfolio_nav_daily", n, ["portfolio_id", "run_type", "date"])


# ── engine assembly ────────────────────────────────────────────────────────


def _cfg(p: dict) -> PortfolioConfig:
    return PortfolioConfig(
        portfolio_id=str(p["portfolio_id"]),
        kind=p["kind"],
        initial_capital=Decimal(p["initial_capital"]),
        max_position_pct=Decimal(p["max_position_pct"]),
    )


# portfolio-level params consumed by the runner, never passed to the strategy ctor
_RESERVED_PARAMS = frozenset(
    {"fund_categories", "sleeves", "picks", "charter", "desk", "standing_constraints"}
)


def _strat_params(params: dict) -> dict:
    return {k: v for k, v in params.items() if k not in _RESERVED_PARAMS}


def _strategy(p: dict):
    if p["kind"] != "strategy":
        return None
    params = p["params"] if isinstance(p["params"], dict) else json.loads(p["params"])
    return get_strategy(p["strategy_key"], _strat_params(params))


def _basket_state(p: dict, universe: pd.DataFrame) -> pd.Series:
    """A basket's inception picks: params.picks = ['stock:<uuid>', 'fund:<mstar>', ...]."""
    params = p["params"] if isinstance(p["params"], dict) else json.loads(p["params"])
    picks = [k.split(":", 1)[1] for k in params.get("picks", [])]
    known = set(universe["instrument_key"])
    missing = [k for k in picks if k not in known]
    if missing:
        raise SystemExit(f"basket picks not in universe: {missing}")
    return pd.Series(True, index=picks)


def _basket_weights(p: dict) -> dict[str, Decimal] | None:
    """params.weights = {'stock:<uuid>': 0.20, 'fund:<mstar>': 0.15, ...} (fractions
    of capital) → {instrument_key: Decimal}. None ⇒ equal-weight (legacy baskets)."""
    params = p["params"] if isinstance(p["params"], dict) else json.loads(p["params"])
    w = params.get("weights")
    if not w:
        return None
    return {k.split(":", 1)[1]: Decimal(str(v)) for k, v in w.items()}


def run_window(p: dict, start: dt.date, end: dt.date, mode: str):
    """Load panels and replay. Modes: backtest / init / resume (see _run_slice).

    Fund cap portfolios: params.fund_categories restricts the universe. A capital-
    weighted BLEND (params.sleeves = [{weight, categories}, ...], e.g. 50/25/25
    LC/MC/SC) runs one INDEPENDENT slice per sleeve with its own capital budget and
    the union is merged — each sleeve manages its own cash, which is exactly what a
    fixed-allocation mandate means.
    """
    params = p["params"] if isinstance(p["params"], dict) else json.loads(p["params"])
    sleeves = params.get("sleeves")
    if sleeves:
        cap = Decimal(p["initial_capital"])
        results = [
            _run_slice(
                p,
                start,
                end,
                mode,
                fund_categories=s["categories"],
                capital=(cap * Decimal(str(s["weight"]))).quantize(Decimal("0.01")),
            )
            for i, s in enumerate(sleeves)
        ]
        trades = (
            pd.concat([t for t, _ in results if not t.empty], ignore_index=True)
            if any(not t.empty for t, _ in results)
            else results[0][0]
        )
        navs = _merge_navs([n for _, n in results if not n.empty])
        return trades, navs
    return _run_slice(p, start, end, mode, fund_categories=params.get("fund_categories"))


def _merge_navs(nav_frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Sum sleeve NAV rows by date (sleeves share the fund session calendar)."""
    if not nav_frames:
        import atlas.portfolio.engine as _e

        return _e._empty_navs()
    alln = pd.concat(nav_frames, ignore_index=True)
    return pd.DataFrame(
        alln.groupby("date", as_index=False).agg(
            nav=("nav", "sum"),
            cash=("cash", "sum"),
            invested=("invested", "sum"),
            n_positions=("n_positions", "sum"),
        )
    )


def _run_slice(
    p: dict,
    start: dt.date,
    end: dt.date,
    mode: str,
    fund_categories: list | None = None,
    capital: Decimal | None = None,
):
    """One independent replay over a (optionally cap-filtered) universe.
    `capital` is set only for blend sleeves; sleeve resume state is scoped by the
    sleeve.s stable fund categories, its cash reconstructed from its own trades."""
    universe = load_universe(list(p["asset_classes"]), fund_categories=fund_categories)
    strat = _strategy(p)
    pid = str(p["portfolio_id"])
    # RESUME: a held name that has left the scored/current universe must still be
    # priced, marked and exitable — never silently dropped. Add held instruments
    # (scoped to this sleeve's categories for a blend) back into the universe.
    if mode == "resume":
        held = set(open_positions(pid))
        if capital is not None and fund_categories:
            held &= set(load_universe(["fund"], fund_categories=fund_categories)["instrument_key"])
        missing = held - set(universe["instrument_key"])
        if missing:
            universe = pd.concat([universe, load_instruments(list(missing))], ignore_index=True)
    lookback = start - dt.timedelta(days=14)  # covers prior sessions for transitions + ffill
    prices = load_prices(universe, lookback, end)
    # Full panel always goes to the engine (valuation carry-forward + inception price
    # lookback need pre-window history); only the DAY-LOOP dates differ by mode.
    if mode == "init":
        loop_dates = list(prices.index[-1:])
    elif mode == "backtest":
        loop_dates = [d for d in prices.index if d >= start]
    else:
        loop_dates = [d for d in prices.index if d > start]
    if not loop_dates:
        return _no_op()

    # FM rule (2026-07-03): a strategy portfolio NEVER buys names already past their
    # crossover — it starts 100% cash and enters only on crossover EVENTS from its
    # window onward (init books nothing; the nightly mark takes it from there).
    # Only FM baskets seed holdings at inception (those are explicit picks).
    # rank/rotation strategies need pre-window history for their signals
    sig_lookback = min(lookback, start - dt.timedelta(days=200))
    composite = load_composite(universe, sig_lookback, end)
    events, inception, inception_weights = None, None, None
    if strat is not None:
        if mode != "init":
            cols = strat.required_columns()
            if cols:
                tech = load_tech(universe, cols, sig_lookback, end)
                if getattr(strat, "needs_composite", False):
                    tech = tech.merge(composite, on=["instrument_key", "date"], how="left")
            else:
                tech = composite.copy()  # composite IS the panel (rank strategies)
            if getattr(strat, "needs_sector", False):
                tech = tech.merge(
                    universe[["instrument_key", "sector"]], on="instrument_key", how="left"
                )
            if getattr(strat, "needs_regime", False):
                regime = _db.read_df(
                    f"""select date, regime_state from {M}.atlas_market_regime_daily
                        where date between :a and :b""",
                    {"a": sig_lookback, "b": end},
                )
                tech = tech.merge(regime, on="date", how="left")
            if getattr(strat, "membership", False):
                # membership strategies: state before `start` informs the scan;
                # emissions begin AT `start` (current members enter at next close)
                events = strat.events(tech, floor=start)
            else:
                events = strat.events(tech)
                events = events[events["date"] >= start]
    elif mode != "resume":
        inception = _basket_state(p, universe)
        inception_weights = _basket_weights(p)

    costs, _rates, exit_load = load_cost_tax()
    cfg = _cfg(p)
    if capital is not None:  # blend sleeve runs on its own capital budget
        cfg = replace(cfg, initial_capital=capital)

    start_positions = start_cash = start_entry_dates = None
    if mode == "resume":
        all_pos = open_positions(pid)
        all_ent = open_entry_dates(pid)
        if capital is None:
            # plain portfolio: the whole book + the authoritative stored cash. NO
            # universe scoping — that was the drift bug (a de-scored holding would
            # vanish and its capital get refunded).
            start_positions, start_entry_dates = all_pos, all_ent
            start_cash = stored_live_cash(pid)
        else:
            # blend sleeve: scope to this sleeve's (stable-category) fund universe;
            # cash reconstructed from this sleeve's own trades.
            keys = set(universe["instrument_key"])
            start_positions = {k: q for k, q in all_pos.items() if k in keys}
            start_entry_dates = {k: d for k, d in all_ent.items() if k in keys}
            start_cash = _slice_cash(pid, keys, cfg.initial_capital)

    return replay(
        cfg,
        prices=prices,
        events=events,
        inception_state=inception,
        composite=composite,
        asset_class=dict(zip(universe["instrument_key"], universe["asset_class"], strict=False)),
        symbols=dict(zip(universe["instrument_key"], universe["symbol"], strict=False)),
        start_positions=start_positions,
        start_cash=start_cash,
        loop_dates=loop_dates,
        costs=costs,
        exit_load=exit_load,
        start_entry_dates=start_entry_dates,
        inception_weights=inception_weights,
    )


def _slice_cash(pid: str, keys: set, capital: Decimal) -> Decimal:
    """Reconstruct a sleeve's live cash from the trades of its own instruments:
    capital − Σ(buy value+cost) + Σ(sell value−cost). Stateless, so a blend never
    needs per-sleeve cash stored. For a plain (non-sleeve) portfolio keys covers
    every instrument, so this equals the stored NAV cash."""
    df = _db.read_df(
        f"""select instrument_key,
                   sum(case when side='buy' then -(value + coalesce(cost,0))
                            else (value - coalesce(cost,0)) end) flow
            from {M}.portfolio_trades where portfolio_id = :p and run_type = 'live'
            group by 1""",
        {"p": pid},
    )
    flow = sum(
        (Decimal(str(r["flow"])) for r in df.to_dict("records") if r["instrument_key"] in keys),
        Decimal(0),
    )
    return (capital + flow).quantize(Decimal("0.01"))


def _no_op():
    import atlas.portfolio.engine as _e

    return _e._empty_trades(), _e._empty_navs()


# ── subcommands ────────────────────────────────────────────────────────────


def cmd_create(a) -> None:
    th = _db.read_df(
        f"select threshold_key, threshold_value from {M}.atlas_thresholds "
        "where category='portfolio' and is_active"
    )
    th = dict(zip(th["threshold_key"], th["threshold_value"], strict=False))
    capital = a.capital or th["portfolio_default_capital"]
    cap_pct = a.cap_pct or th["portfolio_max_position_pct"]
    params = json.loads(a.params) if a.params else {}
    if a.kind == "strategy":
        get_strategy(a.strategy, _strat_params(params))  # validates key + params before insert
    pid = str(uuid.uuid4())
    _db.exec_sql(
        f"""insert into {M}.portfolio_master
            (portfolio_id, name, kind, origin, strategy_key, params, asset_classes,
             initial_capital, max_position_pct, inception_date)
            values (:id, :name, :kind, :origin, :sk, cast(:params as jsonb), :ac,
                    :cap, :pct, :inc)""",
        {
            "id": pid,
            "name": a.name,
            "kind": a.kind,
            "origin": a.origin,
            "sk": a.strategy if a.kind == "strategy" else None,
            "params": json.dumps(params),
            "ac": a.asset_classes,
            "cap": Decimal(capital),
            "pct": Decimal(cap_pct),
            "inc": _db.eod_cutoff(),
        },
    )
    print(json.dumps({"portfolio_id": pid}))


def cmd_init(a) -> None:
    p = load_portfolio(a.portfolio_id)
    if (
        open_positions(a.portfolio_id)
        or not _db.read_df(
            f"select 1 from {M}.portfolio_nav_daily where portfolio_id=:p and run_type='live' limit 1",
            {"p": a.portfolio_id},
        ).empty
    ):
        raise SystemExit("portfolio already initialized — use mark")
    run_id = str(uuid.uuid4())
    inc = p["inception_date"]
    trades, navs = run_window(p, inc, inc, "init")
    _, rates, _el = load_cost_tax()
    trades = _enrich_new_trades(a.portfolio_id, "live", trades, rates)
    write_results(a.portfolio_id, "live", run_id, trades, navs)
    print(json.dumps({"trades": len(trades), "nav_date": str(navs.iloc[0]["date"])}))


def cmd_mark(a) -> None:
    eod = _db.eod_cutoff()
    ports = _db.read_df(
        f"select portfolio_id::text pid from {M}.portfolio_master where status='active'"
    )
    done = skipped = 0
    for pid in ports["pid"]:
        p = load_portfolio(pid)
        last = _db.scalar(
            f"select max(date) from {M}.portfolio_nav_daily where portfolio_id=:p and run_type='live'",
            {"p": pid},
        )
        if last is None:
            print(f"[mark] {p['name']}: not initialized — skipping", flush=True)
            skipped += 1
            continue
        if last >= eod:
            skipped += 1
            continue
        run_id = str(uuid.uuid4())
        trades, navs = run_window(p, last, eod, "resume")
        _, rates, _el = load_cost_tax()
        trades = _enrich_new_trades(pid, "live", trades, rates)
        write_results(pid, "live", run_id, trades, navs)
        done += 1
        print(f"[mark] {p['name']}: +{len(navs)} nav rows, {len(trades)} trades", flush=True)
    print(f"[mark] COMPLETE marked={done} skipped={skipped}", flush=True)


def _summary(navs: pd.DataFrame, trades: pd.DataFrame) -> dict:
    nav = navs.set_index("date")["nav"].astype(float)
    out = {"start": str(nav.index[0]), "end": str(nav.index[-1]), "n_trades": len(trades)}
    peak = nav.cummax()
    out["max_drawdown_pct"] = round(float(((nav - peak) / peak).min()) * 100, 2)
    last_date = cast(dt.date, nav.index[-1])
    for label, days in (("1y", 365), ("3y", 365 * 3), ("5y", 365 * 5)):
        anchor = last_date - dt.timedelta(days=days)
        base = cast(pd.Series, nav[nav.index <= anchor])
        if not base.empty:
            out[f"return_{label}_pct"] = round((nav.iloc[-1] / base.iloc[-1] - 1) * 100, 2)
    out["total_return_pct"] = round((nav.iloc[-1] / nav.iloc[0] - 1) * 100, 2)
    return out


def rebuild_backtest(pid: str, years: float = 5) -> dict:
    """Delete + replay the backtest run for one portfolio (idempotent). Returns the
    summary dict. Reusable by the CLI and by portfolio_evolve on a policy promotion."""
    p = load_portfolio(pid)
    eod = _db.eod_cutoff()
    start = eod - dt.timedelta(days=int(years * 365))
    run_id = str(uuid.uuid4())
    with _db.engine().begin() as conn:
        from sqlalchemy import text

        for tbl in ("portfolio_trades", "portfolio_nav_daily"):
            conn.execute(
                text(f"delete from {M}.{tbl} where portfolio_id=:p and run_type='backtest'"),
                {"p": pid},
            )
    trades, navs = run_window(p, start, eod, "backtest")
    _, rates, _el = load_cost_tax()
    enriched = enrich_trades(trades, rates) if not trades.empty else trades
    persist = enriched.drop(columns=["realized_st", "realized_lt"], errors="ignore")
    write_results(pid, "backtest", run_id, persist, navs)
    out = _summary(navs, trades)
    if not trades.empty and (trades["side"] == "sell").any():
        s = summarize(enriched, rates)
        out["tax_total"] = float(s["tax_total"])
        out["post_tax_total_return_pct"] = round(
            (float(navs.iloc[-1]["nav"]) - float(s["tax_total"])) / float(navs.iloc[0]["nav"]) * 100
            - 100,
            2,
        )
    return out


def cmd_backtest(a) -> None:
    print(json.dumps(rebuild_backtest(a.portfolio_id, a.years), default=str))


def book_trade(pid: str, side: str, ckey: str) -> dict:
    """Book ONE trade for a basket-kind portfolio at the last EOD close, with
    cost + FIFO tax enrichment and a refreshed NAV row. `ckey` = <asset_class>:<key>.
    Shared by the manual CLI and the Atlas Desk orchestrator — every booked trade
    goes through this single audited path. Raises TradeError on any refusal."""
    p = load_portfolio(pid)
    if p["kind"] != "basket":
        raise TradeError("manual trades are for baskets only")
    ac, key = ckey.split(":", 1)
    universe = load_universe([ac])
    row = universe.loc[universe["instrument_key"] == key]
    if row.empty:
        raise TradeError(f"{ckey} not in the {ac} universe")
    eod = _db.eod_cutoff()
    series = cast(pd.Series, load_prices(row, eod - dt.timedelta(days=10), eod)[key]).dropna()
    price, trade_date = Decimal(series.iloc[-1]), series.index[-1]
    positions = open_positions(pid)
    last = _db.read_df(
        f"""select nav, cash from {M}.portfolio_nav_daily
            where portfolio_id=:p and run_type='live' order by date desc limit 1""",
        {"p": pid},
    )
    if last.empty:
        raise TradeError("portfolio not initialized")
    nav, cash = Decimal(last.iloc[0]["nav"]), Decimal(last.iloc[0]["cash"])
    costs, rates, exit_load = load_cost_tax()
    buy_rate, sell_rate = costs[ac]
    if side == "buy":
        if key in positions:
            raise TradeError("already held — sell first or extend engine for top-ups")
        alloc = min(nav * Decimal(p["max_position_pct"]), cash)
        qty = _qty_for(alloc / (1 + buy_rate), price, ac)
        if qty <= 0:
            raise TradeError("insufficient cash for one unit")
    else:
        if key not in positions:
            raise TradeError("not held")
        qty = positions[key]
    value = (qty * price).quantize(Decimal("0.01"))
    cost = (value * (buy_rate if side == "buy" else sell_rate)).quantize(Decimal("0.01"))
    if side == "sell" and ac == "fund":  # MF exit load if redeemed within the window
        entry = open_entry_dates(pid).get(key)
        if entry is not None and (trade_date - entry).days < exit_load[1]:
            cost += (value * exit_load[0]).quantize(Decimal("0.01"))
    trades = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "asset_class": ac,
                "instrument_key": key,
                "symbol": row.iloc[0]["symbol"],
                "side": side,
                "qty": qty,
                "price": price,
                "value": value,
                "cost": cost,
                "reason": "manual",
            }
        ]
    )
    trades = _enrich_new_trades(pid, "live", trades, rates)
    run_id = str(uuid.uuid4())
    write_results(pid, "live", run_id, trades, pd.DataFrame())
    # refresh today's NAV row to reflect the trade
    new_cash = cash - value - cost if side == "buy" else cash + value - cost
    positions = open_positions(pid)
    universe_all = load_universe(list(p["asset_classes"]))
    held = universe_all.loc[universe_all["instrument_key"].isin(positions)]
    invested = Decimal("0")
    if not held.empty:
        px = load_prices(held, eod - dt.timedelta(days=10), eod).ffill()
        invested = sum(
            (positions[k] * Decimal(px.iloc[-1][k]) for k in positions), Decimal("0")
        ).quantize(Decimal("0.01"))
    navs = pd.DataFrame(
        [
            {
                "date": trade_date,
                "nav": (new_cash + invested).quantize(Decimal("0.01")),
                "cash": new_cash.quantize(Decimal("0.01")),
                "invested": invested,
                "n_positions": len(positions),
            }
        ]
    )
    write_results(pid, "live", run_id, pd.DataFrame(), navs)
    return {
        "side": side,
        "symbol": str(row.iloc[0]["symbol"]),
        "qty": str(qty),
        "price": str(price),
        "value": str(value),
        "trade_date": str(trade_date),
    }


def cmd_trade(a) -> None:
    try:
        print(json.dumps(book_trade(a.portfolio_id, a.side, a.key)))
    except TradeError as e:
        raise SystemExit(str(e)) from e


def main():
    ap = argparse.ArgumentParser(description="Portfolio runner (init/backtest/mark/trade)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create")
    c.add_argument("--name", required=True)
    c.add_argument("--kind", choices=["strategy", "basket"], required=True)
    c.add_argument("--strategy", default=None)
    c.add_argument(
        "--params", default=None, help='JSON, e.g. {"fast":50,"slow":200} or {"picks":[...]}'
    )
    c.add_argument(
        "--asset-classes", nargs="+", default=["stock"], choices=["stock", "etf", "fund"]
    )
    c.add_argument("--capital", type=Decimal, default=None)
    c.add_argument("--cap-pct", type=Decimal, default=None)
    c.add_argument("--origin", choices=["fm", "system"], default="fm")
    c.set_defaults(fn=cmd_create)

    i = sub.add_parser("init")
    i.add_argument("--portfolio-id", required=True)
    i.set_defaults(fn=cmd_init)

    b = sub.add_parser("backtest")
    b.add_argument("--portfolio-id", required=True)
    b.add_argument("--years", type=float, default=5)
    b.set_defaults(fn=cmd_backtest)

    m = sub.add_parser("mark")
    m.set_defaults(fn=cmd_mark)

    t = sub.add_parser("trade")
    t.add_argument("--portfolio-id", required=True)
    t.add_argument("--side", choices=["buy", "sell"], required=True)
    t.add_argument("--key", required=True, help="<asset_class>:<instrument_key>")
    t.set_defaults(fn=cmd_trade)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
