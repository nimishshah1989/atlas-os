"""Advice ledger (INTERNAL ONLY): every advised switch, scored 1y/3y later.

A switch event = client's switch_out of scheme A paired with switch_in to
scheme B within ±5 calendar days for a comparable amount (±5% or ±₹500).
For each event, forward scheme returns from the switch date answer "did the
advice add value?":
  fwd_1y/3y_a vs fwd_1y/3y_b → advice_alpha = retB − retA (annualised for 3y),
  rupee impact = amount × (retB − retA).
Advisor attribution via wealth.client_profile_ext (ledger header advisor).

Push waves: ≥5 distinct clients entering the same scheme (switch_in or
purchase ≥ ₹25k) inside a rolling 30-day window = one wave — the signature of
a house push. Waves get their own table with forward returns vs the Nifty
index fund from the wave's median entry date.

Writes wealth.advice_ledger + wealth.advice_waves. Nothing here is client-facing.

Usage: .venv/bin/python scripts/wealth/advice_ledger.py
"""

from __future__ import annotations

import sys

import pandas as pd
from engine_common import BENCH_ID, connect
from psycopg2.extras import execute_values


def main() -> int:
    conn = connect()
    tx = pd.read_sql(
        """select t.client_id, t.scheme_id, t.txn_date, t.txn_type, t.amount::float amount,
                  s.mstar_id, s.display_name
           from wealth.transactions t
           left join wealth.schemes s using (scheme_id)
           where t.txn_date is not null
             and t.txn_type in ('switch_out', 'switch_in', 'purchase') and t.amount > 0""",
        conn,
    )
    tx["txn_date"] = pd.to_datetime(tx.txn_date)
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
        i = s.index.searchsorted(d, side="right") - 1
        return float(s.iloc[i]) if i >= 0 else None

    def fwd_ret(mid, d, days):
        a = nav_at(mid, d)
        b = nav_at(mid, d + pd.Timedelta(days=days))
        s = nav_by.get(mid)
        if not (a and b and s is not None) or (s.index[-1] - d).days < days - 10:
            return None
        r = round((b / a - 1) * 100, 2)
        # paise-NAV side pockets / identity glitches produce impossible returns
        return r if -95 <= r <= 1000 else None

    profile = pd.read_sql(
        "select client_id, advisor_name, advisor_code, branch from wealth.client_profile_ext",
        conn,
    ).set_index("client_id")

    # ---- pair switches per client ----
    events = []
    for cid, g in tx[tx.txn_type.isin(["switch_out", "switch_in"])].groupby("client_id"):
        outs = g[g.txn_type == "switch_out"].sort_values("txn_date").to_dict("records")
        ins_ = g[g.txn_type == "switch_in"].sort_values("txn_date").to_dict("records")
        used = set()
        for o in outs:
            best = None
            for j, i_ in enumerate(ins_):
                if j in used or i_["scheme_id"] == o["scheme_id"]:
                    continue
                dd = abs((i_["txn_date"] - o["txn_date"]).days)
                if dd > 5:
                    continue
                da = abs(i_["amount"] - o["amount"]) / max(o["amount"], 1)
                if da <= 0.05 or abs(i_["amount"] - o["amount"]) <= 500:
                    score = dd + da
                    if best is None or score < best[0]:
                        best = (score, j)
            if best is not None:
                used.add(best[1])
                i_ = ins_[best[1]]
                d = o["txn_date"]
                adv = profile.loc[cid] if cid in profile.index else None
                r1a, r1b = fwd_ret(o["mstar_id"], d, 365), fwd_ret(i_["mstar_id"], d, 365)
                r3a, r3b = fwd_ret(o["mstar_id"], d, 1095), fwd_ret(i_["mstar_id"], d, 1095)
                sid_o = int(o["scheme_id"]) if pd.notna(o["scheme_id"]) else None
                sid_i = int(i_["scheme_id"]) if pd.notna(i_["scheme_id"]) else None
                events.append(
                    (
                        int(cid), str(d.date()), float(o["amount"]),
                        sid_o, o["display_name"], sid_i, i_["display_name"],
                        r1a, r1b,
                        round(r1b - r1a, 2) if (r1a is not None and r1b is not None) else None,
                        round((r1b - r1a) * o["amount"] / 100, 0)
                        if (r1a is not None and r1b is not None) else None,
                        r3a, r3b,
                        round(r3b - r3a, 2) if (r3a is not None and r3b is not None) else None,
                        round((r3b - r3a) * o["amount"] / 100, 0)
                        if (r3a is not None and r3b is not None) else None,
                        adv.advisor_name if adv is not None else None,
                        adv.advisor_code if adv is not None else None,
                        adv.branch if adv is not None else None,
                    )
                )

    # ---- push waves ----
    entries = tx[(tx.txn_type == "switch_in") | ((tx.txn_type == "purchase") & (tx.amount >= 25000))]
    waves = []
    for sid, g in entries.dropna(subset=["scheme_id"]).groupby("scheme_id"):
        g = g.sort_values("txn_date")
        dates = g.txn_date.to_numpy()
        cids = g.client_id.to_numpy()
        amts = g.amount.to_numpy()
        i = 0
        while i < len(g):
            lo = dates[i]
            hi = lo + pd.Timedelta(days=30)
            in_win = (dates >= lo) & (dates <= hi)
            ucids = set(cids[in_win])
            if len(ucids) >= 5:
                med = pd.Series(dates[in_win]).median()
                mid = g.mstar_id.iloc[0]
                waves.append(
                    (
                        int(sid), g.display_name.iloc[0], str(pd.Timestamp(lo).date()),
                        str(pd.Timestamp(hi).date()), len(ucids), float(amts[in_win].sum()),
                        fwd_ret(mid, pd.Timestamp(med), 365), fwd_ret(BENCH_ID, pd.Timestamp(med), 365),
                        fwd_ret(mid, pd.Timestamp(med), 1095), fwd_ret(BENCH_ID, pd.Timestamp(med), 1095),
                    )
                )
                i += int(in_win.sum())  # jump past this wave
            else:
                i += 1

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.advice_ledger")
    cur.execute(
        """create table wealth.advice_ledger (
             advice_id bigint generated always as identity primary key,
             client_id bigint not null references wealth.clients(client_id),
             switch_date date not null, amount numeric(18,2) not null,
             from_scheme_id bigint, from_name text, to_scheme_id bigint, to_name text,
             fwd1y_from numeric(10,2), fwd1y_to numeric(10,2),
             alpha_1y_pp numeric(10,2), alpha_1y_rs numeric(18,0),
             fwd3y_from numeric(10,2), fwd3y_to numeric(10,2),
             alpha_3y_pp numeric(10,2), alpha_3y_rs numeric(18,0),
             advisor_name text, advisor_code text, branch text
           )"""
    )
    execute_values(
        cur,
        """insert into wealth.advice_ledger
           (client_id, switch_date, amount, from_scheme_id, from_name, to_scheme_id, to_name,
            fwd1y_from, fwd1y_to, alpha_1y_pp, alpha_1y_rs, fwd3y_from, fwd3y_to,
            alpha_3y_pp, alpha_3y_rs, advisor_name, advisor_code, branch) values %s""",
        events,
        page_size=500,
    )
    cur.execute("drop table if exists wealth.advice_waves")
    cur.execute(
        """create table wealth.advice_waves (
             wave_id bigint generated always as identity primary key,
             scheme_id bigint not null, scheme_name text,
             window_start date, window_end date,
             n_clients int not null, inflow_rs numeric(18,2),
             fwd1y_scheme numeric(10,2), fwd1y_bench numeric(10,2),
             fwd3y_scheme numeric(10,2), fwd3y_bench numeric(10,2)
           )"""
    )
    execute_values(
        cur,
        """insert into wealth.advice_waves
           (scheme_id, scheme_name, window_start, window_end, n_clients, inflow_rs,
            fwd1y_scheme, fwd1y_bench, fwd3y_scheme, fwd3y_bench) values %s""",
        waves,
        page_size=500,
    )
    cur.execute("revoke all on wealth.advice_ledger from anon, authenticated")
    cur.execute("revoke all on wealth.advice_waves from anon, authenticated")
    conn.commit()

    df = pd.DataFrame(
        events,
        columns=["cid", "d", "amt", "fs", "fn", "ts", "tn", "r1a", "r1b", "a1", "a1rs",
                 "r3a", "r3b", "a3", "a3rs", "an", "ac", "br"],
    )
    print(f"advice events: {len(df)} paired switches, ₹{df.amt.sum() / 1e7:.1f} cr moved")
    s1 = df.dropna(subset=["a1"])
    s3 = df.dropna(subset=["a3"])
    if len(s1):
        print(
            f"1y scoreboard: {len(s1)} scored, median alpha {s1.a1.median():+.2f}pp, "
            f"good calls {(s1.a1 > 0).mean():.0%}, net ₹{s1.a1rs.sum() / 1e5:+.1f}L"
        )
    if len(s3):
        print(
            f"3y scoreboard: {len(s3)} scored, median alpha {s3.a3.median():+.2f}pp, "
            f"good calls {(s3.a3 > 0).mean():.0%}, net ₹{s3.a3rs.sum() / 1e5:+.1f}L"
        )
    print(f"push waves detected: {len(waves)}")
    for w in sorted(waves, key=lambda w: -w[5])[:8]:
        print(f"  {w[1][:45]}: {w[4]} clients ₹{w[5] / 1e5:.1f}L in {w[2]}..{w[3]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
