"""Exact per-client benchmark: replay true external flows into the Nifty-50 index fund.

Replaces the buy-only approximation in client_analytics.py. Every external cash
flow (purchases + SIPs in, redemptions + SWPs + dividend payouts out — switches
and reinvestments are internal) is replayed into ICICI Pru Nifty 50 Index Reg-G
(F0GBR06R0H, NAV history to 2006) at the flow date's NAV:
  in  → buy bench units;  out → sell bench units of equal value.
Terminal bench value = net units × latest NAV → bench XIRR on the same dated
flows. Client XIRR is computed from the same flows + the ledger's own terminal
market value (sum of per-block MV) — both sides exact, same flow set, honest
apples-to-apples. alpha = client − bench.

Flows before the bench series start (2006) are priced at the first available
NAV and flagged (pre_bench_flows) — same treatment as client_analytics did.
Clients whose book carries opening-balance/transfer-in units are flagged approx
(part of their history has no cash-flow record).

Writes wealth.client_benchmark (one row per client) + prints cohort summary.

Usage: .venv/bin/python scripts/wealth/exact_benchmark.py
"""

from __future__ import annotations

import sys

import pandas as pd
from engine_common import BENCH_ID, NavLookup, connect, external_flows, nav_series, xirr
from psycopg2.extras import execute_values


def main() -> int:
    conn = connect()
    bench = nav_series(conn, BENCH_ID)
    if bench.empty:
        print(f"FATAL no NAV series for {BENCH_ID}")
        return 1
    lookup = NavLookup(bench)
    bench_last_date, bench_last_nav = bench.index[-1].date(), float(bench.iloc[-1])

    flows = external_flows(conn)
    # terminal MV per client = sum of the ledger's own per-block Market Value lines
    # (same dataset and date window as the flows — fully self-consistent)
    mv = pd.read_sql(
        """select client_id, sum(market_value)::float mv_total, max(mv_date) mv_date
           from wealth.ledger_blocks group by 1""",
        conn,
    )
    approx_clients = pd.read_sql(
        """select distinct client_id from wealth.transactions
           where txn_type in ('opening_balance', 'transfer_in') and units > 0""",
        conn,
    ).client_id.to_numpy()

    rows = []
    for cid, grp in flows.groupby("client_id"):
        fl = sorted(zip(grp.txn_date, grp.signed), key=lambda t: t[0])
        gross_in = float(-sum(a for _, a in fl if a < 0))
        gross_out = float(sum(a for _, a in fl if a > 0))
        if gross_in <= 0:
            continue
        m = mv[mv.client_id == cid]
        terminal = float(m.mv_total.iloc[0]) if len(m) and pd.notna(m.mv_total.iloc[0]) else None
        mv_date = m.mv_date.iloc[0] if len(m) and pd.notna(m.mv_date.iloc[0]) else bench_last_date
        # bench replay
        units = 0.0
        pre_bench = 0
        for d, a in fl:
            nav = lookup.at(d)
            if nav is None:
                nav = float(bench.iloc[0])
                pre_bench += 1
            units += (-a) / nav  # in (a<0) buys, out (a>0) sells
        bench_terminal = units * (lookup.at(mv_date) or bench_last_nav)
        bxirr = xirr(fl + [(mv_date, bench_terminal)])
        cxirr = xirr(fl + [(mv_date, terminal)]) if terminal is not None else None
        alpha = round(cxirr - bxirr, 2) if (cxirr is not None and bxirr is not None) else None
        rows.append(
            (
                int(cid), cxirr, bxirr, alpha, len(fl), fl[0][0], fl[-1][0],
                gross_in, gross_out, terminal, round(bench_terminal, 2),
                pre_bench, bool(cid in approx_clients), bench_terminal < 0,
            )
        )

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.client_benchmark")
    cur.execute(
        """create table wealth.client_benchmark (
             client_id bigint primary key references wealth.clients(client_id),
             xirr_client numeric(10,2), xirr_bench numeric(10,2), alpha numeric(10,2),
             n_flows int not null, first_flow date, last_flow date,
             gross_in numeric(18,2), gross_out numeric(18,2),
             terminal_mv numeric(18,2), bench_terminal numeric(18,2),
             pre_bench_flows int not null,
             approx boolean not null,         -- opening/transfer units lack flow history
             bench_overdrawn boolean not null -- withdrawals exceeded bench book
           )"""
    )
    execute_values(
        cur,
        """insert into wealth.client_benchmark
           (client_id, xirr_client, xirr_bench, alpha, n_flows, first_flow, last_flow,
            gross_in, gross_out, terminal_mv, bench_terminal, pre_bench_flows, approx,
            bench_overdrawn) values %s""",
        rows,
    )
    cur.execute("revoke all on wealth.client_benchmark from anon, authenticated")
    conn.commit()

    df = pd.DataFrame(
        rows,
        columns=[
            "cid", "cx", "bx", "alpha", "n", "f0", "f1", "gin", "gout", "tmv", "btv",
            "pre", "approx", "over",
        ],
    )
    ok = df.dropna(subset=["alpha"])
    clean = ok[~ok.approx]
    print(f"clients replayed: {len(df)}, with alpha: {len(ok)}, flow-complete (non-approx): {len(clean)}")
    print(
        f"median client XIRR {ok.cx.median():.2f}% vs bench {ok.bx.median():.2f}% "
        f"→ median alpha {ok.alpha.median():+.2f}pp; beating bench: {(ok.alpha > 0).sum()}/{len(ok)}"
    )
    print(
        f"clean-only: median alpha {clean.alpha.median():+.2f}pp, "
        f"beating: {(clean.alpha > 0).sum()}/{len(clean)}"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
