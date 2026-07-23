"""Build wealth.client_scorecard — outcome-anchored per-client evaluation (v1).

Philosophy (FM directive): a client compounding at 14-15%+ XIRR is doing well —
the engine must recognize that BEFORE recommending anything. Recommendations
require an evidence gate (weak outcome, heavy laggards, or hygiene flags), and
every candidate move must quantify expected incremental value vs friction.

Outputs one row per client: outcome grade + forward quality + look-through
concentration + hygiene + the recommendation gate with reasons.

Usage:
    .venv/bin/python scripts/wealth/build_scorecard.py
"""

from __future__ import annotations

import os

import psycopg2

SQL = """
drop table if exists wealth.client_scorecard;
create table wealth.client_scorecard as
with latest_rank as (select max(date) as d from atlas_foundation.fund_rank_daily),
r as (select * from wealth.client_reports),
-- forward quality over the Atlas-scored equity sleeve
qual as (
  select h.client_id,
         sum(h.market_value * fr.composite)
           / nullif(sum(h.market_value) filter (where fr.composite is not null), 0) as wcomp,
         sum(h.market_value) filter (where fr.cat_rank::float / nullif(fr.cat_size,0) > 0.75)
           / nullif(sum(h.market_value) filter (where fr.composite is not null), 0) as laggard_share,
         sum(h.market_value) filter (where fr.composite is not null)
           / nullif(sum(h.market_value) filter (where s.asset_class = 'Equity'), 0) as scored_coverage
  from wealth.holdings h
  join wealth.schemes s using (scheme_id)
  left join atlas_foundation.fund_rank_daily fr
         on fr.mstar_id = s.mstar_id and fr.date = (select d from latest_rank)
  where h.market_value is not null
  group by 1),
-- look-through stock concentration
lk as (
  select client_id,
         sum(exposure) as lt_total,
         sum(exposure) filter (where bucket = 'atlas_scored_stock') as lt_scored
  from wealth.client_stock_exposure group by 1),
top10 as (
  select client_id, sum(exposure) as top10_exp from (
    select client_id, exposure,
           row_number() over (partition by client_id order by stock_exp desc) as rn
    from (select client_id, instrument_id, sum(exposure) as stock_exp,
                 sum(sum(exposure)) over (partition by client_id, instrument_id) as exposure
          from wealth.client_stock_exposure
          where bucket like '%stock%' and instrument_id is not null
          group by 1, 2) x) y
  where rn <= 10 group by 1),
fin as (
  select cse.client_id,
         sum(cse.exposure) filter (where im.sector ilike '%financ%' or im.sector ilike '%bank%') as fin_exp,
         sum(cse.exposure) filter (where cse.bucket like '%stock%') as stock_exp
  from wealth.client_stock_exposure cse
  left join atlas_foundation.instrument_master im using (instrument_id)
  group by 1),
hyg as (
  select h.client_id,
         count(*) filter (where h.port_weight_pct < 1 and h.market_value is not null) as dust_lines,
         count(*) filter (where h.market_value is null) as side_pockets,
         count(*) as n_lines
  from wealth.holdings h group by 1),
dup as (
  select client_id, count(*) as dup_cats from (
    select h.client_id, s.sub_category
    from wealth.holdings h join wealth.schemes s using (scheme_id)
    group by 1, 2 having count(distinct h.scheme_id) >= 3) d
  group by 1)
select c.client_id, c.full_name, c.family_group,
       r.mv_total, r.overall_xirr_pct as xirr,
       round(100.0 * r.mv_equity / nullif(r.mv_total, 0), 1) as equity_pct,
       round(q.wcomp::numeric, 1) as wcomp,
       round(100 * q.laggard_share::numeric, 1) as laggard_pct,
       round(100 * q.scored_coverage::numeric, 1) as scored_coverage_pct,
       round((100 * t.top10_exp / nullif(l.lt_total, 0))::numeric, 1) as top10_stock_pct,
       round((100 * f.fin_exp / nullif(f.stock_exp, 0))::numeric, 1) as financials_pct,
       hy.n_lines, hy.dust_lines, hy.side_pockets,
       coalesce(d.dup_cats, 0) as dup_cats,
       case when r.overall_xirr_pct >= 15 then 'A'
            when r.overall_xirr_pct >= 12 then 'B'
            when r.overall_xirr_pct >= 8  then 'C'
            else 'D' end as outcome_grade,
       (r.overall_xirr_pct < 12
        or coalesce(q.laggard_share, 0) > 0.30
        or coalesce(d.dup_cats, 0) >= 2
        or hy.side_pockets > 0) as needs_attention,
       concat_ws('; ',
         case when r.overall_xirr_pct < 12 then 'outcome below 12% XIRR' end,
         case when coalesce(q.laggard_share, 0) > 0.30
              then round(100 * q.laggard_share)::text || '% of scored equity in bottom-quartile funds' end,
         case when coalesce(d.dup_cats, 0) >= 2
              then d.dup_cats::text || ' sub-categories held 3+ times' end,
         case when hy.side_pockets > 0 then 'dead side-pocket units' end
       ) as attention_reasons
from wealth.clients c
join r on r.client_id = c.client_id
left join qual q on q.client_id = c.client_id
left join lk l on l.client_id = c.client_id
left join top10 t on t.client_id = c.client_id
left join fin f on f.client_id = c.client_id
left join hyg hy on hy.client_id = c.client_id
left join dup d on d.client_id = c.client_id;
revoke all on wealth.client_scorecard from anon, authenticated;
"""

REPORT = """
select outcome_grade, count(*) as clients,
       round(avg(wcomp), 1) as avg_wcomp, round(avg(laggard_pct), 1) as avg_laggard_pct,
       count(*) filter (where needs_attention) as needing_attention,
       round(sum(mv_total) / 1e7, 1) as aum_cr
from wealth.client_scorecard group by 1 order by 1;
"""


def main() -> None:
    dsn = os.environ["ATLAS_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(SQL)
    conn.commit()
    cur.execute("select count(*) from wealth.client_scorecard")
    row = cur.fetchone()
    assert row is not None
    print(f"scorecard rows: {row[0]}")
    cur.execute(REPORT)
    print("grade | clients | avg_wcomp | avg_laggard% | needing_attention | aum_cr")
    for r in cur.fetchall():
        print(" | ".join(str(v) for v in r))
    conn.close()


if __name__ == "__main__":
    main()
