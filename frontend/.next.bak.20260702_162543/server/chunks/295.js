"use strict";exports.id=295,exports.ids=[295],exports.modules={31733:(t,e,a)=>{a.d(e,{sl:()=>d,s0:()=>c,TB:()=>m,W7:()=>i,ih:()=>l});var n=a(5069);let r=t=>null!=t.revenue&&t.revenue>0;function _(t,e){let a=0,n=0;for(let r of t){let t=e(r);null==t||null==r.revenue||r.revenue<=0||(a+=t,n+=r.revenue)}return 0===n?null:100*a/n}function s(t){let e=t.filter(r);if(0===e.length)return{n:0,ebitda_margin:null,net_margin:null,pct_profitable:null};let a=e.filter(t=>null!=t.pat),n=0===a.length?null:100*a.filter(t=>t.pat>0).length/a.length;return{n:e.length,ebitda_margin:_(e,t=>t.ebitda),net_margin:_(e,t=>t.pat),pct_profitable:n}}let o=(t,e)=>null==t||null==e||e<=0?null:100*t/e;async function i(t){let e=await (0,n.A)`
    SELECT technical, fundamental, valuation, catalyst, flow, policy,
           breadth_technical, breadth_fundamental, breadth_flow, dispersion, n_constituents
    FROM atlas_foundation.sector_lens_daily
    WHERE sector = ${t} ORDER BY date DESC LIMIT 1
  `;if(0===e.length)return null;let a=t=>null==t?null:Number(t),r=e[0];return{technical:a(r.technical),fundamental:a(r.fundamental),valuation:a(r.valuation),catalyst:a(r.catalyst),flow:a(r.flow),policy:a(r.policy),breadth_technical:a(r.breadth_technical),breadth_fundamental:a(r.breadth_fundamental),breadth_flow:a(r.breadth_flow),dispersion:a(r.dispersion),n_constituents:null==r.n_constituents?null:Number(r.n_constituents)}}async function d(){let t=await (0,n.A)`
    SELECT sector, technical, fundamental, valuation, catalyst, flow, policy,
           breadth_technical, breadth_fundamental, breadth_flow, dispersion, n_constituents
    FROM atlas_foundation.sector_lens_daily
    WHERE date = (SELECT max(date) FROM atlas_foundation.sector_lens_daily)
  `,e=t=>null==t?null:Number(t),a={};for(let n of t)a[n.sector]={technical:e(n.technical),fundamental:e(n.fundamental),valuation:e(n.valuation),catalyst:e(n.catalyst),flow:e(n.flow),policy:e(n.policy),breadth_technical:e(n.breadth_technical),breadth_fundamental:e(n.breadth_fundamental),breadth_flow:e(n.breadth_flow),dispersion:e(n.dispersion),n_constituents:null==n.n_constituents?null:Number(n.n_constituents)};return a}async function l(t){let e=await (0,n.A)`
    WITH latest AS (
      SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'
    ),
    cap AS (
      SELECT instrument_id,
        CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
             WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
             WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
      FROM atlas_foundation.de_index_constituents
      WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
      GROUP BY instrument_id
    ),
    liq AS (  -- ≈20-session avg traded value (₹ Cr)
      SELECT instrument_id, avg(close * volume) / 1e7 AS liq_cr
      FROM atlas_foundation.ohlcv_stock
      WHERE date >= (SELECT d FROM latest) - INTERVAL '30 days' AND close > 0 AND volume > 0
      GROUP BY instrument_id
    ),
    j AS (
      SELECT l.instrument_id, im.symbol, im.name, im.sector, COALESCE(c.cap,'micro') AS cap,
             l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va,
             l.composite::float comp,
             td.ret_1d::float r1d, td.ret_1w::float r1w, td.ret_1m::float r1m,
             td.ret_3m::float r3m, td.ret_6m::float r6m, td.ret_12m::float r12m,
             td.rs_1m_n500::float rs1m, td.rs_3m_n500::float rs3m, td.rs_6m_n500::float rs6m,
             td.rs_3m_sector::float rs_sec3m  -- canonical stored RS-vs-sector (read, never recompute)
      FROM atlas_foundation.atlas_lens_scores_daily l
      JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      LEFT JOIN atlas_foundation.technical_daily td
        ON td.instrument_id = l.instrument_id AND td.asset_class='stock'
        AND td.date = (SELECT d FROM latest)
      WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)
    ),
    dec AS (
      SELECT instrument_id, symbol, name, sector, cap, t, f, ca, fl, va, comp, r1d, r1w, r1m, r3m, r6m, r12m, rs1m, rs3m, rs6m, rs_sec3m,
        CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_tech,
        CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fund,
        CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_cat,
        CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
        CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_val,
        CASE WHEN comp IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(comp IS NULL) ORDER BY comp) END d_composite
      FROM j
    ),
    ff AS (  -- free-float market cap = market cap × non-promoter, non-ESOP share (concentration view).
             -- Shareholding required (INNER) so no name gets a fabricated 100%-free-float weight.
             -- (equity_marketcap union was tried + verified a no-op for the scored universe — the
             -- uncovered names lack market cap in EVERY source, not just screener_ratios.)
      SELECT mc.instrument_id,
        mc.market_cap * (100 - sh.promoter_pct - COALESCE(sh.employee_trusts_pct,0)) / 100.0 AS ff_mcap
      FROM (SELECT DISTINCT ON (instrument_id) instrument_id, market_cap FROM atlas_foundation.screener_ratios
            WHERE market_cap IS NOT NULL ORDER BY instrument_id, as_of DESC NULLS LAST) mc
      JOIN (SELECT DISTINCT ON (instrument_id) instrument_id, promoter_pct, employee_trusts_pct
            FROM atlas_foundation.lens_shareholding WHERE promoter_pct IS NOT NULL
            ORDER BY instrument_id, period_end DESC) sh ON sh.instrument_id = mc.instrument_id
    )
    SELECT d.symbol, d.name, d.cap, d.d_tech, d.d_fund, d.d_cat, d.d_flow, d.d_val,
      d.r1d, d.r1w, d.r1m, d.r3m, d.r6m, d.r12m, d.rs1m, d.rs3m, d.rs6m,
      d.rs_sec3m AS rs_sector_3m, liq.liq_cr,
      (COALESCE((d.d_composite>=10)::int,0)) AS lead,  -- LEADER = top decile (D10) of composite within cap cohort (one rule; 0/1)
      ((COALESCE(d.d_tech,0)+COALESCE(d.d_flow,0))::float
        / NULLIF((d.d_tech IS NOT NULL)::int+(d.d_flow IS NOT NULL)::int,0)) AS strength,
      -- free-float weight WITHIN this sector: the window runs after the sector WHERE, so it sums the sector only
      round((100.0 * ff.ff_mcap / NULLIF(sum(ff.ff_mcap) OVER (), 0))::numeric, 2) AS ff_weight
    FROM dec d
    LEFT JOIN liq ON liq.instrument_id = d.instrument_id
    LEFT JOIN ff ON ff.instrument_id = d.instrument_id
    WHERE d.sector = ${t}
    ORDER BY strength DESC NULLS LAST
  `,a=t=>null==t?null:Number(t);return e.map(t=>({symbol:t.symbol,name:t.name,cap:t.cap,d_tech:a(t.d_tech),d_fund:a(t.d_fund),d_cat:a(t.d_cat),d_flow:a(t.d_flow),d_val:a(t.d_val),lead:Number(t.lead??0),strength:a(t.strength),ret_1d:a(t.r1d),ret_1w:a(t.r1w),ret_1m:a(t.r1m),ret_3m:a(t.r3m),ret_6m:a(t.r6m),ret_12m:a(t.r12m),rs_1m:a(t.rs1m),rs_3m:a(t.rs3m),rs_6m:a(t.rs6m),rs_sector_3m:a(t.rs_sector_3m),liq_cr:a(t.liq_cr),ff_weight:a(t.ff_weight)}))}async function m(t){let e=await (0,n.A)`
    WITH ld AS (SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'),
    scored AS (SELECT instrument_id FROM atlas_foundation.atlas_lens_scores_daily
               WHERE asset_class='stock' AND date=(SELECT d FROM ld)),
    latest_fin AS (
      SELECT DISTINCT ON (fq.instrument_id) fq.instrument_id,
             fq.ebitda::float ebitda, fq.revenue::float revenue, fq.pat::float pat
      FROM atlas_foundation.financials_quarterly fq
      WHERE fq.consolidated ORDER BY fq.instrument_id, fq.period_end DESC
    )
    SELECT im.symbol, im.sector, lf.ebitda, lf.revenue, lf.pat
    FROM atlas_foundation.instrument_master im
    JOIN scored sc ON sc.instrument_id = im.instrument_id
    JOIN latest_fin lf ON lf.instrument_id = im.instrument_id
    WHERE im.asset_class='stock' AND im.sector IS NOT NULL
  `,a=t=>null==t?null:Number(t),_=e.map(t=>({symbol:t.symbol,ebitda:a(t.ebitda),revenue:a(t.revenue),pat:a(t.pat)})),i=e.filter(e=>e.sector===t).map(t=>({symbol:t.symbol,ebitda:a(t.ebitda),revenue:a(t.revenue),pat:a(t.pat)})),d=s(i);if(0===d.n)return null;let l=s(_);return{n:d.n,ebitda_margin:d.ebitda_margin,net_margin:d.net_margin,pct_profitable:d.pct_profitable,u_ebitda_margin:l.ebitda_margin,u_net_margin:l.net_margin,u_pct_profitable:l.pct_profitable,constituents:i.map(t=>({symbol:t.symbol,ebitda_margin:o(t.ebitda,t.revenue),net_margin:o(t.pat,t.revenue),profitable:null!=t.pat&&r(t)?t.pat>0:null})).sort((t,e)=>(e.ebitda_margin??-1/0)-(t.ebitda_margin??-1/0))}}async function c(t){let e=await (0,n.A)`
    WITH dl AS (SELECT max(date) d FROM atlas_foundation.delivery_daily),
    jl AS (SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'),
    scored AS (SELECT instrument_id, flow_institutional FROM atlas_foundation.atlas_lens_scores_daily
               WHERE asset_class='stock' AND date=(SELECT d FROM jl))
    SELECT im.symbol, im.sector, d.delivery_avg_30d::float a30, d.delivery_avg_60d::float a60,
           d.delivery_updown_asym::float ud, sc.flow_institutional::float fi
    FROM atlas_foundation.instrument_master im
    JOIN scored sc ON sc.instrument_id = im.instrument_id
    LEFT JOIN atlas_foundation.delivery_daily d ON d.instrument_id = im.instrument_id AND d.date=(SELECT d FROM dl)
    WHERE im.asset_class='stock' AND im.sector IS NOT NULL
  `,a=t=>null==t?null:Number(t),r=t=>{let e=t.filter(t=>null!=t);return e.length?e.reduce((t,e)=>t+e,0)/e.length:null},_=e.filter(e=>e.sector===t);if(0===_.length)return null;let s=(t,e)=>r(t.map(t=>a(t[e]))),o=_.map(t=>({symbol:t.symbol,deliv_30d:a(t.a30),deliv_60d:a(t.a60),updown:a(t.ud),flow_inst:a(t.fi)})).sort((t,e)=>(e.deliv_30d??-1/0)-(t.deliv_30d??-1/0));return{n:_.length,deliv_30d:s(_,"a30"),deliv_60d:s(_,"a60"),updown:s(_,"ud"),flow_inst:s(_,"fi"),u_deliv_30d:s(e,"a30"),u_deliv_60d:s(e,"a60"),u_updown:s(e,"ud"),u_flow_inst:s(e,"fi"),constituents:o}}},56822:(t,e,a)=>{a.d(e,{Ko:()=>_,Wi:()=>i,Z4:()=>l,_p:()=>d,af:()=>o,ru:()=>s});var n=a(5069),r=a(6707);async function _(){return(await (0,n.A)`
    SELECT
      as_of_date::text,
      sector_name,
      constituent_count,
      ret_1w::text,
      ret_1m::text,
      ret_3m::text,
      ret_6m::text,
      ret_12m::text,
      rs_1m::text,
      rs_3m::text,
      rs_6m::text,
      vol_60d_ann::text,
      pct_above_ema21::text,
      pct_above_ema200::text,
      pct_at_52wh::text,
      hhi_concentration::text,
      buy_signal_count,
      confidence_distribution,
      verdict,
      verdict_abbr
    FROM atlas_foundation.mv_sector_cards
    WHERE as_of_date = (
      -- Anchor to last fully-populated date. On a fresh trading day,
      -- rs_1m / ret_1w / ret_12m / breadth columns can lag rs_3m by one
      -- compute cycle. Picking MAX(as_of_date) blindly gives a partial row
      -- with empty 1W / 12M / breadth columns. Filter on rs_1m IS NOT NULL.
      SELECT MAX(as_of_date) FROM atlas_foundation.mv_sector_cards
      WHERE rs_1m IS NOT NULL AND ret_1w IS NOT NULL
    )
      AND LOWER(sector_name) NOT LIKE '%conglomerate%'
    ORDER BY rs_3m DESC NULLS LAST
  `).map(t=>({as_of_date:t.as_of_date,sector_name:t.sector_name,constituent_count:t.constituent_count,ret_1w:(0,r.Ro)(t.ret_1w),ret_1m:(0,r.Ro)(t.ret_1m),ret_3m:(0,r.Ro)(t.ret_3m),ret_6m:(0,r.Ro)(t.ret_6m),ret_12m:(0,r.Ro)(t.ret_12m),rs_1m:(0,r.Ro)(t.rs_1m),rs_3m:(0,r.Ro)(t.rs_3m),rs_6m:(0,r.Ro)(t.rs_6m),vol_60d_ann:(0,r.Ro)(t.vol_60d_ann),pct_above_ema21:(0,r.Ro)(t.pct_above_ema21),pct_above_ema200:(0,r.Ro)(t.pct_above_ema200),pct_at_52wh:(0,r.Ro)(t.pct_at_52wh),hhi_concentration:(0,r.Ro)(t.hhi_concentration),buy_signal_count:t.buy_signal_count,confidence_distribution:t.confidence_distribution,verdict:t.verdict,verdict_abbr:t.verdict_abbr}))}async function s(){let t=await (0,n.A)`
    WITH latest AS (
      SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'
    ),
    ff AS (  -- free-float market cap = market cap × non-promoter, non-ESOP share (sector concentration).
             -- Shareholding required (INNER) so no name gets a fabricated 100%-free-float weight.
      SELECT mc.instrument_id,
        mc.market_cap * (100 - sh.promoter_pct - COALESCE(sh.employee_trusts_pct,0)) / 100.0 AS ff_mcap
      FROM (SELECT DISTINCT ON (instrument_id) instrument_id, market_cap FROM atlas_foundation.screener_ratios
            WHERE market_cap IS NOT NULL ORDER BY instrument_id, as_of DESC NULLS LAST) mc
      JOIN (SELECT DISTINCT ON (instrument_id) instrument_id, promoter_pct, employee_trusts_pct
            FROM atlas_foundation.lens_shareholding WHERE promoter_pct IS NOT NULL
            ORDER BY instrument_id, period_end DESC) sh ON sh.instrument_id = mc.instrument_id
    )
    SELECT im.sector, im.symbol, im.name,
           td.ret_1d::float r1d, td.ret_1w::float r1w, td.ret_1m::float r1m,
           td.ret_3m::float r3m, td.ret_6m::float r6m, td.ret_12m::float r12m,
           round((100.0 * ff.ff_mcap / NULLIF(sum(ff.ff_mcap) OVER (PARTITION BY im.sector), 0))::numeric, 2) AS ff_weight
    FROM atlas_foundation.atlas_lens_scores_daily l
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
    LEFT JOIN atlas_foundation.technical_daily td
      ON td.instrument_id = l.instrument_id AND td.asset_class='stock' AND td.date=(SELECT d FROM latest)
    LEFT JOIN ff ON ff.instrument_id = l.instrument_id
    WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest) AND im.sector IS NOT NULL
    ORDER BY im.sector, ff_weight DESC NULLS LAST
  `,e={};for(let a of t)(e[a.sector]??=[]).push({sector:a.sector,symbol:a.symbol,name:a.name,ret_1d:(0,r.Ro)(a.r1d),ret_1w:(0,r.Ro)(a.r1w),ret_1m:(0,r.Ro)(a.r1m),ret_3m:(0,r.Ro)(a.r3m),ret_6m:(0,r.Ro)(a.r6m),ret_12m:(0,r.Ro)(a.r12m),ff_weight:(0,r.Ro)(a.ff_weight)});return e}async function o(t){return(await (0,n.A)`
    SELECT
      as_of_date::text,
      sector_name,
      constituent_count,
      pct_above_ema21::text,
      pct_above_ema50::text,
      pct_above_ema200::text,
      pct_at_52wh::text,
      breadth_by_window,
      breadth_by_strength,
      top_movers,
      bottom_movers
    FROM atlas_foundation.mv_sector_breadth
    WHERE as_of_date = (
      SELECT MAX(as_of_date) FROM atlas_foundation.mv_sector_breadth
    )
    ${null!=t?(0,n.A)`AND sector_name = ${t}`:(0,n.A)``}
    ORDER BY sector_name
  `).map(t=>({as_of_date:t.as_of_date,sector_name:t.sector_name,constituent_count:t.constituent_count,pct_above_ema21:(0,r.Ro)(t.pct_above_ema21),pct_above_ema50:(0,r.Ro)(t.pct_above_ema50),pct_above_ema200:(0,r.Ro)(t.pct_above_ema200),pct_at_52wh:(0,r.Ro)(t.pct_at_52wh),breadth_by_window:t.breadth_by_window??[],breadth_by_strength:t.breadth_by_strength??null,top_movers:t.top_movers??[],bottom_movers:t.bottom_movers??[]}))}async function i(){return(await (0,n.A)`
    WITH anchors AS (
      SELECT
        MAX(date) FILTER (WHERE rn = 1)  AS d_now,
        MAX(date) FILTER (WHERE rn = 6)  AS d_1w,
        MAX(date) FILTER (WHERE rn = 22) AS d_1m
      FROM (
        SELECT date, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
        FROM (
          SELECT DISTINCT date
          FROM atlas_foundation.technical_daily
          WHERE asset_class = 'stock'
          ORDER BY date DESC
          LIMIT 22
        ) z
      ) r
    )
    SELECT
      im.sector AS sector_name,
      AVG(CASE WHEN td.date = a.d_now THEN td.above_ema_21::int END)::text AS ema21_now,
      AVG(CASE WHEN td.date = a.d_1w  THEN td.above_ema_21::int END)::text AS ema21_1w,
      AVG(CASE WHEN td.date = a.d_1m  THEN td.above_ema_21::int END)::text AS ema21_1m
    FROM atlas_foundation.technical_daily td
    JOIN atlas_foundation.instrument_master im
      ON im.instrument_id = td.instrument_id
    CROSS JOIN anchors a
    WHERE td.asset_class = 'stock'
      AND im.sector IS NOT NULL
      AND td.date IN (a.d_now, a.d_1w, a.d_1m)
    GROUP BY im.sector
    ORDER BY im.sector
  `).map(t=>({sector_name:t.sector_name,ema21_now:(0,r.Ro)(t.ema21_now),ema21_1w:(0,r.Ro)(t.ema21_1w),ema21_1m:(0,r.Ro)(t.ema21_1m)}))}async function d(){return(await (0,n.A)`
    SELECT
      r.as_of_date::text,
      r.sector_name,
      r.rs_ratio_current::text,
      r.rs_momentum_current::text,
      r.quadrant_current,
      r.trail_6w,
      COALESCE(c.constituent_count, 0) AS constituent_count
    FROM atlas_foundation.mv_sector_rrg r
    LEFT JOIN atlas_foundation.mv_sector_cards c
      ON c.sector_name = r.sector_name
     AND c.as_of_date = r.as_of_date
    WHERE r.as_of_date = (
      SELECT MAX(as_of_date) FROM atlas_foundation.mv_sector_rrg
    )
    ORDER BY r.sector_name
  `).map(t=>({as_of_date:t.as_of_date,sector_name:t.sector_name,rs_ratio_current:(0,r.Ro)(t.rs_ratio_current),rs_momentum_current:(0,r.Ro)(t.rs_momentum_current),quadrant_current:t.quadrant_current,trail_6w:t.trail_6w??[],constituent_count:t.constituent_count}))}async function l(t){let e=await (0,n.A)`
    SELECT
      sector_name,
      verdict,
      constituent_count,
      data_as_of::text,
      returns,
      rs_windows,
      pct_above_ema21::text,
      pct_above_ema200::text,
      pct_at_52wh::text,
      constituents_top30,
      open_signals,
      strength_dist,
      top_picks_top10
    FROM atlas_foundation.mv_sector_deepdive
    WHERE sector_name = ${t}
    LIMIT 1
  `;if(0===e.length)return null;let a=e[0];return{sector_name:a.sector_name,verdict:a.verdict,constituent_count:a.constituent_count,data_as_of:a.data_as_of,returns:a.returns,rs_windows:a.rs_windows,pct_above_ema21:(0,r.Ro)(a.pct_above_ema21),pct_above_ema200:(0,r.Ro)(a.pct_above_ema200),pct_at_52wh:(0,r.Ro)(a.pct_at_52wh),constituents_top30:a.constituents_top30??[],open_signals:a.open_signals??[],strength_dist:a.strength_dist??{very_strong:0,strong:0,neutral:0,weak:0,very_weak:0},top_picks_top10:a.top_picks_top10??[],sub_industries:[]}}},64868:(t,e,a)=>{a.d(e,{E:()=>o,x:()=>i});var n=a(5069),r=a(6707);let _={ret_1d:null,ret_1w:null,ret_1m:null,ret_3m:null,ret_6m:null,ret_12m:null};function s(t){return{ret_1d:(0,r.Ro)(t.ret_1d),ret_1w:(0,r.Ro)(t.ret_1w),ret_1m:(0,r.Ro)(t.ret_1m),ret_3m:(0,r.Ro)(t.ret_3m),ret_6m:(0,r.Ro)(t.ret_6m),ret_12m:(0,r.Ro)(t.ret_12m)}}async function o(){let t=await (0,n.A)`
    SELECT
      im.index_code,
      sm.sector_name,
      im.ret_1d::text,
      im.ret_1w::text,
      im.ret_1m::text,
      im.ret_3m::text,
      im.ret_6m::text,
      im.ret_12m::text,
      im.date::text
    FROM atlas_foundation.atlas_index_metrics_daily im
    LEFT JOIN atlas_foundation.atlas_sector_master sm
      ON sm.primary_nse_index = im.index_code
     AND sm.is_active = true
     AND LOWER(sm.sector_name) NOT LIKE '%conglomerate%'
    WHERE im.date = (SELECT MAX(date) FROM atlas_foundation.atlas_index_metrics_daily)
      AND (sm.sector_name IS NOT NULL OR im.index_code IN ('NIFTY 50', 'NIFTY 500'))
    ORDER BY sm.sector_name NULLS LAST
  `,e=new Map(t.filter(t=>"NIFTY 50"===t.index_code||"NIFTY 500"===t.index_code).map(t=>[t.index_code,s(t)]));return{sectors:t.filter(t=>null!=t.sector_name).map(t=>({sector_name:t.sector_name,nse_index_code:t.index_code,ret:s(t)})),bases:{"NIFTY 50":e.get("NIFTY 50")??_,"NIFTY 500":e.get("NIFTY 500")??_},as_of:t[0]?.date??null}}async function i(t){let e=await (0,n.A)`
    SELECT s.date::text AS date, s.index_code, (s.close / n.close)::text AS ratio
    FROM atlas_foundation.index_prices s
    JOIN atlas_foundation.index_prices n
      ON n.date = s.date AND n.index_code = 'NIFTY 50'
    WHERE s.index_code = (
      SELECT primary_nse_index FROM atlas_foundation.atlas_sector_master
      WHERE sector_name = ${t} AND is_active = true
      LIMIT 1
    )
      AND n.close > 0
      AND s.close > 0
    ORDER BY s.date
  `;return{sector_name:t,index_code:e[0]?.index_code??null,daily:e.map(t=>({time:t.date,value:(0,r.Ro)(t.ratio)})).filter(t=>null!=t.value&&Number.isFinite(t.value))}}},85427:(t,e,a)=>{a.d(e,{k:()=>_});var n=a(37413);let r={timeZone:"Asia/Kolkata"};function _({source:t="live",asOf:e,hint:a}){let _="live"===t,s=/^\d{4}-\d{2}-\d{2}$/.test(e)?`snapshot ${e}`:`Data as of ${function(t,e=!1){let a="string"==typeof t?new Date(t):t,n=new Intl.DateTimeFormat("en-IN",{...r,day:"2-digit"}).format(a),_=new Intl.DateTimeFormat("en-IN",{...r,month:"short"}).format(a),s=new Intl.DateTimeFormat("en-IN",{...r,year:"numeric"}).format(a);if(!e)return`${n}-${_}-${s}`;let o=new Intl.DateTimeFormat("en-IN",{...r,hour:"2-digit",minute:"2-digit",hour12:!1}).format(a);return`${n}-${_}-${s} ${o} IST`}(e)}`;return(0,n.jsxs)("div",{className:"px-6 py-1.5 border-b border-paper-rule/60 flex items-center gap-3 bg-paper",children:[(0,n.jsxs)("span",{className:"inline-flex items-center gap-1.5 font-sans text-[10px] uppercase tracking-wider text-ink-tertiary",children:[(0,n.jsx)("span",{className:`inline-block w-1.5 h-1.5 rounded-full ${_?"bg-signal-pos":"bg-signal-warn"}`}),(0,n.jsx)("span",{className:"text-ink-secondary",children:_?"Live Supabase":"Demo data"})]}),(0,n.jsx)("span",{className:"font-sans text-[10px] text-ink-tertiary",children:s}),a&&(0,n.jsx)("span",{className:"font-sans text-[10px] text-ink-tertiary ml-auto",children:a})]})}}};