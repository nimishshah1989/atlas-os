"""Churn & CLV from the transaction ledger — at the levels the data can support.

Honesty first: the loaded ledgers are the CURRENT client book (departed clients'
files were never in the drop), so client-level churn has only a handful of
observable events — no fittable model, and this script refuses to pretend
otherwise. It reports that fact, then models churn where events are plentiful:

  1. SIP-stream survival — every detected SIP stream (≥3 monthly credits per
     fund-folio), duration first→last instalment, censored while active.
     Kaplan-Meier + Cox PH (lifelines) with interpretable covariates:
     equity vs non-equity, started-after-rally (trailing-3m > 10%), monthly
     amount tercile. Hundreds of stop events → real inference.
  2. Holding survival — every fund-folio relationship, first buy → full exit,
     censored while units remain. The book's "relationship half-life".
  3. Per-client early-warning — a transparent disengagement score for ACTIVE
     clients (no black box): stopped-SIP share + months since last inflow +
     12m net-outflow share of book. Ranked call list, factors shown.
  4. CLV proxy in AUM-years — client AUM × expected remaining holding-years
     from the holding-level KM at the client's current mix. Deliberately NOT
     rupees of revenue: no trail-rate assumption is invented here.

Writes wealth.client_churn_risk (one row per active client) +
wealth.churn_curves (KM curves for the dashboard). Runs in the jhaveri venv
(lifelines lives there, never in the prod .venv):

    /home/ubuntu/jhaveri_data/venv/bin/python scripts/wealth/churn_clv.py
"""

# pyright: reportMissingImports=false
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import psycopg2
from lifelines import CoxPHFitter, KaplanMeierFitter
from psycopg2.extras import execute_values

QUIET_MONTHS = 6  # book ~0 and silent this long = departed


def connect():
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    return psycopg2.connect(dsn)


def main() -> int:
    conn = connect()
    txns = pd.read_sql(
        """select t.client_id, t.scheme_id, t.fund_name, t.folio, t.txn_date, t.txn_type,
                  t.is_debit, t.units::float units, t.amount::float amount,
                  s.asset_class, s.mstar_id
           from wealth.transactions t
           left join wealth.schemes s using (scheme_id)
           where t.txn_date is not null
           order by t.client_id, t.txn_date, t.txn_id""",
        conn,
    )
    txns["txn_date"] = pd.to_datetime(txns.txn_date)
    ledger_end = txns.txn_date.max()

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

    def ret_3m(mid, d):
        s = nav_by.get(mid)
        if s is None:
            return None
        i1 = s.index.searchsorted(d, side="right") - 1
        i0 = s.index.searchsorted(d - pd.Timedelta(days=91), side="right") - 1
        if i0 < 0 or i1 < 0:
            return None
        return float(s.iloc[i1] / s.iloc[i0] - 1)

    # ---- 0. client-level survivorship statement (no model — refuse fake precision) ----
    mv = pd.read_sql(
        "select client_id, coalesce(sum(market_value),0)::float mv from wealth.ledger_blocks group by 1",
        conn,
    ).set_index("client_id").mv
    life = txns.groupby("client_id").txn_date.agg(["min", "max"])
    life["mv"] = mv.reindex(life.index).fillna(0)
    life["departed"] = (life.mv < 1000) & (
        life["max"] < ledger_end - pd.Timedelta(days=30 * QUIET_MONTHS)
    )
    n_dep = int(life.departed.sum())
    print(
        f"client-level: {n_dep} observable departures / {len(life)} clients — survivor-only "
        f"book (departed clients' ledgers were never in the drop). No client-level model is "
        f"fit on {n_dep} events; churn is modelled at SIP-stream and holding level below."
    )
    for cid in life[life.departed].index:
        nm = pd.read_sql(
            "select full_name from wealth.clients where client_id=%s", conn, params=(int(cid),)
        ).full_name.iloc[0]
        print(f"  departed: {nm} (last activity {life.loc[cid, 'max'].date()})")

    # ---- 1. SIP-stream survival ----
    sips = txns[txns.txn_type == "sip"]
    streams = []
    for (cid, sid, fn, fo), g in sips.groupby(["client_id", "scheme_id", "fund_name", "folio"], dropna=False):
        months = g.txn_date.dt.to_period("M").nunique()
        if months < 3:
            continue
        first, last = g.txn_date.min(), g.txn_date.max()
        active = (ledger_end - last).days <= 45
        dur_m = max(months, round((last - first).days / 30.44))
        r3 = ret_3m(g.mstar_id.iloc[0], first) if pd.notna(g.mstar_id.iloc[0]) else None
        streams.append(
            dict(
                client_id=int(cid), months=dur_m, stopped=not active,
                equity=1 if g.asset_class.iloc[0] == "Equity" else 0,
                rally_start=1 if (r3 is not None and r3 > 0.10) else 0,
                monthly=float(g.amount.tail(6).median() or 0),
            )
        )
    sdf = pd.DataFrame(streams)
    sdf["amt_high"] = (sdf.monthly >= sdf.monthly.quantile(2 / 3)).astype(int)
    km = KaplanMeierFitter()
    km.fit(sdf.months, sdf.stopped, label="all SIP streams")
    med = km.median_survival_time_
    print(
        f"\nSIP streams: {len(sdf)} (stopped {int(sdf.stopped.sum())}, active {int((~sdf.stopped).sum())}) "
        f"— median stream life {med:.0f} months"
    )
    cox = CoxPHFitter()
    cox.fit(
        sdf[["months", "stopped", "equity", "rally_start", "amt_high"]],
        duration_col="months", event_col="stopped",
    )
    print("Cox PH on stream stop (HR > 1 = stops sooner):")
    for cov in ("equity", "rally_start", "amt_high"):
        row = cox.summary.loc[cov]
        print(
            f"  {cov:12s} HR {np.exp(row['coef']):.2f} "
            f"[{np.exp(row['coef lower 95%']):.2f}–{np.exp(row['coef upper 95%']):.2f}] p={row['p']:.3f}"
        )

    # ---- 2. holding (fund-folio) survival ----
    fin = pd.read_sql(
        """select client_id, fund_name, folio,
                  (array_agg(balance_units order by txn_date desc nulls last, txn_id desc))[1]::float fb
           from wealth.transactions group by 1, 2, 3""",
        conn,
    )
    fin_key = {(int(r.client_id), r.fund_name, r.folio): (r.fb or 0) < 0.01 for r in fin.itertuples()}
    hold = []
    for (cid, sid, fn, fo), g in txns.groupby(["client_id", "scheme_id", "fund_name", "folio"], dropna=False):
        first, last = g.txn_date.min(), g.txn_date.max()
        hold.append(
            dict(
                client_id=int(cid),
                years=max((last - first).days / 365.25, 0.05),
                closed=fin_key.get((int(cid), fn, fo), False),
                equity=1 if g.asset_class.iloc[0] == "Equity" else 0,
            )
        )
    hdf = pd.DataFrame(hold)
    kmh = KaplanMeierFitter()
    kmh.fit(hdf.years, hdf.closed, label="all holdings")
    kme = KaplanMeierFitter().fit(hdf[hdf.equity == 1].years, hdf[hdf.equity == 1].closed, label="equity")
    kmn = KaplanMeierFitter().fit(hdf[hdf.equity == 0].years, hdf[hdf.equity == 0].closed, label="non-equity")
    print(
        f"\nholdings: {len(hdf)} fund-folios ({int(hdf.closed.sum())} fully closed) — "
        f"median relationship life {kmh.median_survival_time_:.1f}y "
        f"(equity {kme.median_survival_time_:.1f}y, non-equity {kmn.median_survival_time_:.1f}y)"
    )

    # ---- 3. per-client disengagement early-warning (active clients) ----
    ext_in = txns[txns.txn_type.isin(["purchase", "sip"]) & txns.amount.gt(0)]
    ext_out = txns[txns.txn_type.isin(["redemption", "swp"]) & txns.amount.gt(0)]
    last_in = ext_in.groupby("client_id").txn_date.max()
    out12 = ext_out[ext_out.txn_date > ledger_end - pd.Timedelta(days=365)].groupby("client_id").amount.sum()
    sip_stats = sdf.groupby("client_id").agg(streams=("stopped", "size"), stopped=("stopped", "sum"))

    rows = []
    for cid in life[~life.departed].index:
        cmv = float(life.loc[cid, "mv"])
        li = last_in.get(cid)
        months_quiet = (ledger_end - li).days / 30.44 if pd.notna(li) else 999
        st = sip_stats.loc[cid] if cid in sip_stats.index else None
        sip_stop_share = float(st.stopped / st.streams) if st is not None and st.streams else None
        o12 = float(out12.get(cid, 0))
        out_share = min(o12 / cmv, 1.0) if cmv > 1000 else (1.0 if o12 > 0 else 0.0)
        # transparent 0-100 score: equal thirds, each factor already 0-1
        f_quiet = min(months_quiet / 24, 1.0)  # 2y+ without an inflow = max
        f_sip = sip_stop_share if sip_stop_share is not None else 0.5  # no SIP history = neutral
        f_out = out_share
        score = round(100 * (f_quiet + f_sip + f_out) / 3, 1)
        rows.append(
            (int(cid), cmv, round(months_quiet, 1), sip_stop_share, round(out_share, 3), score)
        )
    ew = pd.DataFrame(
        rows, columns=["client_id", "mv", "months_since_inflow", "sip_stop_share", "out12_share", "score"]
    )
    # expected remaining years from the all-holdings KM restricted-mean (cap 25y)
    from lifelines.utils import restricted_mean_survival_time

    rmst = restricted_mean_survival_time(kmh, t=25)
    ew["clv_aum_years"] = (ew.mv * rmst / 1e5).round(1)  # in ₹L·years
    print(
        f"\nearly-warning: {len(ew)} active clients scored; restricted-mean remaining "
        f"holding-life {rmst:.1f}y (25y cap) → CLV proxy = AUM × {rmst:.1f} AUM-years "
        f"(no trail-rate assumption made)"
    )

    names = pd.read_sql("select client_id, full_name from wealth.clients", conn).set_index("client_id").full_name
    top = ew.sort_values("score", ascending=False).head(12)
    print("highest disengagement risk (call list):")
    for r in top.itertuples():
        print(
            f"  {names.get(r.client_id, '?'):42s} score {r.score:5.1f} · ₹{r.mv / 1e5:7.1f}L · "
            f"quiet {r.months_since_inflow:5.1f}m · SIP-stop {('—' if r.sip_stop_share is None else f'{r.sip_stop_share:.0%}'):>4s} · "
            f"12m-out {r.out12_share:.0%}"
        )

    # ---- persist ----
    cur = conn.cursor()
    cur.execute("drop table if exists wealth.client_churn_risk")
    cur.execute(
        """create table wealth.client_churn_risk (
             client_id bigint primary key references wealth.clients(client_id),
             mv numeric(18,2), months_since_inflow numeric(8,1),
             sip_stop_share numeric(6,3), out12_share numeric(6,3),
             disengagement_score numeric(6,1),
             clv_aum_l_years numeric(14,1),
             computed_asof date not null
           )"""
    )
    execute_values(
        cur,
        """insert into wealth.client_churn_risk
           (client_id, mv, months_since_inflow, sip_stop_share, out12_share,
            disengagement_score, clv_aum_l_years, computed_asof) values %s""",
        [
            (
                int(r.client_id), r.mv, r.months_since_inflow,
                r.sip_stop_share, r.out12_share, r.score, r.clv_aum_years,
                str(ledger_end.date()),
            )
            for r in ew.itertuples()
        ],
        page_size=500,
    )
    cur.execute("drop table if exists wealth.churn_curves")
    cur.execute(
        """create table wealth.churn_curves (
             curve text not null, t numeric(10,2) not null, s numeric(8,5) not null,
             primary key (curve, t)
           )"""
    )
    curve_rows = []
    for label, fitter, unit in (
        ("sip_stream_months", km, 1.0),
        ("holding_years_all", kmh, 1.0),
        ("holding_years_equity", kme, 1.0),
        ("holding_years_nonequity", kmn, 1.0),
    ):
        sf = fitter.survival_function_
        col = sf.columns[0]
        for t, v in sf[col].items():
            curve_rows.append((label, round(float(t), 2), round(float(v), 5)))
    execute_values(
        cur, "insert into wealth.churn_curves (curve, t, s) values %s on conflict do nothing",
        curve_rows, page_size=1000,
    )
    cur.execute("revoke all on wealth.client_churn_risk from anon, authenticated")
    cur.execute("revoke all on wealth.churn_curves from anon, authenticated")
    conn.commit()
    print(f"\nwrote wealth.client_churn_risk ({len(ew)}) + wealth.churn_curves ({len(curve_rows)} pts)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
