"""Behaviour gap: money-weighted (investor) vs time-weighted (fund) return.

Morningstar "Mind the Gap" methodology at client×scheme granularity over the
client's own holding window, using scheme NAV series for both sides:
  investor return (MWR): XIRR of the client's unit-flow values in the scheme —
    every unit-moving txn valued at NAV (buys negative, sells positive), terminal
    = final units × latest NAV. Dividends taken in cash are outflows.
  fund return (TWR): CAGR of the scheme NAV over the same first-txn → last-NAV
    window (time-weighted by construction — no flows).
  gap_pp = mwr − twr; gap_rs ≈ gap_pp × average invested capital × years held
    (the ₹ the client's timing cost them vs buy-and-hold of the same fund).

Hayley (2014) caveat encoded in the output: part of any MWR−TWR gap is
mechanical (a falling NAV after any inflow drags MWR below TWR regardless of
skill); we report the decomposition inputs, not a verdict.

Writes wealth.behaviour_gap (client × scheme) + per-client rollup into the
cohort summary printout. Uses unit-flows × NAV (not cash amounts) so switches,
mergers and transfers are handled identically to purchases at the same date.

Usage: .venv/bin/python scripts/wealth/behaviour_gap.py
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from engine_common import connect, xirr
from psycopg2.extras import execute_values


def main() -> int:
    conn = connect()
    txns = pd.read_sql(
        """select t.client_id, t.scheme_id, t.txn_date, t.txn_type, t.is_debit,
                  t.units::float units, t.amount::float amount, t.nav::float nav,
                  t.balance_units::float bal, s.mstar_id
           from wealth.transactions t
           join wealth.schemes s using (scheme_id)
           where s.mstar_id is not null and t.txn_date is not null
           order by t.client_id, t.scheme_id, t.txn_date, t.txn_id""",
        conn,
    )
    txns["txn_date"] = pd.to_datetime(txns.txn_date)
    navs = pd.read_sql(
        """select mstar_id, nav_date, nav::float nav from atlas_foundation.de_mf_nav_daily
           where mstar_id in (select distinct mstar_id from wealth.schemes
                              where mstar_id is not null) and nav > 0""",
        conn,
    )
    navs["nav_date"] = pd.to_datetime(navs.nav_date)
    nav_by_scheme = {
        mid: g.sort_values("nav_date").drop_duplicates("nav_date", keep="last").set_index("nav_date").nav
        for mid, g in navs.groupby("mstar_id")
    }

    rows = []
    for (cid, sid), g in txns.groupby(["client_id", "scheme_id"]):
        mid = g.mstar_id.iloc[0]
        s = nav_by_scheme.get(mid)
        if s is None or len(s) < 30:
            continue
        last_date, last_nav = s.index[-1], float(s.iloc[-1])

        def nav_at(d):
            i = s.index.searchsorted(d, side="right") - 1
            return float(s.iloc[i]) if i >= 0 else None

        flows = []
        skipped = False
        for r in g.itertuples():
            if not r.units or r.units == 0:
                if r.txn_type == "div_payout" and r.amount:
                    flows.append((r.txn_date.date(), r.amount))  # cash taken out
                continue
            px = nav_at(r.txn_date) or r.nav
            if px is None:
                skipped = True
                continue
            val = r.units * px
            flows.append((r.txn_date.date(), val if r.is_debit else -val))
        final_units = g.bal.iloc[-1] if pd.notna(g.bal.iloc[-1]) else 0.0
        if final_units and final_units > 0:
            flows.append((last_date.date(), final_units * last_nav))
        if len(flows) < 2:
            continue
        mwr = xirr(flows)
        # fund TWR over the same window
        d0 = g.txn_date.iloc[0]
        nav0 = nav_at(d0)
        yrs = (last_date - d0).days / 365.25
        if nav0 is None or yrs < 0.5:
            continue
        twr = round(((last_nav / nav0) ** (1 / yrs) - 1) * 100, 2)
        if mwr is None:
            continue
        # average invested capital ≈ time-weighted average of units-held × NAV at flow points
        invested = float(-sum(a for _, a in flows if a < 0))
        gap_pp = round(mwr - twr, 2)
        avg_cap = invested / 2 if invested else 0.0  # ponytail: flat-average proxy, upgrade to daily curve if needed
        gap_rs = round(gap_pp / 100 * avg_cap * min(yrs, 25), 0)
        rows.append(
            (int(cid), int(sid), mid, str(d0.date()), float(yrs), len(flows), invested,
             mwr, twr, gap_pp, avg_cap, gap_rs, skipped)
        )

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.behaviour_gap")
    cur.execute(
        """create table wealth.behaviour_gap (
             client_id bigint not null references wealth.clients(client_id),
             scheme_id bigint not null references wealth.schemes(scheme_id),
             mstar_id text not null,
             first_txn date not null, years numeric(8,2) not null, n_flows int not null,
             invested numeric(18,2), mwr_pct numeric(10,2), twr_pct numeric(10,2),
             gap_pp numeric(10,2), avg_capital numeric(18,2), gap_rs numeric(18,0),
             partial boolean not null,
             primary key (client_id, scheme_id)
           )"""
    )
    execute_values(
        cur,
        """insert into wealth.behaviour_gap
           (client_id, scheme_id, mstar_id, first_txn, years, n_flows, invested,
            mwr_pct, twr_pct, gap_pp, avg_capital, gap_rs, partial) values %s""",
        rows,
        page_size=1000,
    )
    cur.execute("revoke all on wealth.behaviour_gap from anon, authenticated")
    conn.commit()

    df = pd.DataFrame(rows, columns=[
        "cid", "sid", "mid", "d0", "yrs", "n", "inv", "mwr", "twr", "gap", "cap", "gaprs", "part"
    ])
    w = df[df.inv > 0]
    wavg = float(np.average(w.gap, weights=w.inv)) if len(w) else float("nan")
    print(f"client×scheme rows: {len(df)} ({df.cid.nunique()} clients, {df.sid.nunique()} schemes)")
    print(f"median gap {df.gap.median():+.2f}pp · invested-weighted {wavg:+.2f}pp")
    per_client = df.groupby("cid").gaprs.sum()
    print(
        f"₹ gap/yr proxy: cohort {df.gaprs.sum() / df.yrs.mean() / 1e7:.2f} cr total-window; "
        f"worst client ₹{per_client.min() / 1e5:.1f}L, best ₹{per_client.max() / 1e5:.1f}L"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
