#!/usr/bin/env python3
"""Portfolio correctness gate — asserts on REAL produced output (rule #0).

Run nightly after portfolio_run.py mark (and ad hoc after any backtest):

    python validate_portfolios.py          # exit 1 on any failure

Checks, per portfolio and run_type:
  A. every ACTIVE initialized portfolio has a live NAV row at the last EOD
  B. latest NAV reconciles: cash + Σ(open qty × stored price) == nav (±0.01/position)
  C. every trade is priced at the stored adjusted close/NAV for its date
  D. cash never negative on any NAV row
  E. every buy's value respects the position cap vs that day's NAV
"""

from __future__ import annotations

import sys
from decimal import Decimal

import _db

M = "atlas_foundation"

# One price surface for all three asset classes. Takes a :px_floor date param so
# the planner can range-scan the PK indexes instead of materializing full history.
_PRICE_SQL = f"""
    with px as (
        select 'stock' asset_class, instrument_id::text instrument_key, date, close_adj price
        from {M}.ohlcv_stock where close_adj > 0 and date >= :px_floor
        union all
        select 'etf', i.instrument_id::text, o.date, o.close_adj
        from {M}.ohlcv_etf o
        join {M}.instrument_master i on i.symbol = o.ticker and i.asset_class = 'etf'
        where o.close_adj > 0 and o.date >= :px_floor
        union all
        select 'fund', mstar_id, nav_date, nav from {M}.de_mf_nav_daily
        where nav > 0 and nav_date >= :px_floor
    )
"""

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL: {msg}", flush=True)


def check_a_marked_at_eod() -> None:
    eod = _db.eod_cutoff()
    df = _db.read_df(
        f"""select m.name, max(n.date) last
            from {M}.portfolio_master m
            join {M}.portfolio_nav_daily n
              on n.portfolio_id = m.portfolio_id and n.run_type = 'live'
            where m.status = 'active' group by 1""",
    )
    for r in df.to_dict("records"):
        # the EOD cutoff can be a holiday/weekend; fresh == last trading day covered
        lag = _db.scalar(
            f"select count(distinct date) from {M}.ohlcv_stock where date > :a and date <= :b",
            {"a": r["last"], "b": eod},
        )
        if lag and lag > 0:
            fail(
                f"A: {r['name']} live NAV stale — last={r['last']}, {lag} session(s) behind EOD {eod}"
            )


def check_b_nav_reconciles() -> None:
    floor = _db.scalar(
        f"select min(d) - 21 from (select max(date) d from {M}.portfolio_nav_daily group by portfolio_id, run_type) x"
    )
    if floor is None:
        return
    df = _db.read_df(
        _PRICE_SQL
        + f""",
        latest as (
            select portfolio_id, run_type, max(date) date
            from {M}.portfolio_nav_daily group by 1, 2
        ),
        pos as (
            select t.portfolio_id, t.run_type, t.asset_class, t.instrument_key, l.date,
                   sum(case when t.side = 'buy' then t.qty else -t.qty end) qty
            from {M}.portfolio_trades t
            join latest l using (portfolio_id, run_type)
            where t.trade_date <= l.date
            group by 1, 2, 3, 4, 5
            having sum(case when t.side = 'buy' then t.qty else -t.qty end) <> 0
        ),
        valued as (
            select p.portfolio_id, p.run_type, p.date,
                   sum(p.qty * (select px.price from px
                                where px.asset_class = p.asset_class
                                  and px.instrument_key = p.instrument_key
                                  and px.date <= p.date
                                order by px.date desc limit 1)) invested,
                   count(*) n_pos
            from pos p group by 1, 2, 3
        )
        select m.name, n.run_type, n.date, n.nav, n.cash, n.invested stored_invested,
               coalesce(v.invested, 0) calc_invested, coalesce(v.n_pos, 0) calc_pos, n.n_positions
        from {M}.portfolio_nav_daily n
        join latest l on (l.portfolio_id, l.run_type, l.date) = (n.portfolio_id, n.run_type, n.date)
        left join valued v on (v.portfolio_id, v.run_type) = (n.portfolio_id, n.run_type)
        join {M}.portfolio_master m on m.portfolio_id = n.portfolio_id
        """,
        {"px_floor": floor},
    )
    for r in df.to_dict("records"):
        tol = Decimal("0.01") * (r["calc_pos"] + 1)
        if abs(Decimal(r["nav"]) - (Decimal(r["cash"]) + Decimal(r["calc_invested"]))) > tol:
            fail(
                f"B: {r['name']}/{r['run_type']} nav {r['nav']} != cash {r['cash']} + "
                f"recomputed invested {r['calc_invested']} on {r['date']}"
            )
        if r["calc_pos"] != r["n_positions"]:
            fail(
                f"B: {r['name']}/{r['run_type']} n_positions {r['n_positions']} != derived {r['calc_pos']}"
            )


def check_c_trade_prices() -> None:
    # Exact-date PK joins per asset class (trades span years — no bounded union here).
    df = _db.read_df(
        f"""select m.name, t.run_type, t.symbol, t.trade_date, t.price,
                   coalesce(o.close_adj, e.close_adj, f.nav) stored
            from {M}.portfolio_trades t
            join {M}.portfolio_master m using (portfolio_id)
            left join {M}.ohlcv_stock o
              on t.asset_class = 'stock'
             and o.instrument_id::text = t.instrument_key and o.date = t.trade_date
            left join {M}.instrument_master i
              on t.asset_class = 'etf' and i.instrument_id::text = t.instrument_key
            left join {M}.ohlcv_etf e
              on i.symbol = e.ticker and e.date = t.trade_date
            left join {M}.de_mf_nav_daily f
              on t.asset_class = 'fund'
             and f.mstar_id = t.instrument_key and f.nav_date = t.trade_date
            where coalesce(o.close_adj, e.close_adj, f.nav) is distinct from t.price"""
    )
    for r in df.to_dict("records"):
        fail(
            f"C: {r['name']}/{r['run_type']} {r['symbol']} @ {r['trade_date']} traded {r['price']} "
            f"!= stored {r['stored']}"
        )


def check_d_cash_never_negative() -> None:
    df = _db.read_df(
        f"""select m.name, n.run_type, min(n.cash) worst
            from {M}.portfolio_nav_daily n join {M}.portfolio_master m using (portfolio_id)
            group by 1, 2 having min(n.cash) < 0"""
    )
    for r in df.to_dict("records"):
        fail(f"D: {r['name']}/{r['run_type']} cash went negative ({r['worst']})")


def check_e_position_cap() -> None:
    df = _db.read_df(
        f"""select m.name, t.run_type, t.symbol, t.trade_date, t.value, n.nav, m.max_position_pct
            from {M}.portfolio_trades t
            join {M}.portfolio_master m using (portfolio_id)
            join {M}.portfolio_nav_daily n
              on (n.portfolio_id, n.run_type, n.date) = (t.portfolio_id, t.run_type, t.trade_date)
            where t.side = 'buy'
              and t.value > n.nav * m.max_position_pct * 1.001"""
    )
    for r in df.to_dict("records"):
        fail(
            f"E: {r['name']}/{r['run_type']} buy {r['symbol']} {r['value']} on {r['trade_date']} "
            f"exceeds cap {r['max_position_pct']} of nav {r['nav']}"
        )


def check_f_cost_cash_identity_and_ledger() -> None:
    # Full-history cash identity INCLUDING execution costs: latest stored cash must
    # equal initial capital plus every signed flow (buy: -(value+cost), sell: value-cost).
    df = _db.read_df(
        f"""with latest as (
              select portfolio_id, run_type, cash, date,
                     row_number() over (partition by portfolio_id, run_type order by date desc) rn
              from {M}.portfolio_nav_daily)
            select m.name, l.run_type, l.cash,
                   m.initial_capital
                   + coalesce(sum(case when t.side = 'sell' then t.value - coalesce(t.cost, 0)
                                       else -(t.value + coalesce(t.cost, 0)) end), 0) expected
            from latest l
            join {M}.portfolio_master m using (portfolio_id)
            left join {M}.portfolio_trades t
              on (t.portfolio_id, t.run_type) = (l.portfolio_id, l.run_type)
             and t.trade_date <= l.date
            where l.rn = 1
            group by 1, 2, 3, m.initial_capital"""
    )
    for r in df.to_dict("records"):
        if abs(Decimal(r["cash"]) - Decimal(r["expected"])) > Decimal("0.05"):
            fail(
                f"F: {r['name']}/{r['run_type']} cash {r['cash']} != capital+flows {r['expected']}"
            )
    bad = _db.read_df(
        f"""select m.name, t.run_type, count(*) n from {M}.portfolio_trades t
            join {M}.portfolio_master m using (portfolio_id)
            where t.side = 'sell' and (t.realized_pnl is null or t.tax is null or t.cost is null)
            group by 1, 2"""
    )
    for r in bad.to_dict("records"):
        fail(
            f"F: {r['name']}/{r['run_type']} has {r['n']} sell(s) missing cost/realized/tax ledger"
        )


def main() -> None:
    n = _db.scalar(f"select count(*) from {M}.portfolio_master where status = 'active'")
    print(f"[validate-portfolios] active portfolios: {n}", flush=True)
    if not n:
        print("[validate-portfolios] nothing to validate — PASS", flush=True)
        return
    for chk in (
        check_a_marked_at_eod,
        check_b_nav_reconciles,
        check_c_trade_prices,
        check_d_cash_never_negative,
        check_e_position_cap,
        check_f_cost_cash_identity_and_ledger,
    ):
        print(f"[validate-portfolios] {chk.__name__}", flush=True)
        chk()
    if FAILURES:
        print(f"[validate-portfolios] {len(FAILURES)} FAILURE(S)", flush=True)
        sys.exit(1)
    print("[validate-portfolios] ALL CHECKS PASS", flush=True)


if __name__ == "__main__":
    main()
