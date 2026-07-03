#!/usr/bin/env python3
"""Portfolio runner — ALL I/O for the atlas.portfolio engine (which is pure).

    python portfolio_run.py create --name "Golden Cross 50/200" --kind strategy \
        --strategy ema_cross --params '{"fast":50,"slow":200}'      # prints {portfolio_id}
    python portfolio_run.py init --portfolio-id <uuid>              # inception trades + first NAV
    python portfolio_run.py backtest --portfolio-id <uuid> [--years 5]  # replay + JSON summary
    python portfolio_run.py mark                                    # nightly: all active portfolios
    python portfolio_run.py trade --portfolio-id <uuid> --side buy --key stock:<uuid>

Timing contract (see atlas/portfolio/engine.py): signals detected at close of
session e execute at the close of the next session; everything anchors to the
last complete EOD (_db.eod_cutoff) — never an in-session partial candle.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import cast

import _db
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atlas.portfolio import PortfolioConfig, get_strategy, replay
from atlas.portfolio.engine import _qty_for

M = "atlas_foundation"


# ── loaders ────────────────────────────────────────────────────────────────


def load_portfolio(pid: str) -> dict:
    df = _db.read_df(f"select * from {M}.portfolio_master where portfolio_id = :p", {"p": pid})
    if df.empty:
        raise SystemExit(f"portfolio {pid} not found")
    return df.iloc[0].to_dict()


def load_universe(asset_classes: list[str]) -> pd.DataFrame:
    """(instrument_key, asset_class, symbol) for the portfolio's declared universe."""
    parts = []
    eq = [c for c in asset_classes if c in ("stock", "etf")]
    if eq:
        # Stocks are the SCORED universe (Nifty 500 as ranked by the lens pipeline),
        # not every listed name — composite ranking is the FM's selection rule.
        parts.append(
            _db.read_df(
                f"""select i.instrument_id::text as instrument_key, i.asset_class, i.symbol
                    from {M}.instrument_master i
                    where i.is_active and i.kite_token is not null and i.asset_class = any(:ac)
                      and (i.asset_class <> 'stock' or exists (
                            select 1 from {M}.atlas_lens_scores_daily s
                            where s.instrument_id = i.instrument_id
                              and s.date = (select max(date) from {M}.atlas_lens_scores_daily)))""",
                {"ac": eq},
            )
        )
    if "fund" in asset_classes:
        f = _db.read_df(f"select mstar_id, scheme_name from {M}.atlas_universe_funds")
        parts.append(
            pd.DataFrame(
                {
                    "instrument_key": f["mstar_id"],
                    "asset_class": "fund",
                    "symbol": f["scheme_name"],
                }
            )
        )
    return (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame(columns=pd.Index(["instrument_key", "asset_class", "symbol"]))
    )


def load_tech(
    universe: pd.DataFrame, cols: tuple[str, ...], since: dt.date, until: dt.date
) -> pd.DataFrame:
    """EMA panel (instrument_key, date, <cols>) across asset classes."""
    collist = ", ".join(cols)
    parts = []
    if (universe["asset_class"] != "fund").any():
        parts.append(
            _db.read_df(
                f"""select t.instrument_id::text as instrument_key, t.date, {collist}
                    from {M}.technical_daily t
                    where t.instrument_id::text = any(:ks) and t.date between :a and :b
                    order by t.date""",
                {
                    "ks": universe.loc[
                        universe["asset_class"] != "fund", "instrument_key"
                    ].tolist(),
                    "a": since,
                    "b": until,
                },
            )
        )
    if (universe["asset_class"] == "fund").any():
        parts.append(
            _db.read_df(
                f"""select mstar_id as instrument_key, date, {collist}
                    from {M}.technical_fund_daily
                    where mstar_id = any(:ks) and date between :a and :b order by date""",
                {
                    "ks": universe.loc[
                        universe["asset_class"] == "fund", "instrument_key"
                    ].tolist(),
                    "a": since,
                    "b": until,
                },
            )
        )
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def load_prices(universe: pd.DataFrame, since: dt.date, until: dt.date) -> pd.DataFrame:
    """Date-indexed price panel (Decimal), one column per instrument_key, ffilled."""
    parts = []
    by_class = {c: g["instrument_key"].tolist() for c, g in universe.groupby("asset_class")}
    if by_class.get("stock"):
        parts.append(
            _db.read_df(
                f"""select instrument_id::text as instrument_key, date, close_adj as price
                    from {M}.ohlcv_stock
                    where instrument_id::text = any(:ks) and close_adj > 0
                      and date between :a and :b""",
                {"ks": by_class["stock"], "a": since, "b": until},
            )
        )
    if by_class.get("etf"):
        parts.append(
            _db.read_df(
                f"""select i.instrument_id::text as instrument_key, o.date, o.close_adj as price
                    from {M}.ohlcv_etf o
                    join {M}.instrument_master i on i.symbol = o.ticker and i.asset_class = 'etf'
                    where i.instrument_id::text = any(:ks) and o.close_adj > 0
                      and o.date between :a and :b""",
                {"ks": by_class["etf"], "a": since, "b": until},
            )
        )
    if by_class.get("fund"):
        parts.append(
            _db.read_df(
                f"""select mstar_id as instrument_key, nav_date as date, nav as price
                    from {M}.de_mf_nav_daily
                    where mstar_id = any(:ks) and nav > 0 and nav_date between :a and :b""",
                {"ks": by_class["fund"], "a": since, "b": until},
            )
        )
    long = pd.concat(parts, ignore_index=True)
    if long.empty:
        raise SystemExit("no prices in window — check universe/asset_classes")
    panel = long.pivot_table(
        index="date", columns="instrument_key", values="price", aggfunc="last"
    ).sort_index()
    # Day-loop calendar = REAL NSE sessions (NIFTY 50). A handful of instruments carry
    # spurious holiday rows; without this the engine booked trades on Republic Day.
    sessions = _db.read_df(
        f"""select date from {M}.index_prices
            where index_code = 'NIFTY 50' and date between :a and :b order by date""",
        {"a": since, "b": until},
    )["date"]
    return panel.reindex(sessions.tolist())


def load_composite(universe: pd.DataFrame, since: dt.date, until: dt.date) -> pd.DataFrame:
    return _db.read_df(
        f"""select instrument_id::text as instrument_key, date, composite
            from {M}.atlas_lens_scores_daily
            where instrument_id::text = any(:ks) and date between :a and :b""",
        {"ks": universe["instrument_key"].tolist(), "a": since, "b": until},
    )


def open_positions(pid: str, run_type: str = "live") -> dict[str, Decimal]:
    df = _db.read_df(
        f"""select instrument_key,
                   sum(case when side='buy' then qty else -qty end) as qty
            from {M}.portfolio_trades
            where portfolio_id = :p and run_type = :r group by 1""",
        {"p": pid, "r": run_type},
    )
    return {
        r["instrument_key"]: Decimal(r["qty"])
        for r in df.to_dict("records")
        if Decimal(r["qty"]) != 0
    }


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


def _strategy(p: dict):
    if p["kind"] != "strategy":
        return None
    params = p["params"] if isinstance(p["params"], dict) else json.loads(p["params"])
    return get_strategy(p["strategy_key"], params)


def _basket_state(p: dict, universe: pd.DataFrame) -> pd.Series:
    """A basket's inception picks: params.picks = ['stock:<uuid>', 'fund:<mstar>', ...]."""
    params = p["params"] if isinstance(p["params"], dict) else json.loads(p["params"])
    picks = [k.split(":", 1)[1] for k in params.get("picks", [])]
    known = set(universe["instrument_key"])
    missing = [k for k in picks if k not in known]
    if missing:
        raise SystemExit(f"basket picks not in universe: {missing}")
    return pd.Series(True, index=picks)


def run_window(p: dict, start: dt.date, end: dt.date, mode: str):
    """Load panels and replay. Modes:
    backtest — day-loop over trading dates in [start, end], inception-seeded at the first
    init     — single-day loop at the last trading date <= end; strategies book
               NOTHING (all-cash first NAV row), baskets book the FM's picks
    resume   — continue live state over trading dates AFTER `start` (= last marked date);
               only signals detected on/after `start` are eligible (one shot each,
               same as backtest semantics)
    """
    universe = load_universe(list(p["asset_classes"]))
    strat = _strategy(p)
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
    events, inception = None, None
    if strat is not None:
        if mode != "init":
            tech = load_tech(universe, strat.required_columns(), lookback, end)
            events = strat.events(tech)
            events = events[events["date"] >= start]
    elif mode != "resume":
        inception = _basket_state(p, universe)

    start_positions = start_cash = None
    if mode == "resume":
        start_positions = open_positions(str(p["portfolio_id"]))
        last = _db.read_df(
            f"""select cash from {M}.portfolio_nav_daily
                where portfolio_id=:p and run_type='live' order by date desc limit 1""",
            {"p": str(p["portfolio_id"])},
        )
        start_cash = Decimal(last.iloc[0]["cash"])
    return replay(
        _cfg(p),
        prices=prices,
        events=events,
        inception_state=inception,
        composite=load_composite(universe, lookback, end),
        asset_class=dict(zip(universe["instrument_key"], universe["asset_class"], strict=False)),
        symbols=dict(zip(universe["instrument_key"], universe["symbol"], strict=False)),
        start_positions=start_positions,
        start_cash=start_cash,
        loop_dates=loop_dates,
    )


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
        get_strategy(a.strategy, params)  # validates key + params before insert
    pid = str(uuid.uuid4())
    _db.exec_sql(
        f"""insert into {M}.portfolio_master
            (portfolio_id, name, kind, strategy_key, params, asset_classes,
             initial_capital, max_position_pct, inception_date)
            values (:id, :name, :kind, :sk, cast(:params as jsonb), :ac,
                    :cap, :pct, :inc)""",
        {
            "id": pid,
            "name": a.name,
            "kind": a.kind,
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


def cmd_backtest(a) -> None:
    p = load_portfolio(a.portfolio_id)
    eod = _db.eod_cutoff()
    start = eod - dt.timedelta(days=int(a.years * 365))
    run_id = str(uuid.uuid4())
    with _db.engine().begin() as conn:
        from sqlalchemy import text

        for tbl in ("portfolio_trades", "portfolio_nav_daily"):
            conn.execute(
                text(f"delete from {M}.{tbl} where portfolio_id=:p and run_type='backtest'"),
                {"p": a.portfolio_id},
            )
    trades, navs = run_window(p, start, eod, "backtest")
    write_results(a.portfolio_id, "backtest", run_id, trades, navs)
    print(json.dumps(_summary(navs, trades), default=str))


def cmd_trade(a) -> None:
    p = load_portfolio(a.portfolio_id)
    if p["kind"] != "basket":
        raise SystemExit("manual trades are for baskets only")
    ac, key = a.key.split(":", 1)
    universe = load_universe([ac])
    row = universe.loc[universe["instrument_key"] == key]
    if row.empty:
        raise SystemExit(f"{a.key} not in the {ac} universe")
    eod = _db.eod_cutoff()
    series = cast(pd.Series, load_prices(row, eod - dt.timedelta(days=10), eod)[key]).dropna()
    price, trade_date = Decimal(series.iloc[-1]), series.index[-1]
    positions = open_positions(a.portfolio_id)
    last = _db.read_df(
        f"""select nav, cash from {M}.portfolio_nav_daily
            where portfolio_id=:p and run_type='live' order by date desc limit 1""",
        {"p": a.portfolio_id},
    )
    if last.empty:
        raise SystemExit("portfolio not initialized")
    nav, cash = Decimal(last.iloc[0]["nav"]), Decimal(last.iloc[0]["cash"])
    if a.side == "buy":
        if key in positions:
            raise SystemExit("already held — sell first or extend engine for top-ups")
        qty = _qty_for(min(nav * Decimal(p["max_position_pct"]), cash), price, ac)
        if qty <= 0:
            raise SystemExit("insufficient cash for one unit")
    else:
        if key not in positions:
            raise SystemExit("not held")
        qty = positions[key]
    value = (qty * price).quantize(Decimal("0.01"))
    trades = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "asset_class": ac,
                "instrument_key": key,
                "symbol": row.iloc[0]["symbol"],
                "side": a.side,
                "qty": qty,
                "price": price,
                "value": value,
                "reason": "manual",
            }
        ]
    )
    run_id = str(uuid.uuid4())
    write_results(a.portfolio_id, "live", run_id, trades, pd.DataFrame())
    # refresh today's NAV row to reflect the trade
    new_cash = cash - value if a.side == "buy" else cash + value
    positions = open_positions(a.portfolio_id)
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
    write_results(a.portfolio_id, "live", run_id, pd.DataFrame(), navs)
    print(
        json.dumps(
            {
                "side": a.side,
                "symbol": row.iloc[0]["symbol"],
                "qty": str(qty),
                "price": str(price),
                "value": str(value),
            }
        )
    )


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
