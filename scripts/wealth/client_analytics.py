"""Client-level analytics v2 — full-coverage risk, benchmark alpha, fees, rules.

Produces:
  * wealth.client_flags — the rules engine (explicit rules -> client lists ->
    action + estimated value with its basis)
  * a JSON blob (aggregates + per-client rows) consumed by the dossier page

Benchmark = ICICI Pru Nifty 50 Index Reg Gr NAV (F0GBR06R0H, history to 2006):
client's own purchase dates/amounts replayed into the index fund -> benchmark
XIRR -> alpha. Clients with material withdrawals are flagged approximate (their
outflow dates are not in the valuation report).

Usage:
    .venv/bin/python scripts/wealth/client_analytics.py --out /path/dossier_data.json
"""

from __future__ import annotations

import argparse
import json
import os
import warnings
from datetime import date

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")
BENCH_ID = "F0GBR06R0H"
BENCH_NAME = "ICICI Pru Nifty 50 Index (Reg-G)"
INDEX_ER = 0.20  # achievable index-fund expense ratio, %/yr
AS_ON = date(2026, 7, 14)


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Bisection IRR on dated flows; returns % p.a. or None."""
    if len(flows) < 2:
        return None
    t0 = flows[0][0]
    yrs = np.array([(d - t0).days / 365.25 for d, _ in flows])
    amt = np.array([a for _, a in flows], float)

    def npv(r):
        return float((amt / (1 + r) ** yrs).sum())

    lo, hi = -0.95, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(90):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return round(((lo + hi) / 2) * 100, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)

    hold = pd.read_sql("""
        select h.client_id, h.market_value, h.investments, h.inv_since, h.inv_days,
               h.xirr_pct, s.scheme_id, s.display_name, s.asset_class, s.sub_category,
               s.mstar_id, fr.composite, fr.cat_rank, fr.cat_size, fr.category,
               m.expense_ratio
        from wealth.holdings h
        join wealth.schemes s using (scheme_id)
        left join atlas_foundation.fund_rank_daily fr on fr.mstar_id = s.mstar_id
             and fr.date = (select max(date) from atlas_foundation.fund_rank_daily)
        left join atlas_foundation.de_mf_master m on m.mstar_id = s.mstar_id
        where h.market_value is not null""", conn)
    for c in ("market_value", "investments", "xirr_pct", "composite", "cat_rank",
              "cat_size", "expense_ratio"):
        hold[c] = pd.to_numeric(hold[c], errors="coerce")
    hold["inv_since"] = pd.to_datetime(hold["inv_since"]).dt.date

    rep = pd.read_sql("""
        select r.client_id, c.full_name, c.family_group, r.mv_total, r.mv_equity,
               r.mv_hybrid, r.mv_debt, r.mv_others, r.overall_xirr_pct as xirr,
               r.lumpsum_purchases + r.systematic_investments + r.switch_ins as gross_in,
               r.redemptions + r.switch_outs + r.systematic_withdrawals as gross_out,
               r.systematic_investments, r.dividend_payouts,
               sc.wcomp, sc.laggard_pct, sc.outcome_grade, sc.dup_cats, sc.side_pockets,
               sc.financials_pct, sc.top10_stock_pct
        from wealth.client_reports r
        join wealth.clients c using (client_id)
        join wealth.client_scorecard sc using (client_id)
        where r.mv_total > 1e5""", conn)
    for c in rep.columns:
        if c not in ("full_name", "family_group", "outcome_grade"):
            rep[c] = pd.to_numeric(rep[c], errors="coerce")

    # ---- NAV panel (held funds + benchmark), weekly ----
    ids = tuple(sorted(set(hold.mstar_id.dropna()) | {BENCH_ID}))
    nav = pd.read_sql(
        "select mstar_id, nav_date, nav from atlas_foundation.de_mf_nav_daily "
        f"where mstar_id in {ids} and nav_date >= '2022-07-01' and nav > 0", conn)
    nav["nav_date"] = pd.to_datetime(nav.nav_date)
    wide = (nav.pivot_table(index="nav_date", columns="mstar_id", values="nav")
               .resample("W-FRI").last())
    wret = wide.pct_change(fill_method=None)
    volf = (wret.std() * np.sqrt(52)).rename("ann_vol")
    volf[wret.count() < 60] = np.nan
    ret3y = (wide.iloc[-1] / wide.iloc[0]) ** (1 / 3) - 1  # ~3y CAGR window

    bench_full = pd.read_sql(
        "select nav_date, nav from atlas_foundation.de_mf_nav_daily "
        f"where mstar_id = '{BENCH_ID}' and nav > 0 order by nav_date", conn)
    bench_full["nav_date"] = pd.to_datetime(bench_full.nav_date)
    bench_daily = bench_full.set_index("nav_date").nav.sort_index()
    bench_w = wret[BENCH_ID]

    # ---- per-fund closet-indexer stats (equity with ER) ----
    fundstats = []
    for mid in wret.columns:
        if mid == BENCH_ID:
            continue
        pair = pd.concat([wret[mid], bench_w], axis=1).dropna()
        if len(pair) < 80:
            continue
        r2 = pair.corr().iloc[0, 1] ** 2
        te = float((pair.iloc[:, 0] - pair.iloc[:, 1]).std() * np.sqrt(52))
        fundstats.append((mid, r2, te))
    fs = pd.DataFrame(fundstats, columns=["mstar_id", "r2", "te"]).set_index("mstar_id")

    h = hold.merge(fs, left_on="mstar_id", right_index=True, how="left")
    h["ann_vol"] = h.mstar_id.map(volf)
    h["ret3y"] = h.mstar_id.map(ret3y)
    h["closet"] = ((h.r2 >= 0.93) & (h.expense_ratio >= 0.8)
                   & (h.asset_class == "Equity"))
    h["fee_save"] = np.where(h.closet, h.market_value * (h.expense_ratio - INDEX_ER) / 100, 0.0)

    # ---- per-client aggregates ----
    def agg(d: pd.DataFrame) -> pd.Series:
        mv = d.market_value.sum()
        cov = d.loc[d.ann_vol.notna(), "market_value"].sum()
        lag_mv = d.loc[(d.cat_rank / d.cat_size > 0.75), "market_value"].sum()
        return pd.Series({
            "port_vol": (d.market_value * d.ann_vol).sum() / cov if cov > 0 else np.nan,
            "vol_cov": cov / mv,
            "wret3y": (d.market_value * d.ret3y).sum()
                      / d.loc[d.ret3y.notna(), "market_value"].sum()
                      if d.ret3y.notna().any() else np.nan,
            "fee_save": d.fee_save.sum(),
            "closet_mv": d.loc[d.closet, "market_value"].sum(),
            "lag_mv": lag_mv, "scored_mv": d.loc[d.composite.notna(), "market_value"].sum(),
        })

    per = h.groupby("client_id").apply(agg).reset_index()

    # swap headroom: laggards -> same-category best realized 3y sharpe among held peers
    cat_best = (h.dropna(subset=["ret3y", "ann_vol", "category"])
                  .assign(sharpe=lambda d: d.ret3y / d.ann_vol)
                  .groupby("category").agg(best_ret=("ret3y", "max"),
                                           best_sharpe=("sharpe", "max")))
    hh = h.merge(cat_best, on="category", how="left")
    hh["is_lag"] = hh.cat_rank / hh.cat_size > 0.75
    swap = (hh[hh.is_lag & hh.best_ret.notna() & hh.ret3y.notna()]
            .assign(gain=lambda d: d.market_value * (d.best_ret - d.ret3y))
            .groupby("client_id").gain.sum().rename("swap_gain_rs"))
    per = per.merge(swap, on="client_id", how="left")

    # ---- benchmark alpha: EXACT ledger-flow replay (exact_benchmark.py) ----
    # wealth.client_benchmark replays every external cash flow from the Folio
    # Ledgers into the index fund; the old buy-only approximation is retired.
    bench = pd.read_sql(
        """select client_id, xirr_client, xirr_bench bench_xirr, alpha ex_alpha,
                  approx bench_approx
           from wealth.client_benchmark""",
        conn,
    )
    for c in ("xirr_client", "bench_xirr", "ex_alpha"):
        bench[c] = pd.to_numeric(bench[c], errors="coerce")

    cl = rep.merge(per, on="client_id", how="left").merge(bench, on="client_id", how="left")
    # exact ledger XIRR supersedes the valuation report's own figure where present
    cl["xirr"] = cl.xirr_client.combine_first(cl.xirr)
    cl["approx_flows"] = cl.bench_approx.fillna(True).astype(bool)
    cl["alpha"] = cl.xirr - cl.bench_xirr
    cl["laggard_share"] = cl.lag_mv / cl.scored_mv.replace(0, np.nan)

    # ---- sector exposure per client ----
    sec = pd.read_sql("""
        select x.client_id, coalesce(nullif(im.sector,''),'Other') as sector,
               sum(x.exposure) as exp
        from wealth.client_stock_exposure x
        left join atlas_foundation.instrument_master im using (instrument_id)
        where x.bucket like '%%stock%%' group by 1,2""", conn)
    sec["exp"] = pd.to_numeric(sec["exp"])
    stot = sec.groupby("client_id")["exp"].sum().rename("stot")
    sec = sec.merge(stot, on="client_id")
    sec["share"] = sec["exp"] / sec.stot
    top_sec = sec.loc[sec.groupby("client_id").share.idxmax()][["client_id", "sector", "share"]]
    top_sec.columns = ["client_id", "top_sector", "top_sector_share"]
    cl = cl.merge(top_sec, on="client_id", how="left")
    sector_cohort = (sec.groupby("sector")
                     .agg(cr=("exp", lambda s: round(s.sum() / 1e7, 1)),
                          clients=("client_id", "nunique"),
                          med_share=("share", "median")).reset_index()
                     .sort_values("cr", ascending=False).head(12))

    # ---- amc concentration ----
    hold["amc"] = hold.display_name.str.split().str[0]
    amc_mv = hold.groupby(["client_id", "amc"]).market_value.sum().reset_index()
    amc_tot = amc_mv.groupby("client_id").market_value.sum().rename("tot")
    amc_mv = amc_mv.merge(amc_tot, on="client_id")
    amc_top = amc_mv.assign(sh=lambda d: d.market_value / d.tot).groupby("client_id").sh.max()
    cl = cl.merge(amc_top.rename("top_amc_share"), on="client_id", how="left")

    # ---- RULES ENGINE ----
    rules = []

    def add(cid, rule, evidence, action, value, basis):
        rules.append(dict(client_id=int(cid), rule=rule, evidence=evidence,
                          action=action, est_value=value, basis=basis))

    for r in cl.itertuples():
        lag = (r.laggard_share or 0) * 100
        recent_guard = False
        if r.xirr is not None and r.xirr < 12:
            grp = hold[hold.client_id == r.client_id]
            rec_share = grp.loc[[d >= date(2024, 7, 1) for d in grp.inv_since],
                                "market_value"].sum() / max(grp.market_value.sum(), 1)
            if rec_share >= 0.5:
                recent_guard = True
                add(r.client_id, "R0 recent-buyer guard",
                    f"{rec_share:.0%} of book bought since Jul-24; XIRR {r.xirr}%",
                    "HOLD — do not churn; review at 18-month mark", None, "protection rule")
        if lag >= 50 and not recent_guard:
            g = float(r.swap_gain_rs) if r.swap_gain_rs == r.swap_gain_rs else 0.0
            add(r.client_id, "R1 laggards ≥50%",
                f"{lag:.0f}% of scored value in category-bottom-quartile funds",
                "swap worst laggards to category leaders (LTCG-budgeted)",
                round(g), "₹/yr if laggards had matched best held same-category 3y CAGR (historical, not promised)")
        elif lag >= 25 and not recent_guard:
            g = float(r.swap_gain_rs) if r.swap_gain_rs == r.swap_gain_rs else 0.0
            add(r.client_id, "R2 laggards 25-50%",
                f"{lag:.0f}% of scored value in bottom-quartile funds",
                "1-2 swaps at next review; redirect SIPs first", round(g),
                "same basis as R1")
        if r.fee_save and r.fee_save > 10000:
            add(r.client_id, "R3 closet-indexer fees",
                f"₹{r.closet_mv / 1e5:.1f}L in funds tracking Nifty50 (R²≥0.93) at active fees",
                f"switch to index fund @ {INDEX_ER}% ER",
                round(float(r.fee_save)), "₹/yr certain fee saving (ER spread × value)")
        if r.top_amc_share and r.top_amc_share > 0.35:
            add(r.client_id, "R4 single-AMC >35%",
                f"top AMC = {r.top_amc_share:.0%} of book",
                "diversify AMC exposure on next inflows", None, "risk reduction")
        if r.dup_cats and r.dup_cats >= 2:
            add(r.client_id, "R5 category duplication",
                f"{int(r.dup_cats)} sub-categories held 3+ times",
                "consolidate to best 1-2 per category", None,
                "fewer overlapping bets; cleaner attribution")
        if r.side_pockets and r.side_pockets > 0:
            add(r.client_id, "R6 dead side-pockets",
                f"{int(r.side_pockets)} segregated-portfolio lines",
                "write-off recognition / exit paperwork", None, "hygiene")
        if (r.mv_hybrid / max(r.mv_total, 1)) >= 0.40 and r.xirr is not None and r.xirr < 12 and not recent_guard:
            add(r.client_id, "R7 hybrid-parked underperformer",
                f"{r.mv_hybrid / r.mv_total:.0%} in hybrids; XIRR {r.xirr}%",
                "risk-capacity conversation → staged mix shift", None,
                "allocation, not selection")
        if r.top_sector_share and r.top_sector_share > 0.35:
            add(r.client_id, "R8 sector concentration >35%",
                f"{r.top_sector}: {r.top_sector_share:.0%} of stock exposure",
                "trim via fund choice on next moves", None, "risk reduction")

    fl = pd.DataFrame(rules)
    cur = conn.cursor()
    cur.execute("""drop table if exists wealth.client_flags;
        create table wealth.client_flags (
          client_id bigint references wealth.clients(client_id),
          rule text, evidence text, action text,
          est_value numeric, basis text,
          created_at timestamptz not null default now());
        revoke all on wealth.client_flags from anon, authenticated;""")
    from psycopg2.extras import execute_values as ev
    ev(cur, "insert into wealth.client_flags (client_id, rule, evidence, action, est_value, basis) values %s",
       [(x["client_id"], x["rule"], x["evidence"], x["action"], x["est_value"], x["basis"]) for x in rules])
    conn.commit()

    # ---- JSON out ----
    def jr(v, nd=2):
        return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)

    clients_json = []
    for r in cl.itertuples():
        clients_json.append(dict(
            id=int(r.client_id), name=r.full_name, grp=r.family_group,
            mv=jr(r.mv_total / 1e5, 1), xirr=jr(r.xirr), grade=r.outcome_grade,
            bench=jr(r.bench_xirr), alpha=jr(r.alpha), approx=bool(r.approx_flows),
            vol=jr((r.port_vol or np.nan) * 100, 1), volcov=jr((r.vol_cov or 0) * 100, 0),
            wret3y=jr((r.wret3y or np.nan) * 100, 1),
            lag=jr((r.laggard_share or np.nan) * 100, 0),
            fee=jr(r.fee_save, 0), wcomp=jr(r.wcomp, 1),
            topsec=r.top_sector if isinstance(r.top_sector, str) else None,
            topsecsh=jr((r.top_sector_share or np.nan) * 100, 0),
            eq=jr(r.mv_equity / max(r.mv_total, 1) * 100, 0),
            hy=jr(r.mv_hybrid / max(r.mv_total, 1) * 100, 0),
        ))

    rule_summary = (fl.groupby("rule").agg(clients=("client_id", "nunique"),
                                           total_value=("est_value", "sum"))
                      .reset_index().to_dict("records"))
    closet_funds = (h[h.closet].groupby("display_name")
                    .agg(mv_cr=("market_value", lambda s: round(s.sum() / 1e7, 2)),
                         clients=("client_id", "nunique"),
                         er=("expense_ratio", "median"), r2=("r2", "median"))
                    .reset_index().sort_values("mv_cr", ascending=False).to_dict("records"))

    out = dict(
        as_on=str(AS_ON), bench=BENCH_NAME,
        clients=clients_json,
        rules=[{k: (jr(v, 0) if k == "total_value" else v) for k, v in r.items()} for r in rule_summary],
        flags=rules,
        closet_funds=closet_funds,
        sector_cohort=sector_cohort.assign(med_share=lambda d: (d.med_share * 100).round(1)).to_dict("records"),
        beat=dict(
            n=int(cl.alpha.notna().sum()),
            beating=int((cl.alpha > 0).sum()),
            med_alpha=jr(cl.alpha.median()),
            med_bench=jr(cl.bench_xirr.median()),
            clean=int((~cl.approx_flows & cl.alpha.notna()).sum()),
            beating_clean=int(((cl.alpha > 0) & ~cl.approx_flows).sum()),
        ),
        fees=dict(total=jr(cl.fee_save.sum(), 0), clients=int((cl.fee_save > 10000).sum()),
                  closet_mv_cr=jr(h.loc[h.closet, "market_value"].sum() / 1e7, 1)),
        risk=dict(covered=int((cl.vol_cov > 0.5).sum()), total=len(cl)),
    )
    with open(args.out, "w") as f:
        json.dump(out, f, allow_nan=False)
    print(f"clients={len(clients_json)} bench_computed={out['beat']['n']} "
          f"beating={out['beat']['beating']} med_alpha={out['beat']['med_alpha']} "
          f"med_bench={out['beat']['med_bench']} clean={out['beat']['clean']} "
          f"beating_clean={out['beat']['beating_clean']}")
    print(f"vol coverage now {out['risk']['covered']}/{out['risk']['total']}")
    print(f"closet-indexer value ₹{out['fees']['closet_mv_cr']}cr, fee savings ₹{out['fees']['total']:,}/yr")
    print(f"flags: {len(rules)} across {fl.client_id.nunique()} clients")
    print(fl.groupby('rule').size().to_string())
    conn.close()


if __name__ == "__main__":
    main()
