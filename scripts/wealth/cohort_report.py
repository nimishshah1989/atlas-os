"""Cohort + portfolio evaluation report over wealth schema joined to Atlas scores.

Read-only. Prints the numbers the recommendation-framework design is grounded in.

Usage:
    .venv/bin/python scripts/wealth/cohort_report.py
"""

from __future__ import annotations

import os

import psycopg2

Q = {
    "AUM bands": """
with c as (select r.client_id, r.mv_total from wealth.client_reports r)
select case when mv_total < 1e6 then 'a <10L' when mv_total < 5e6 then 'b 10-50L'
            when mv_total < 1e7 then 'c 50L-1cr' when mv_total < 5e7 then 'd 1-5cr'
            else 'e >5cr' end as band,
       count(*) as clients, round(sum(mv_total)/1e7,1) as aum_cr,
       round(100*sum(mv_total)/(select sum(mv_total) from c),1) as aum_pct
from c group by 1 order by 1;""",
    "Asset-class mix (cohort)": """
select round(sum(mv_equity)/1e7,1) eq_cr, round(sum(mv_hybrid)/1e7,1) hy_cr,
       round(sum(mv_debt)/1e7,1) dt_cr, round(sum(mv_others)/1e7,1) ot_cr,
       round(100*sum(mv_equity)/sum(mv_total),1) eq_pct,
       round(100*sum(mv_hybrid)/sum(mv_total),1) hy_pct
from wealth.client_reports where mv_total > 0;""",
    "Client equity% distribution": """
select width_bucket(100.0*mv_equity/mv_total, 0, 100, 5) as b,
       min(round(100.0*mv_equity/mv_total)) || '-' || max(round(100.0*mv_equity/mv_total)) || '%' as range,
       count(*) as clients, round(sum(mv_total)/1e7,1) as aum_cr
from wealth.client_reports where mv_total > 0 group by 1 order by 1;""",
    "Fragmentation & concentration per client": """
with per as (
  select h.client_id, count(*) as n_lines, count(distinct h.scheme_id) as n_schemes,
         max(h.port_weight_pct) as top_wgt,
         sum(power(coalesce(h.port_weight_pct,0)/100.0, 2)) as hhi
  from wealth.holdings h group by 1)
select round(avg(n_lines),1) avg_lines, round(avg(n_schemes),1) avg_schemes,
       percentile_cont(0.5) within group (order by n_schemes) med_schemes,
       round(avg(top_wgt)::numeric,1) avg_top_wgt,
       count(*) filter (where top_wgt >= 25) as clients_top_wgt_ge25,
       count(*) filter (where hhi >= 0.20) as clients_hhi_ge020
from per;""",
    "Flow behaviour (SIP vs lumpsum vs dividends)": """
select count(*) filter (where systematic_investments > 0) as sip_clients,
       count(*) filter (where systematic_investments = 0) as pure_lumpsum,
       count(*) filter (where dividend_payouts > 0) as dividend_takers,
       count(*) filter (where redemptions + switch_outs > 0.5*(lumpsum_purchases+systematic_investments+switch_ins)
                        and lumpsum_purchases+systematic_investments+switch_ins > 0) as heavy_redeemers
from wealth.client_reports;""",
    "Client XIRR distribution": """
select count(*) filter (where overall_xirr_pct < 8) as below_8,
       count(*) filter (where overall_xirr_pct >= 8 and overall_xirr_pct < 12) as p8_12,
       count(*) filter (where overall_xirr_pct >= 12 and overall_xirr_pct < 16) as p12_16,
       count(*) filter (where overall_xirr_pct >= 16) as above_16,
       round(percentile_cont(0.5) within group (order by overall_xirr_pct)::numeric,2) as median_xirr
from wealth.client_reports where mv_total > 1e5;""",
    "House book: most-held schemes": """
select s.display_name, s.asset_class, count(distinct h.client_id) as clients,
       round(sum(h.market_value)/1e7,2) as mv_cr, s.in_atlas_universe as scored
from wealth.holdings h join wealth.schemes s using (scheme_id)
group by 1,2,5 order by clients desc limit 15;""",
    "AMC concentration (top word of scheme name)": """
select split_part(s.display_name,' ',1) as amc, round(sum(h.market_value)/1e7,1) as mv_cr,
       count(distinct h.client_id) as clients
from wealth.holdings h join wealth.schemes s using (scheme_id)
group by 1 order by 2 desc limit 12;""",
    "Category duplication (clients holding 3+ funds of same sub-category)": """
with dup as (
  select h.client_id, s.sub_category, count(distinct h.scheme_id) n, sum(h.market_value) mv
  from wealth.holdings h join wealth.schemes s using (scheme_id)
  group by 1,2 having count(distinct h.scheme_id) >= 3)
select count(distinct client_id) as clients_with_dup, count(*) as dup_pairs,
       round(sum(mv)/1e7,1) as mv_cr from dup;""",
    "Dead/segregated holdings": """
select count(*) as na_lines, count(distinct client_id) as clients_affected,
       round(sum(balance_units)::numeric,0) as units
from wealth.holdings where market_value is null;""",
    "Atlas evaluability per client (equity sleeve)": """
with per as (
  select h.client_id,
         sum(h.market_value) filter (where s.asset_class='Equity') as eq_mv,
         sum(h.market_value) filter (where s.in_atlas_universe) as scored_mv
  from wealth.holdings h join wealth.schemes s using (scheme_id)
  where h.market_value is not null group by 1)
select count(*) filter (where scored_mv/nullif(eq_mv,0) >= 0.8) as ge80pct,
       count(*) filter (where scored_mv/nullif(eq_mv,0) >= 0.5 and scored_mv/nullif(eq_mv,0) < 0.8) as p50_80,
       count(*) filter (where scored_mv/nullif(eq_mv,0) < 0.5) as below50,
       count(*) filter (where eq_mv is null or eq_mv = 0) as no_equity
from per;""",
    "Weighted Atlas composite per client (equity sleeve, latest scores)": """
with latest as (select max(date) d from atlas_foundation.fund_rank_daily),
per as (
  select h.client_id,
         sum(h.market_value * fr.composite) / nullif(sum(h.market_value) filter (where fr.composite is not null),0) as wcomp,
         sum(h.market_value) filter (where fr.cat_rank::float/nullif(fr.cat_size,0) > 0.75) as laggard_mv,
         sum(h.market_value) filter (where fr.composite is not null) as scored_mv
  from wealth.holdings h
  join wealth.schemes s using (scheme_id)
  left join atlas_foundation.fund_rank_daily fr
    on fr.mstar_id = s.mstar_id and fr.date = (select d from latest)
  where h.market_value is not null and s.asset_class='Equity'
  group by 1)
select count(*) filter (where wcomp is not null) as clients_scored,
       round(percentile_cont(0.5) within group (order by wcomp)::numeric,1) as median_wcomp,
       round(min(wcomp)::numeric,1) as min_wcomp, round(max(wcomp)::numeric,1) as max_wcomp,
       count(*) filter (where laggard_mv/nullif(scored_mv,0) > 0.30) as clients_gt30pct_in_laggards,
       round((sum(laggard_mv)/nullif(sum(scored_mv),0)*100)::numeric,1) as cohort_laggard_pct
from per;""",
    "Tax status of holdings (LTCG-free swap capacity)": """
select count(*) filter (where inv_days > 365) as lt_lines,
       count(*) filter (where inv_days <= 365) as st_lines,
       round(sum(market_value) filter (where inv_days > 365)/1e7,1) as lt_mv_cr,
       round(100.0*sum(market_value) filter (where inv_days > 365)/sum(market_value),1) as lt_pct
from wealth.holdings where market_value is not null;""",
    "Swap dry-run: single best swap per client (worst scored fund -> top category fund)": """
with latest as (select max(date) d from atlas_foundation.fund_rank_daily),
scored as (
  select h.client_id, h.holding_id, h.market_value, h.inv_days, s.display_name,
         fr.composite, fr.category, fr.cat_rank, fr.cat_size,
         h.market_value / sum(h.market_value) over (partition by h.client_id) as w
  from wealth.holdings h
  join wealth.schemes s using (scheme_id)
  join atlas_foundation.fund_rank_daily fr on fr.mstar_id = s.mstar_id and fr.date = (select d from latest)
  where h.market_value is not null),
best_cat as (
  select category, max(composite) as best_comp from atlas_foundation.fund_rank_daily
  where date = (select d from latest) group by 1),
cand as (
  select sc.*, bc.best_comp, (bc.best_comp - sc.composite) * sc.w as delta,
         row_number() over (partition by sc.client_id order by (bc.best_comp - sc.composite) * sc.w desc) as rn
  from scored sc join best_cat bc using (category)
  where sc.cat_rank::float/nullif(sc.cat_size,0) > 0.5 and sc.inv_days > 365)
select count(*) as clients_with_ltcg_free_swap,
       round(avg(delta)::numeric,1) as avg_wcomp_gain_1swap,
       round(percentile_cont(0.5) within group (order by delta)::numeric,1) as median_gain
from cand where rn = 1;""",
}


def main() -> None:
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    for title, sql in Q.items():
        cur.execute(sql)
        cols = [d[0] for d in cur.description or []]
        print(f"\n## {title}")
        print(" | ".join(cols))
        for row in cur.fetchall():
            print(" | ".join(str(v) for v in row))
    conn.close()


if __name__ == "__main__":
    main()
