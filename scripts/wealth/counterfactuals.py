"""Per-client counterfactuals: what-if ₹ deltas for the RM call-sheet.

Four scenarios per client (wide row in wealth.counterfactuals):
  cf_index_rs      — all external flows into the Nifty-50 index fund instead:
                     bench terminal − actual terminal (from exact_benchmark).
  cf_no_panic_rs   — drawdown-window external sells held instead of sold:
                     value today of the sold units minus the cash received
                     (cash assumed idle — stated caveat, upper bound).
  cf_sip_alive_rs  — stopped SIP streams continued at the same monthly amount
                     from stop month to ledger end into the same scheme:
                     value today − contributions (the foregone gain only).
  cf_no_switch_rs  — every paired switch stayed in the source fund:
                     amount × (from-fund return − to-fund return) to today.

Honesty rails: all four are historical replays of NAV series that actually
happened — no forward-return claims. Panic/SIP scenarios are upper bounds and
labelled so on the dashboard.

Usage: .venv/bin/python scripts/wealth/counterfactuals.py
"""

from __future__ import annotations

import sys

import pandas as pd
from engine_common import BENCH_ID, connect, nav_series
from psycopg2.extras import execute_values


def main() -> int:
    conn = connect()
    navs = pd.read_sql(
        """select mstar_id, nav_date, nav::float nav from atlas_foundation.de_mf_nav_daily
           where (mstar_id in (select distinct mstar_id from wealth.schemes
                               where mstar_id is not null) or mstar_id = %s) and nav > 0""",
        conn,
        params=(BENCH_ID,),
    )
    navs["nav_date"] = pd.to_datetime(navs.nav_date)
    nav_by = {
        mid: g.sort_values("nav_date").drop_duplicates("nav_date", keep="last").set_index("nav_date").nav
        for mid, g in navs.groupby("mstar_id")
    }

    def nav_at(mid, d):
        s = nav_by.get(mid)
        if s is None:
            return None
        i = s.index.searchsorted(pd.Timestamp(d), side="right") - 1
        return float(s.iloc[i]) if i >= 0 else None

    def nav_last(mid):
        s = nav_by.get(mid)
        return (s.index[-1], float(s.iloc[-1])) if s is not None else (None, None)

    # ---- scenario 1: index-everything (already computed exactly) ----
    bench_df = pd.read_sql(
        """select client_id, terminal_mv::float tmv, bench_terminal::float btv
           from wealth.client_benchmark""",
        conn,
    ).set_index("client_id")

    # ---- scenario 2: no panic sells ----
    from behaviour_fingerprints import drawdown_windows  # same window definition

    bench = nav_series(conn, BENCH_ID)
    windows = drawdown_windows(bench)

    sells = pd.read_sql(
        """select t.client_id, t.txn_date, t.amount::float amount, t.units::float units,
                  s.mstar_id
           from wealth.transactions t
           join wealth.schemes s using (scheme_id)
           where t.txn_type in ('redemption', 'swp') and t.txn_date is not null
             and t.units > 0 and t.amount > 0 and s.mstar_id is not null""",
        conn,
    )
    sells["txn_date"] = pd.to_datetime(sells.txn_date)
    sells["in_dd"] = sells.txn_date.map(lambda d: any(a <= d <= b for a, b in windows))
    panic = sells[sells.in_dd].copy()
    panic["nav_now"] = panic.mstar_id.map(lambda m: nav_last(m)[1])
    panic["nav_then"] = [nav_at(m, d) for m, d in zip(panic.mstar_id, panic.txn_date)]
    panic = panic.dropna(subset=["nav_now", "nav_then"])
    panic["cf"] = panic.units * panic.nav_now - panic.amount
    cf_panic = panic.groupby("client_id").agg(cf_no_panic_rs=("cf", "sum"),
                                              panic_sells=("cf", "size"))

    # ---- scenario 3: stopped SIPs continued ----
    sips = pd.read_sql(
        """select t.client_id, t.scheme_id, t.fund_name, t.folio, t.txn_date,
                  t.amount::float amount, s.mstar_id
           from wealth.transactions t
           join wealth.schemes s using (scheme_id)
           where t.txn_type = 'sip' and t.txn_date is not null and t.amount > 0
             and s.mstar_id is not null""",
        conn,
    )
    sips["txn_date"] = pd.to_datetime(sips.txn_date)
    ledger_end = pd.read_sql("select max(txn_date) d from wealth.transactions", conn).d.iloc[0]
    ledger_end = pd.Timestamp(ledger_end)
    sip_rows = []
    for (cid, sid, fn, fo), g in sips.groupby(["client_id", "scheme_id", "fund_name", "folio"]):
        months = g.txn_date.dt.to_period("M").drop_duplicates()
        if len(months) < 3:
            continue
        last = g.txn_date.max()
        if (ledger_end - last).days <= 45:
            continue  # still active
        mid = g.mstar_id.iloc[0]
        _, nnow = nav_last(mid)
        if not nnow:
            continue
        monthly = float(g.amount.tail(6).median())
        extra_val = extra_cash = 0.0
        d = last + pd.Timedelta(days=30)
        while d <= ledger_end:
            px = nav_at(mid, d)
            if px:
                extra_val += monthly / px * nnow
                extra_cash += monthly
            d += pd.Timedelta(days=30)
        if extra_cash > 0:
            sip_rows.append((cid, extra_val - extra_cash, extra_cash, monthly))
    cf_sip = (
        pd.DataFrame(sip_rows, columns=["client_id", "cf", "cash", "monthly"])
        .groupby("client_id")
        .agg(cf_sip_alive_rs=("cf", "sum"), sip_cash=("cash", "sum"), sip_streams=("cf", "size"))
        if sip_rows
        else pd.DataFrame(columns=["cf_sip_alive_rs", "sip_cash", "sip_streams"])
    )

    # ---- scenario 4: no switches ----
    adv = pd.read_sql(
        """select client_id, switch_date, amount::float amount, from_scheme_id, to_scheme_id
           from wealth.advice_ledger""",
        conn,
    )
    scheme_mid = pd.read_sql(
        "select scheme_id, mstar_id from wealth.schemes where mstar_id is not null", conn
    ).set_index("scheme_id").mstar_id
    sw_rows = []
    for r in adv.itertuples():
        mfrom = scheme_mid.get(r.from_scheme_id)
        mto = scheme_mid.get(r.to_scheme_id)
        if not (mfrom and mto):
            continue
        f0, fT = nav_at(mfrom, r.switch_date), nav_last(mfrom)[1]
        t0, tT = nav_at(mto, r.switch_date), nav_last(mto)[1]
        if not (f0 and fT and t0 and tT):
            continue
        sw_rows.append((r.client_id, r.amount * (fT / f0 - tT / t0)))
    cf_sw = (
        pd.DataFrame(sw_rows, columns=["client_id", "cf"])
        .groupby("client_id")
        .agg(cf_no_switch_rs=("cf", "sum"), switches=("cf", "size"))
        if sw_rows
        else pd.DataFrame(columns=["cf_no_switch_rs", "switches"])
    )

    out = bench_df.copy()
    out["cf_index_rs"] = out.btv - out.tmv
    out = (
        out[["cf_index_rs"]]
        .join(cf_panic, how="outer")
        .join(cf_sip, how="outer")
        .join(cf_sw, how="outer")
        .fillna(0)
    )

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.counterfactuals")
    cur.execute(
        """create table wealth.counterfactuals (
             client_id bigint primary key references wealth.clients(client_id),
             cf_index_rs numeric(18,0), cf_no_panic_rs numeric(18,0), panic_sells int,
             cf_sip_alive_rs numeric(18,0), sip_cash numeric(18,0), sip_streams int,
             cf_no_switch_rs numeric(18,0), switches int
           )"""
    )
    execute_values(
        cur,
        """insert into wealth.counterfactuals
           (client_id, cf_index_rs, cf_no_panic_rs, panic_sells, cf_sip_alive_rs,
            sip_cash, sip_streams, cf_no_switch_rs, switches) values %s""",
        [
            (
                int(cid), round(r.cf_index_rs), round(r.cf_no_panic_rs),
                int(r.get("panic_sells", 0)), round(r.cf_sip_alive_rs),
                round(r.get("sip_cash", 0)), int(r.get("sip_streams", 0)),
                round(r.cf_no_switch_rs), int(r.get("switches", 0)),
            )
            for cid, r in out.iterrows()
        ],
        page_size=500,
    )
    cur.execute("revoke all on wealth.counterfactuals from anon, authenticated")
    conn.commit()

    print(f"counterfactuals for {len(out)} clients")
    for col in ("cf_index_rs", "cf_no_panic_rs", "cf_sip_alive_rs", "cf_no_switch_rs"):
        s = out[col]
        print(
            f"  {col}: cohort ₹{s.sum() / 1e7:+.1f} cr · median ₹{s.median() / 1e5:+.2f}L · "
            f"positive for {(s > 0).sum()}/{len(s)}"
        )
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
