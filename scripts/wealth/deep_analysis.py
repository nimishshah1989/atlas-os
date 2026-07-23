"""Deep risk-return + attribution analysis over the Jhaveri book (all real data).

Sections:
  A. portfolio risk-return map (XIRR vs realized weighted fund vol/MDD)
  B. XIRR variance attribution: mix -> timing -> tilts -> selection -> behaviour
  C. Atlas validation: client 2x2 (XIRR quartile x wcomp quartile), holding-level
     composite-decile vs realized XIRR within category+vintage, and the honest
     95-day point-in-time forward test (composite@2026-03-02 vs NAV return since)
  D. vintage surface: median holding XIRR by entry-year x asset class / category
  E. strong-portfolio fingerprint: top vs bottom XIRR quartile feature contrast

Usage:
    .venv/bin/python scripts/wealth/deep_analysis.py
"""

from __future__ import annotations

import os
import warnings

import numpy as np
import pandas as pd
import psycopg2

warnings.filterwarnings("ignore")  # pandas read_sql on psycopg2 conn

DSN = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")


def q(conn, sql: str) -> pd.DataFrame:
    return pd.read_sql(sql, conn)


def nested_r2(df: pd.DataFrame, y: str, blocks: list[tuple[str, list[str]]]) -> None:
    """Sequential OLS: incremental R^2 as each feature block is added."""
    d = df.dropna(subset=[y] + [c for _, cols in blocks for c in cols]).copy()
    yy = d[y].to_numpy(float)
    yy_c = yy - yy.mean()
    tss = float(yy_c @ yy_c)
    X = np.ones((len(d), 1))
    prev = 0.0
    print(f"  n={len(d)}  (block -> incremental R^2, cumulative)")
    for name, cols in blocks:
        X = np.hstack([X, d[cols].to_numpy(float)])
        beta, *_ = np.linalg.lstsq(X, yy, rcond=None)
        resid = yy - X @ beta
        r2 = 1 - float(resid @ resid) / tss
        print(f"  + {name:<28} +{r2 - prev:5.1%}   cum {r2:5.1%}")
        prev = r2


def main() -> None:
    conn = psycopg2.connect(DSN)

    # ---------- client-level feature table ----------
    cl = q(
        conn,
        """
        with flows as (
          select client_id, overall_xirr_pct as xirr, mv_total,
                 mv_equity/nullif(mv_total,0) as eq_share,
                 mv_hybrid/nullif(mv_total,0) as hy_share,
                 (mv_others)/nullif(mv_total,0) as other_share,
                 systematic_investments/nullif(lumpsum_purchases+systematic_investments+switch_ins,0) as sip_share,
                 (redemptions+switch_outs)/nullif(lumpsum_purchases+systematic_investments+switch_ins,0) as churn
          from wealth.client_reports where mv_total > 1e5),
        hold as (
          select h.client_id,
                 sum(h.market_value*h.inv_days)/nullif(sum(h.market_value),0)/365.25 as w_age_yrs,
                 sum(h.market_value) filter (where h.inv_since >= '2024-07-01')/nullif(sum(h.market_value),0) as recent_share,
                 sum(h.market_value) filter (where s.sub_category ~* 'small cap|mid cap|midcap')/nullif(sum(h.market_value),0) as smallmid_share,
                 sum(h.market_value) filter (where s.asset_class='Commodities')/nullif(sum(h.market_value),0) as commodity_share
          from wealth.holdings h join wealth.schemes s using (scheme_id)
          where h.market_value is not null group by 1),
        sc as (select client_id, wcomp, laggard_pct/100.0 as laggard_share,
                      top10_stock_pct, financials_pct, dup_cats, n_lines
               from wealth.client_scorecard)
        select f.*, h.w_age_yrs, h.recent_share, h.smallmid_share, h.commodity_share,
               s.wcomp, s.laggard_share, s.top10_stock_pct, s.financials_pct, s.dup_cats, s.n_lines
        from flows f join hold h using (client_id) join sc s using (client_id)""",
    )
    cl = cl.apply(pd.to_numeric, errors="coerce")

    # fund realized risk from NAV series (3y weekly), for funds the book holds
    risk = q(
        conn,
        """
        with held as (select distinct mstar_id from wealth.schemes where mstar_id is not null),
        nav as (
          select n.mstar_id, n.nav_date, n.nav as nav_adj
          from atlas_foundation.de_mf_nav_daily n join held using (mstar_id)
          where n.nav_date >= current_date - interval '3 years' and n.nav > 0),
        wk as (
          select mstar_id, date_trunc('week', nav_date) as w, max(nav_date) as d
          from nav group by 1,2),
        wnav as (
          select nav.mstar_id, nav.nav_adj, wk.w
          from nav join wk on wk.mstar_id=nav.mstar_id and wk.d=nav.nav_date),
        ret as (
          select mstar_id, w,
                 nav_adj/lag(nav_adj) over (partition by mstar_id order by w) - 1 as r
          from wnav)
        select mstar_id, stddev_samp(r)*sqrt(52) as ann_vol, count(*) as n_wk
        from ret where r is not null group by 1 having count(*) >= 100""",
    )

    hold = q(
        conn,
        """
        select h.client_id, h.market_value, h.xirr_pct, h.inv_since, h.inv_days,
               s.mstar_id, s.asset_class, s.sub_category, s.scheme_id, s.display_name,
               fr.composite, fr.cat_rank, fr.cat_size
        from wealth.holdings h
        join wealth.schemes s using (scheme_id)
        left join atlas_foundation.fund_rank_daily fr
          on fr.mstar_id = s.mstar_id
         and fr.date = (select max(date) from atlas_foundation.fund_rank_daily)
        where h.market_value is not null""",
    )
    hold["inv_since"] = pd.to_datetime(hold["inv_since"])
    hold["entry_year"] = hold["inv_since"].dt.year.clip(lower=2015)
    for c in ("market_value", "xirr_pct", "composite", "cat_rank", "cat_size"):
        hold[c] = pd.to_numeric(hold[c], errors="coerce")

    # ---------- A. risk-return map ----------
    print("=" * 76)
    print("A. PORTFOLIO RISK-RETURN MAP (realized 3y weekly vol, weighted; real NAVs)")
    hv = hold.merge(risk, on="mstar_id", how="left")
    pv = (
        hv.assign(wv=lambda d: d.market_value * d.ann_vol)
        .groupby("client_id")
        .apply(
            lambda d: pd.Series(
                {
                    "port_vol": d.wv.sum() / d.loc[d.ann_vol.notna(), "market_value"].sum()
                    if d.ann_vol.notna().any()
                    else np.nan,
                    "vol_cov": d.loc[d.ann_vol.notna(), "market_value"].sum()
                    / d.market_value.sum(),
                }
            )
        )
        .reset_index()
    )
    a = cl.merge(pv, on="client_id")
    a = a[(a.vol_cov > 0.5) & a.xirr.notna() & a.port_vol.notna()]
    assert len(a) > 50, f"vol coverage collapsed: only {len(a)} clients"
    a["ret_q"] = pd.qcut(a.xirr, 2, labels=["loRet", "hiRet"])
    a["vol_q"] = pd.qcut(a.port_vol, 2, labels=["loVol", "hiVol"])
    quad = a.groupby(["vol_q", "ret_q"], observed=True).agg(
        clients=("client_id", "count"),
        med_xirr=("xirr", "median"),
        med_vol=("port_vol", "median"),
        aum_cr=("mv_total", lambda s: round(s.sum() / 1e7, 1)),
    )
    print(quad.round(2).to_string())
    print(f"  vol coverage: {len(a)}/{len(cl)} clients with >=50% of MV vol-covered")
    hi_lo = a[(a.ret_q == "hiRet") & (a.vol_q == "loVol")]
    print(
        f"  EFFICIENT quadrant (hiRet/loVol): {len(hi_lo)} clients, "
        f"med XIRR {hi_lo.xirr.median():.1f}%, med vol {hi_lo.port_vol.median():.1%}"
    )

    # ---------- B. attribution ----------
    print("=" * 76)
    print("B. XIRR VARIANCE ATTRIBUTION (nested OLS, client level)")
    blocks = [
        ("asset mix (eq/hy/other)", ["eq_share", "hy_share", "other_share"]),
        ("entry timing (age, recent%)", ["w_age_yrs", "recent_share"]),
        ("tilts (small-mid, commodity)", ["smallmid_share", "commodity_share"]),
        ("fund selection (wcomp, laggard)", ["wcomp", "laggard_share"]),
        ("behaviour (SIP%, churn)", ["sip_share", "churn"]),
    ]
    nested_r2(cl, "xirr", blocks)
    print("  (order-robustness: selection block alone, added last vs first)")
    nested_r2(cl, "xirr", [blocks[3]])

    # ---------- C. Atlas validation ----------
    print("=" * 76)
    print("C1. CLIENT 2x2: XIRR quartile x weighted-composite quartile (counts | AUM cr)")
    c = cl.dropna(subset=["xirr", "wcomp"]).copy()
    c["xirr_q"] = pd.qcut(c.xirr, 4, labels=["Q1 worst", "Q2", "Q3", "Q4 best"])
    c["comp_q"] = pd.qcut(c.wcomp, 4, labels=["C1 low", "C2", "C3", "C4 high"])
    t = pd.crosstab(c.xirr_q, c.comp_q)
    t_aum = pd.crosstab(c.xirr_q, c.comp_q, values=c.mv_total / 1e7, aggfunc="sum").round(1)
    print(t.to_string())
    print("-- AUM (cr):")
    print(t_aum.to_string())
    print(
        f"  median laggard-share by XIRR quartile: "
        f"{c.groupby('xirr_q', observed=True).laggard_share.median().round(3).to_dict()}"
    )
    r = np.corrcoef(c.xirr.rank(), c.wcomp.rank())[0, 1]
    print(f"  Spearman(XIRR, wcomp) = {r:.3f}")

    print("\nC2. HOLDING-LEVEL: current composite decile vs realized holding XIRR")
    h = hold.dropna(subset=["xirr_pct", "composite"]).query("inv_days > 365").copy()
    h["comp_dec"] = pd.qcut(h.composite, 10, labels=False, duplicates="drop") + 1
    print("  (equity holdings held >1y; median XIRR by composite decile)")
    print(h.groupby("comp_dec").xirr_pct.agg(["median", "count"]).round(1).to_string())
    # within category + entry-year (kills vintage/category confounds)
    h["cell"] = h.sub_category + "|" + h.entry_year.astype(str)
    cells = h.groupby("cell").filter(lambda d: d.composite.nunique() > 3 and len(d) >= 8)
    if len(cells):

        def cell_corr(d):
            return pd.Series(
                {"rho": np.corrcoef(d.composite.rank(), d.xirr_pct.rank())[0, 1], "n": len(d)}
            )

        cc = cells.groupby("cell").apply(cell_corr)
        wmean = float(np.average(cc.rho, weights=cc.n))
        print(
            f"  within category+entry-year cells (n={len(cc)} cells, {int(cc.n.sum())} holdings): "
            f"weighted mean Spearman = {wmean:.3f}; {(cc.rho > 0).mean():.0%} of cells positive"
        )
    print("  CAVEAT: current composite vs past XIRR is consistency, NOT prediction. ->C3")

    print("\nC3. POINT-IN-TIME (honest, short): composite@2026-03-02 vs NAV return since")
    pit = q(
        conn,
        """
        with s0 as (select mstar_id, composite from atlas_foundation.fund_rank_daily
                    where date = '2026-03-02'),
        held as (select distinct mstar_id from wealth.schemes where mstar_id is not null),
        p0 as (select n.mstar_id, n.nav as nav_adj from atlas_foundation.de_mf_nav_daily n
               where n.nav_date = (select min(nav_date) from atlas_foundation.de_mf_nav_daily
                                   where nav_date >= '2026-03-02')),
        p1 as (select n.mstar_id, n.nav as nav_adj from atlas_foundation.de_mf_nav_daily n
               where n.nav_date = (select max(nav_date) from atlas_foundation.de_mf_nav_daily))
        select s0.mstar_id, s0.composite, (p1.nav_adj/p0.nav_adj - 1)*100 as fwd_ret
        from s0 join held using (mstar_id) join p0 using (mstar_id) join p1 using (mstar_id)""",
    )
    pit = pit.dropna()
    pit["comp_q"] = pd.qcut(pit.composite, 4, labels=["C1 low", "C2", "C3", "C4 high"])
    print(
        pit.groupby("comp_q", observed=True).fwd_ret.agg(["median", "count"]).round(2).to_string()
    )
    print(
        f"  Spearman(composite@Mar, fwd 4.5m return) = "
        f"{np.corrcoef(pit.composite.rank(), pit.fwd_ret.rank())[0, 1]:.3f} (n={len(pit)})"
    )

    # ---------- D. vintage surface ----------
    print("=" * 76)
    print("D. VINTAGE SURFACE: median holding XIRR by entry year x asset class")
    hv2 = hold.dropna(subset=["xirr_pct"])
    surf = hv2.pivot_table(
        index="entry_year", columns="asset_class", values="xirr_pct", aggfunc="median"
    ).round(1)
    n_surf = hv2.pivot_table(
        index="entry_year", columns="asset_class", values="xirr_pct", aggfunc="count"
    )
    print(surf.where(n_surf >= 10).to_string())
    print("\n  top categories, entry 2024+ vs pre-2024 (median XIRR):")
    for cat in [
        "Equity - Small Cap",
        "Equity - Mid Cap",
        "Equity - Flexi Cap",
        "Hybrid - Multi Asset Allocation",
    ]:
        d = hv2[hv2.sub_category == cat]
        old = d[d.entry_year < 2024].xirr_pct.median()
        new = d[d.entry_year >= 2024].xirr_pct.median()
        print(f"    {cat:<36} pre-24: {old:6.1f}%   24+: {new:6.1f}%")

    # ---------- E. fingerprint ----------
    print("=" * 76)
    print("E. STRONG-PORTFOLIO FINGERPRINT (top vs bottom XIRR quartile, medians)")
    c["grp"] = np.where(
        c.xirr_q == "Q4 best", "TOP", np.where(c.xirr_q == "Q1 worst", "BOTTOM", None)
    )
    feats = [
        "eq_share",
        "hy_share",
        "smallmid_share",
        "commodity_share",
        "w_age_yrs",
        "recent_share",
        "wcomp",
        "laggard_share",
        "sip_share",
        "churn",
        "dup_cats",
        "n_lines",
        "financials_pct",
        "top10_stock_pct",
    ]
    fp = c[c.grp.notna()].groupby("grp")[feats].median().T.round(3)
    fp["delta"] = (fp.get("TOP") - fp.get("BOTTOM")).round(3)
    print(fp.to_string())
    conn.close()


if __name__ == "__main__":
    main()
