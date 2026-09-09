#!/usr/bin/env python3
"""Basket correctness gate — asserts on REAL produced output (rule #0), independently of the
marker: every check below is its own SQL over ``basket_*`` and ``ohlcv_daily``, never a call
into ``mark_baskets``. India's ``validate_portfolios.py`` checks A–G, over the M2 tables.

    python scripts/global_market/validate_baskets.py [--eod YYYY-MM-DD]   # exit 1 on any failure

Checks, per active basket (live run):
  A. every basket that has been marked has a NAV row at the anchor session (the latest SPY
     session on or before the EOD); a basket with no NAV row yet is REPORTED, not failed —
     the worker books it within minutes, and check G still holds its constituents to account
  B. the latest NAV reconciles: cash + Σ(qty × fill price × close_tr[latest] / close_tr[entry])
     == nav, within a cent per position; n_positions matches the trades
  C. every trade is priced at the stored close on its date — close_adj, or close_tr where the
     row carries no close_adj (the archive)
  D. cash never negative on any NAV row
  E. every buy respects the position cap: an inception buy against initial capital, any other
     buy against that day's NAV (basket_max_position_pct, × 1.001 for cent rounding)
  F. the cash identity: latest cash == initial capital + every signed flow (buy −(value+cost),
     sell +(value−cost))
  G. the current version's weights sum to 1, each within [basket_min_weight_frac,
     basket_max_position_pct], and — once booked — each inception fill is sized to its weight of
     capital (value ≤ target, short of it by at most the 6-dp quantum of one share plus the
     cost reserve)

Every threshold comes from ``atlas_global.atlas_thresholds``; a missing key fails the gate.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # _gdb, basket_data
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the atlas package
import _gdb
import basket_data as data

from atlas.global_market import calendar as gcal

M = _gdb.M
RUN_TYPE = data.RUN_TYPE
CENT = Decimal("0.01")
QUANTUM = Decimal("0.000001")  # basket_trades.qty numeric(18,6)
# One cent per position of rounding in the NAV identity (India's check B tolerance).
NAV_TOL_PER_POSITION = CENT
# Cash identity slack over a long trade history (India's check F).
CASH_TOL = Decimal("0.05")
# A buy may exceed the cap by the cent-rounding of its value (India's check E: × 1.001).
CAP_SLACK = Decimal("1.001")

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL: {msg}", flush=True)


def anchor_session(eod: dt.date) -> dt.date | None:
    df = _gdb.read_df(
        f"""SELECT DISTINCT o.date FROM {M}.ohlcv_daily o
            JOIN {M}.instrument_master im ON im.instrument_id = o.instrument_id
            WHERE im.symbol = :anchor AND im.is_active AND o.date <= :eod ORDER BY o.date""",
        {"anchor": gcal.CONFIG.calendar_anchor, "eod": eod},
    )
    return gcal.latest_session_on_or_before(gcal.sessions(df["date"]), eod)


def check_a_marked_at_anchor(anchor: dt.date) -> None:
    df = _gdb.read_df(
        f"""SELECT m.name, max(n.date) AS last
            FROM {M}.basket_master m
            LEFT JOIN {M}.basket_nav_daily n
              ON n.basket_id = m.basket_id AND n.run_type = :r
            WHERE m.status = 'active' GROUP BY m.basket_id, m.name ORDER BY m.name""",
        {"r": RUN_TYPE},
    )
    for r in df.to_dict("records"):
        if r["last"] is None:
            print(f"  note: {r['name']} has no NAV row yet (the worker books new baskets)")
        elif r["last"] < anchor:
            fail(f"A: {r['name']} live NAV stale — last={r['last']}, anchor session {anchor}")


# The latest NAV row of each basket and, per still-held instrument, the fill re-marked the way
# the marker marks it: fill × close_tr[latest bar ≤ NAV date] / close_tr[entry], close_adj
# standing in where close_tr is NULL at either end. Inception-only books (one buy per name).
_RECON_SQL = f"""
WITH latest AS (
    SELECT basket_id, max(date) AS date FROM {M}.basket_nav_daily
    WHERE run_type = :r GROUP BY basket_id
),
pos AS (
    SELECT t.basket_id, t.instrument_id, t.symbol, l.date,
           sum(CASE WHEN t.side = 'buy' THEN t.qty ELSE -t.qty END) AS qty,
           max(t.trade_date) FILTER (WHERE t.side = 'buy') AS entry
    FROM {M}.basket_trades t
    JOIN latest l USING (basket_id)
    WHERE t.run_type = :r AND t.trade_date <= l.date
    GROUP BY 1, 2, 3, 4
    HAVING sum(CASE WHEN t.side = 'buy' THEN t.qty ELSE -t.qty END) <> 0
),
valued AS (
    SELECT p.basket_id, p.date,
           count(*) AS n_pos,
           sum(p.qty * e.price
               * CASE WHEN e.close_tr IS NOT NULL AND x.close_tr IS NOT NULL
                      THEN x.close_tr / e.close_tr ELSE x.close_adj / e.close_adj END) AS invested
    FROM pos p
    JOIN LATERAL (
        SELECT t.price, o.close_tr, o.close_adj
        FROM {M}.basket_trades t
        JOIN {M}.ohlcv_daily o ON o.instrument_id = t.instrument_id AND o.date = t.trade_date
        WHERE t.basket_id = p.basket_id AND t.run_type = :r AND t.instrument_id = p.instrument_id
          AND t.side = 'buy' AND t.trade_date = p.entry
        ORDER BY t.trade_id DESC LIMIT 1) e ON true
    JOIN LATERAL (
        SELECT o.close_tr, o.close_adj FROM {M}.ohlcv_daily o
        WHERE o.instrument_id = p.instrument_id AND o.date <= p.date
          AND (o.close_tr IS NOT NULL OR o.close_adj IS NOT NULL)
        ORDER BY o.date DESC LIMIT 1) x ON true
    GROUP BY 1, 2
)
SELECT m.name, n.date, n.nav, n.cash, n.invested AS stored_invested, n.n_positions,
       coalesce(v.invested, 0) AS calc_invested, coalesce(v.n_pos, 0) AS calc_pos
FROM {M}.basket_nav_daily n
JOIN latest l ON (l.basket_id, l.date) = (n.basket_id, n.date)
LEFT JOIN valued v ON (v.basket_id, v.date) = (n.basket_id, n.date)
JOIN {M}.basket_master m ON m.basket_id = n.basket_id
WHERE n.run_type = :r AND m.status = 'active'
"""


def check_b_nav_reconciles() -> None:
    df = _gdb.read_df(_RECON_SQL, {"r": RUN_TYPE}, coerce_float=False)
    for r in df.to_dict("records"):
        tol = NAV_TOL_PER_POSITION * (int(r["calc_pos"]) + 1)
        nav, cash = Decimal(str(r["nav"])), Decimal(str(r["cash"]))
        calc = Decimal(str(r["calc_invested"]))
        if abs(nav - (cash + calc)) > tol:
            fail(
                f"B: {r['name']} nav {nav} != cash {cash} + recomputed invested "
                f"{calc.quantize(CENT)} on {r['date']}"
            )
        if int(r["calc_pos"]) != int(r["n_positions"]):
            fail(f"B: {r['name']} n_positions {r['n_positions']} != derived {r['calc_pos']}")


def check_c_trade_prices() -> None:
    df = _gdb.read_df(
        f"""SELECT m.name, t.symbol, t.trade_date, t.price,
                   o.close_adj, o.close_tr, coalesce(o.close_adj, o.close_tr) AS stored
            FROM {M}.basket_trades t
            JOIN {M}.basket_master m USING (basket_id)
            LEFT JOIN {M}.ohlcv_daily o
              ON o.instrument_id = t.instrument_id AND o.date = t.trade_date
            WHERE t.run_type = :r AND m.status = 'active'
              AND coalesce(o.close_adj, o.close_tr) IS DISTINCT FROM t.price""",
        {"r": RUN_TYPE},
        coerce_float=False,
    )
    for r in df.to_dict("records"):
        fail(
            f"C: {r['name']} {r['symbol']} @ {r['trade_date']} traded {r['price']} != stored "
            f"{r['stored']} (close_adj {r['close_adj']}, close_tr {r['close_tr']})"
        )


def check_d_cash_never_negative() -> None:
    df = _gdb.read_df(
        f"""SELECT m.name, min(n.cash) AS worst
            FROM {M}.basket_nav_daily n JOIN {M}.basket_master m USING (basket_id)
            WHERE n.run_type = :r AND m.status = 'active'
            GROUP BY m.name HAVING min(n.cash) < 0""",
        {"r": RUN_TYPE},
        coerce_float=False,
    )
    for r in df.to_dict("records"):
        fail(f"D: {r['name']} cash went negative ({r['worst']})")


def check_e_position_cap(cap: Decimal) -> None:
    df = _gdb.read_df(
        f"""SELECT m.name, t.symbol, t.trade_date, t.reason, t.value,
                   CASE WHEN t.reason = 'inception' THEN m.initial_capital ELSE n.nav END AS base
            FROM {M}.basket_trades t
            JOIN {M}.basket_master m USING (basket_id)
            LEFT JOIN {M}.basket_nav_daily n
              ON (n.basket_id, n.run_type, n.date) = (t.basket_id, t.run_type, t.trade_date)
            WHERE t.run_type = :r AND m.status = 'active' AND t.side = 'buy'""",
        {"r": RUN_TYPE},
        coerce_float=False,
    )
    for r in df.to_dict("records"):
        if r["base"] is None:
            fail(
                f"E: {r['name']} buy {r['symbol']} on {r['trade_date']} has no NAV row to cap against"
            )
            continue
        limit = Decimal(str(r["base"])) * cap * CAP_SLACK
        if Decimal(str(r["value"])) > limit:
            fail(
                f"E: {r['name']} buy {r['symbol']} {r['value']} on {r['trade_date']} exceeds cap "
                f"{cap} of {r['base']}"
            )


def check_f_cash_identity() -> None:
    df = _gdb.read_df(
        f"""WITH latest AS (
              SELECT basket_id, cash, date,
                     row_number() OVER (PARTITION BY basket_id ORDER BY date DESC) AS rn
              FROM {M}.basket_nav_daily WHERE run_type = :r)
            SELECT m.name, l.cash,
                   m.initial_capital
                   + coalesce(sum(CASE WHEN t.side = 'sell' THEN t.value - coalesce(t.cost, 0)
                                       ELSE -(t.value + coalesce(t.cost, 0)) END), 0) AS expected
            FROM latest l
            JOIN {M}.basket_master m USING (basket_id)
            LEFT JOIN {M}.basket_trades t
              ON t.basket_id = l.basket_id AND t.run_type = :r AND t.trade_date <= l.date
            WHERE l.rn = 1 AND m.status = 'active'
            GROUP BY m.name, l.cash, m.initial_capital""",
        {"r": RUN_TYPE},
        coerce_float=False,
    )
    for r in df.to_dict("records"):
        if abs(Decimal(str(r["cash"])) - Decimal(str(r["expected"]))) > CASH_TOL:
            fail(f"F: {r['name']} cash {r['cash']} != capital+flows {r['expected']}")


def check_g_weights_and_sizing(th: dict[str, Decimal]) -> None:
    cap, floor = th["basket_max_position_pct"], th["basket_min_weight_frac"]
    buy_rate = th["basket_cost_bps_buy"] / Decimal(10000)
    baskets = data.active_baskets()
    for b in baskets.to_dict("records"):
        name = b["name"]
        cons = data.constituents(b["basket_id"], int(b["current_version"]))
        if cons.empty:
            fail(f"G: {name} has no constituents for version {b['current_version']}")
            continue
        total = sum((Decimal(str(w)) for w in cons["target_weight_frac"]), Decimal(0))
        if total != 1:
            fail(f"G: {name} weights sum to {total}, not 1")
        for r in cons.to_dict("records"):
            w = Decimal(str(r["target_weight_frac"]))
            if w > cap or w < floor:
                fail(f"G: {name} {r['symbol']} weight {w} outside [{floor}, {cap}]")
        tr = data.trades(b["basket_id"])
        if tr.empty or b["initial_capital"] is None:
            continue
        capital = Decimal(str(b["initial_capital"]))
        booked = {
            r["instrument_id"]: r for r in tr.loc[tr["reason"] == "inception"].to_dict("records")
        }
        for r in cons.to_dict("records"):
            row = booked.get(r["instrument_id"])
            if row is None:
                fail(f"G: {name} constituent {r['symbol']} was never booked at inception")
                continue
            target = Decimal(str(r["target_weight_frac"])) * capital
            value, price = Decimal(str(row["value"])), Decimal(str(row["price"]))
            # value ≤ target; short of it by at most one 6-dp share, the cost reserve and a cent
            slack = price * QUANTUM + target * buy_rate + CENT
            if value > target + CENT or target - value > slack:
                fail(
                    f"G: {name} {r['symbol']} booked {value} != target weight {target.quantize(CENT)} "
                    f"(one share = {price})"
                )


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert the basket books reconcile to real rows")
    ap.add_argument("--eod", type=dt.date.fromisoformat, default=None)
    args = ap.parse_args()
    eod = args.eod or _gdb.eod_cutoff()
    n = _gdb.scalar(f"SELECT count(*) FROM {M}.basket_master WHERE status = 'active'")
    print(f"[validate-baskets] EOD={eod} active baskets: {n}", flush=True)
    if not n:
        print("[validate-baskets] nothing to validate — PASS", flush=True)
        return 0
    th = data.thresholds()
    anchor = anchor_session(eod)
    if anchor is None:
        print(f"[validate-baskets] FAIL — no SPY session on or before {eod}", flush=True)
        return 1
    checks = (
        ("check_a_marked_at_anchor", lambda: check_a_marked_at_anchor(anchor)),
        ("check_b_nav_reconciles", check_b_nav_reconciles),
        ("check_c_trade_prices", check_c_trade_prices),
        ("check_d_cash_never_negative", check_d_cash_never_negative),
        ("check_e_position_cap", lambda: check_e_position_cap(th["basket_max_position_pct"])),
        ("check_f_cash_identity", check_f_cash_identity),
        ("check_g_weights_and_sizing", lambda: check_g_weights_and_sizing(th)),
    )
    for label, chk in checks:
        print(f"[validate-baskets] {label}", flush=True)
        chk()
    if FAILURES:
        print(f"[validate-baskets] {len(FAILURES)} FAILURE(S)", flush=True)
        return 1
    print("[validate-baskets] ALL CHECKS PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
