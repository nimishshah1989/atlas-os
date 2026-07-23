"""Per-client behaviour fingerprints from the transaction ledger.

One row per client in wealth.client_behaviour:
  disposition (Odean PGR/PLR, dispositionEffect-package methodology on avg-cost
    positions): PGR = gains realized / (gains realized + paper gains),
    PLR likewise for losses, de = PGR − PLR (positive → sells winners, rides losers);
  chase: invested-weighted average trailing-3m return of the scheme at the moment
    of each equity buy ("buys after +X% quarters") + share of buy value placed
    after a >10% trailing quarter;
  panic: outflow value during bench drawdown windows (peak-to-trough-to-recovery
    stretches where the Nifty-50 index fund fell >10%, computed from the NAV
    series, not hardcoded dates) + how much of it was sold below cost;
  SIP persistence: detected SIP streams (≥3 monthly credits per fund-folio),
    still-active vs stopped, stops that happened inside a drawdown window;
  dividend leakage: cash taken as dividend payouts instead of compounding.

Position replay is average-cost (the dispositionEffect package default), fed by
unit-moving txns; pledge/unpledge don't change ownership and are skipped.

Usage: .venv/bin/python scripts/wealth/behaviour_fingerprints.py
"""

from __future__ import annotations

import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from engine_common import BENCH_ID, connect, nav_series
from psycopg2.extras import execute_values

ADD_TYPES = {"purchase", "sip", "switch_in", "div_reinvest", "bonus", "dtp_in",
             "merger_in", "transfer_in", "transmission_in", "opening_balance",
             "segregation", "balance_adjust"}
REMOVE_TYPES = {"redemption", "swp", "switch_out", "dtp_out", "merger_out",
                "transfer_out", "transmission_out", "balance_adjust"}
EXTERNAL_SELL = {"redemption", "swp"}


def drawdown_windows(nav: pd.Series, floor: float = -0.10) -> list[tuple]:
    """(start, trough, recovery) stretches where drawdown from running peak < floor."""
    peak = nav.cummax()
    dd = nav / peak - 1
    out, in_dd, start = [], False, None
    for d, v in dd.items():
        if not in_dd and v < floor:
            in_dd, start = True, d
        elif in_dd and v >= -0.001:  # recovered to peak
            out.append((start, d))
            in_dd = False
    if in_dd:
        out.append((start, dd.index[-1]))
    return out


def main() -> int:
    conn = connect()
    txns = pd.read_sql(
        """select t.client_id, t.scheme_id, t.fund_name, t.folio, t.txn_date, t.txn_type,
                  t.is_debit, t.units::float units, t.amount::float amount, t.nav::float nav,
                  s.mstar_id, s.asset_class
           from wealth.transactions t
           left join wealth.schemes s using (scheme_id)
           where t.txn_date is not null
           order by t.client_id, t.txn_date, t.txn_id""",
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

    def ret_3m(mid, d):
        s = nav_by.get(mid)
        if s is None:
            return None
        now, then = nav_at(mid, d), nav_at(mid, d - pd.Timedelta(days=91))
        return (now / then - 1) if (now and then) else None

    bench = nav_series(conn, BENCH_ID)
    dd_windows = drawdown_windows(bench)
    print(f"bench drawdown(>10%) windows: {[(str(a.date()), str(b.date())) for a, b in dd_windows]}")

    def in_drawdown(d) -> bool:
        return any(a <= d <= b for a, b in dd_windows)

    out_rows = []
    for cid, g in txns.groupby("client_id"):
        pos: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])  # key → [units, cost]
        chase_val = chase_wret = chase_hot = 0.0
        panic_out = panic_loss_out = total_out = 0.0
        div_leak = 0.0
        sell_gain_rs = sell_loss_rs = 0.0
        for r in g.itertuples():
            key = (r.scheme_id, r.fund_name, r.folio)
            units = r.units or 0.0
            mid = r.mstar_id
            # --- chase (equity buys with real cash) ---
            if r.txn_type in ("purchase", "sip", "switch_in") and r.asset_class == "Equity" and r.amount:
                tr = ret_3m(mid, r.txn_date) if mid else None
                if tr is not None:
                    chase_val += r.amount
                    chase_wret += r.amount * tr
                    if tr > 0.10:
                        chase_hot += r.amount
            # --- dividend leakage ---
            if r.txn_type == "div_payout" and r.amount:
                div_leak += r.amount
            # --- position replay + disposition + panic ---
            if r.txn_type in ADD_TYPES and not r.is_debit and units > 0:
                cost = (
                    units * r.nav
                    if r.txn_type == "div_reinvest" and r.nav
                    else (r.amount if r.amount else (units * (nav_at(mid, r.txn_date) or r.nav or 0.0)))
                )
                pos[key][0] += units
                pos[key][1] += cost or 0.0
            elif r.txn_type in REMOVE_TYPES and units > 0:
                u0, c0 = pos[key]
                avg_cost = (c0 / u0) if u0 > 1e-9 else None
                sell_px = (r.amount / units) if r.amount else (r.nav or None)
                take = min(units, u0) if u0 > 0 else 0.0
                pos[key][0] = max(u0 - units, 0.0)
                pos[key][1] = max(c0 - (avg_cost or 0.0) * take, 0.0)
                if r.txn_type in EXTERNAL_SELL and r.amount:
                    total_out += r.amount
                    if in_drawdown(r.txn_date):
                        panic_out += r.amount
                        if avg_cost and sell_px and sell_px < avg_cost:
                            panic_loss_out += r.amount
                if avg_cost and sell_px:
                    if sell_px > avg_cost:
                        sell_gain_rs += (sell_px - avg_cost) * take
                    else:
                        sell_loss_rs += (avg_cost - sell_px) * take
        out_rows.append([int(cid), chase_val, chase_wret, chase_hot, panic_out,
                         panic_loss_out, total_out, div_leak, sell_gain_rs, sell_loss_rs])

    # ---- second pass: exact PGR/PLR with paper gains/losses at each sell date ----
    # rebuild positions per client with a running frame, but evaluate paper signs
    # only at sell dates (vectorized per client over held keys).
    de_rows = {}
    for cid, g in txns.groupby("client_id"):
        pos: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])
        mid_of: dict[tuple, str | None] = {}
        RG = PG = RL = PL = 0
        for r in g.itertuples():
            key = (r.scheme_id, r.fund_name, r.folio)
            mid_of.setdefault(key, r.mstar_id)
            units = r.units or 0.0
            if r.txn_type in ADD_TYPES and not r.is_debit and units > 0:
                cost = (
                    units * r.nav
                    if r.txn_type == "div_reinvest" and r.nav
                    else (r.amount if r.amount else (units * (nav_at(r.mstar_id, r.txn_date) or r.nav or 0.0)))
                )
                pos[key][0] += units
                pos[key][1] += cost or 0.0
            elif r.txn_type in REMOVE_TYPES and units > 0:
                u0, c0 = pos[key]
                avg_cost = (c0 / u0) if u0 > 1e-9 else None
                sell_px = (r.amount / units) if r.amount else (r.nav or None)
                take = min(units, u0) if u0 > 0 else 0.0
                pos[key][0] = max(u0 - units, 0.0)
                pos[key][1] = max(c0 - (avg_cost or 0.0) * take, 0.0)
                if r.txn_type in EXTERNAL_SELL and avg_cost and sell_px:
                    if sell_px > avg_cost:
                        RG += 1
                    else:
                        RL += 1
                    for k2, (u2, c2) in pos.items():
                        if u2 <= 1e-6 or c2 <= 0:
                            continue
                        m2 = mid_of.get(k2)
                        px2 = nav_at(m2, r.txn_date) if m2 else None
                        if px2 is None:
                            continue
                        if px2 * u2 > c2:
                            PG += 1
                        else:
                            PL += 1
        pgr = RG / (RG + PG) if (RG + PG) else None
        plr = RL / (RL + PL) if (RL + PL) else None
        de = round(pgr - plr, 3) if (pgr is not None and plr is not None) else None
        de_rows[cid] = (RG, PG, RL, PL,
                        round(pgr, 3) if pgr is not None else None,
                        round(plr, 3) if plr is not None else None, de)

    # ---- SIP persistence ----
    sips = txns[txns.txn_type == "sip"].copy()
    sip_stats = {}
    ledger_end = txns.txn_date.max()
    for cid, g in sips.groupby("client_id"):
        streams = active = stopped = stop_in_dd = 0
        for _key, sg in g.groupby(["scheme_id", "fund_name", "folio"], dropna=False):
            months = sg.txn_date.dt.to_period("M").drop_duplicates()
            if len(months) < 3:
                continue
            streams += 1
            last = sg.txn_date.max()
            if (ledger_end - last).days <= 45:
                active += 1
            else:
                stopped += 1
                if in_drawdown(last + pd.Timedelta(days=30)):
                    stop_in_dd += 1
        sip_stats[cid] = (streams, active, stopped, stop_in_dd)

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.client_behaviour")
    cur.execute(
        """create table wealth.client_behaviour (
             client_id bigint primary key references wealth.clients(client_id),
             pgr numeric(6,3), plr numeric(6,3), disposition numeric(6,3),
             n_gain_sells int, n_paper_gains int, n_loss_sells int, n_paper_losses int,
             chase_buy_rs numeric(18,2),        -- equity buy value with trailing-3m known
             chase_avg_3m_pct numeric(8,2),     -- invested-weighted trailing-3m at buy
             chase_hot_share numeric(6,3),      -- share bought after >10% quarters
             panic_out_rs numeric(18,2), panic_loss_out_rs numeric(18,2),
             total_out_rs numeric(18,2), panic_share numeric(6,3),
             div_leak_rs numeric(18,2),
             realized_gain_rs numeric(18,2), realized_loss_rs numeric(18,2),
             sip_streams int, sip_active int, sip_stopped int, sip_stops_in_drawdown int
           )"""
    )
    ins = []
    for row in out_rows:
        cid, cval, cwret, chot, pout, plout, tout, dleak, sgain, sloss = row
        rg, pg, rl, pl, pgr, plr, de = de_rows.get(cid, (0, 0, 0, 0, None, None, None))
        st, sa, ss, sd = sip_stats.get(cid, (0, 0, 0, 0))
        ins.append(
            (
                cid, pgr, plr, de, rg, pg, rl, pl,
                round(cval, 2), round(cwret / cval * 100, 2) if cval else None,
                round(chot / cval, 3) if cval else None,
                round(pout, 2), round(plout, 2), round(tout, 2),
                round(pout / tout, 3) if tout else None,
                round(dleak, 2), round(sgain, 2), round(sloss, 2), st, sa, ss, sd,
            )
        )
    execute_values(
        cur,
        """insert into wealth.client_behaviour
           (client_id, pgr, plr, disposition, n_gain_sells, n_paper_gains, n_loss_sells,
            n_paper_losses, chase_buy_rs, chase_avg_3m_pct, chase_hot_share, panic_out_rs,
            panic_loss_out_rs, total_out_rs, panic_share, div_leak_rs, realized_gain_rs,
            realized_loss_rs, sip_streams, sip_active, sip_stopped, sip_stops_in_drawdown)
           values %s""",
        ins,
        page_size=500,
    )
    cur.execute("revoke all on wealth.client_behaviour from anon, authenticated")
    conn.commit()

    df = pd.read_sql("select * from wealth.client_behaviour", conn)
    print(f"{len(df)} clients fingerprinted")
    print(
        f"disposition: median {df.disposition.median():+.3f} "
        f"({(df.disposition > 0.1).sum()} strong winner-sellers of {df.disposition.notna().sum()})"
    )
    print(
        f"chase: median trailing-3m at equity buy {df.chase_avg_3m_pct.median():+.2f}% · "
        f"hot-buy share median {df.chase_hot_share.median():.1%}"
    )
    print(
        f"panic: {int((df.panic_share > 0.25).sum())} clients took >25% of lifetime outflows "
        f"inside drawdowns; ₹{df.panic_loss_out_rs.sum() / 1e7:.1f} cr sold below cost in drawdowns"
    )
    print(f"dividend leakage: ₹{df.div_leak_rs.sum() / 1e7:.1f} cr taken as payouts")
    print(f"SIPs: {int(df.sip_stopped.sum())} stopped ({int(df.sip_stops_in_drawdown.sum())} in drawdowns)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
