"use strict";exports.id=763,exports.ids=[763],exports.modules={32936:(t,e,a)=>{a.d(e,{h:()=>o});var n=a(37413),s=a(4536),l=a.n(s);let i={pos:"var(--color-sig-pos)",neg:"var(--color-sig-neg)",warn:"var(--color-sig-warn)",neutral:"var(--color-txt-1)",brand:"var(--color-brand)"};function o({label:t,value:e,unit:a,sub:s,delta:o,tone:_="neutral",href:r,children:d}){let c=(0,n.jsxs)(n.Fragment,{children:[(0,n.jsxs)("div",{className:"flex items-center justify-between gap-2",children:[(0,n.jsx)("span",{className:"font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:t}),r&&(0,n.jsx)("span",{className:"font-num text-[12px] text-txt-3 transition-colors group-hover/stat:text-brand",children:"→"})]}),(0,n.jsxs)("div",{className:"mt-2 flex items-baseline gap-1",children:[(0,n.jsx)("span",{className:"font-display text-[30px] font-semibold leading-none tracking-tight tabular-nums",style:{color:i[_]},children:e}),a&&(0,n.jsx)("span",{className:"font-num text-[13px] text-txt-2",children:a})]}),d&&(0,n.jsx)("div",{className:"mt-2.5",children:d}),(s||o)&&(0,n.jsxs)("div",{className:"mt-2 flex items-center gap-2",children:[s&&(0,n.jsx)("span",{className:"font-sans text-[11px] text-txt-2",children:s}),o&&(0,n.jsx)("span",{className:"font-num text-[11px] tabular-nums",style:{color:i[o.tone]},children:o.value})]})]}),m="group/stat block rounded-tile border border-edge-hair bg-surface-raised px-4 py-3.5 shadow-tile transition-colors";return r?(0,n.jsx)(l(),{href:r,className:`${m} hover:border-edge-strong hover:bg-surface-raised`,children:c}):(0,n.jsx)("div",{className:m,children:c})}},96742:(t,e,a)=>{a.d(e,{Aw:()=>L,BC:()=>N,E6:()=>f,J4:()=>o,Jt:()=>u,LI:()=>m,Q9:()=>S,W4:()=>_,kL:()=>l,yV:()=>E});var n=a(5069),s=a(6707);let l=9,i=["1d","1w","1m","3m","6m","12m"];async function o(t){let e=await (0,n.A)`
    SELECT to_char(t.date,'YYYY-MM-DD') AS as_of,
           t.rs_1d_n50, t.rs_1w_n50, t.rs_1m_n50, t.rs_3m_n50, t.rs_6m_n50, t.rs_12m_n50,
           t.rs_1d_n500, t.rs_1w_n500, t.rs_1m_n500, t.rs_3m_n500, t.rs_6m_n500, t.rs_12m_n500,
           t.rs_1m_sector, t.rs_3m_sector, t.rs_6m_sector, t.rs_12m_sector
    FROM atlas_foundation.technical_daily t
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = t.instrument_id
    WHERE im.symbol = ${t} AND t.asset_class='stock'
    ORDER BY t.date DESC LIMIT 1
  `;if(0===e.length)return null;let a=e[0],l=t=>{let e=null==t?null:(0,s.Ro)(t);return null==e?null:100*e},o=(t,e)=>e.map(e=>({window:e.toUpperCase(),v:l(a[`rs_${e}_${t}`])}));return{as_of:a.as_of,rows:[{baseline:"Nifty 50",cells:o("n50",i)},{baseline:"Nifty 500",cells:o("n500",i)},{baseline:"Sector",cells:o("sector",["1m","3m","6m","12m"])}]}}async function _(t,e=5){return(0,n.A)`
    SELECT to_char(o.date,'YYYY-MM-DD') AS date, o.close::text,
           (o.close / NULLIF(n50.close, 0))::text  AS rs_n50,
           (o.close / NULLIF(n500.close, 0))::text AS rs_n500
    FROM atlas_foundation.ohlcv_stock o
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = o.instrument_id
    LEFT JOIN atlas_foundation.index_prices n50  ON n50.date = o.date  AND n50.index_code = 'NIFTY 50'
    LEFT JOIN atlas_foundation.index_prices n500 ON n500.date = o.date AND n500.index_code = 'NIFTY 500'
    WHERE im.symbol = ${t} AND o.close > 0
      AND o.date >= NOW() - (${e} || ' years')::INTERVAL
    ORDER BY o.date ASC
  `}let r={technical:[["tech_trend","Trend"],["tech_rs","Rel. strength"],["tech_vol_contraction","Vol contraction"],["tech_volume","Volume"]],fundamental:[["fund_profitability","Profitability"],["fund_margin","Margin"],["fund_growth","Growth"],["fund_balance_sheet","Balance sheet"]],valuation:[["val_pe_vs_sector","PE vs sector"],["val_absolute_pe","Absolute PE"],["val_pb","P/B"],["val_52w_position","52w position"]],catalyst:[["cat_earnings_strategy","Earnings"],["cat_capital_action","Capital action"],["cat_governance","Governance"]],flow:[["flow_promoter","Promoter"],["flow_institutional","Institutional"],["flow_smart_money","Smart money"],["flow_accumulation","Accumulation (delivery)"]],policy:[["policy_tailwind","Sector tailwind"]]},d={technical:"Technical",fundamental:"Fundamental",valuation:"Valuation",catalyst:"Catalyst",flow:"Flow",policy:"Policy"},c=Object.values(r).flat().map(([t])=>t);async function m(t){let e=await (0,n.A)`
    WITH latest AS (SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'),
    cap AS (
      SELECT instrument_id,
        CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
             WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
             WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
      FROM atlas_foundation.de_index_constituents
      WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
      GROUP BY instrument_id
    ),
    j AS (
      SELECT l.*, im.symbol, im.name, im.sector, COALESCE(c.cap,'micro') AS cap,
             l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va
      FROM atlas_foundation.atlas_lens_scores_daily l
      JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)
    ),
    dec AS (
      SELECT *,
        CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_technical,
        CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fundamental,
        CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_catalyst,
        CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
        CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_valuation,
        CASE WHEN composite IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(composite IS NULL) ORDER BY composite) END d_composite
      FROM j
    )
    SELECT symbol, name, sector, cap,
      technical, fundamental, valuation, catalyst, flow, policy,
      composite, conviction_tier,
      d_technical, d_fundamental, d_valuation, d_catalyst, d_flow,
      ${(0,n.A)(c)}, evidence,
      -- LEADER = top decile (D10) of composite within cap cohort (one rule). lead 0/1.
      (COALESCE((d_composite>=10)::int,0)) AS lead,
      ((COALESCE(d_technical,0)+COALESCE(d_flow,0))::float
        / NULLIF((d_technical IS NOT NULL)::int+(d_flow IS NOT NULL)::int,0)) AS strength
    FROM dec WHERE symbol = ${t} LIMIT 1
  `;if(0===e.length)return null;let a=e[0],l=t=>null==t?null:(0,s.Ro)(t),i=Object.keys(r).map(t=>({key:t,label:d[t],score:l(a[t]),decile:l(a[`d_${t}`]),subs:r[t].map(([t,e])=>({label:e,v:l(a[t])}))}));return{symbol:a.symbol,name:a.name,sector:a.sector,cap:a.cap,lens:i,lead:(0,s.oT)(a.lead,0),strength:l(a.strength),composite:l(a.composite),conviction_tier:a.conviction_tier??null,evidence:function(t){if(null==t)return null;if("string"!=typeof t)return t;try{return JSON.parse(t)}catch{return null}}(a.evidence)}}async function E(t){let e=await (0,n.A)`
    WITH im AS (SELECT instrument_id FROM atlas_foundation.instrument_master WHERE symbol = ${t} LIMIT 1),
    td AS (SELECT t.* FROM atlas_foundation.technical_daily t, im
           WHERE t.instrument_id = im.instrument_id AND t.asset_class='stock' ORDER BY t.date DESC LIMIT 1),
    px AS (SELECT o.date, o.close FROM atlas_foundation.ohlcv_stock o, im
           WHERE o.instrument_id = im.instrument_id AND o.close > 0 ORDER BY o.date DESC LIMIT 1),
    vw AS (SELECT sum(close*volume)/NULLIF(sum(volume),0) AS vwap_252
           FROM (SELECT o.close, o.volume FROM atlas_foundation.ohlcv_stock o, im
                 WHERE o.instrument_id = im.instrument_id AND o.close > 0 AND o.volume > 0
                 ORDER BY o.date DESC LIMIT 252) z),
    dl AS (SELECT d.* FROM atlas_foundation.delivery_daily d, im
           WHERE d.instrument_id = im.instrument_id ORDER BY d.date DESC LIMIT 1),
    sh AS (SELECT s.promoter_pct FROM atlas_foundation.lens_shareholding s, im
           WHERE s.instrument_id = im.instrument_id ORDER BY s.period_end DESC LIMIT 1),
    fin AS (SELECT sum(eps) AS eps_ttm FROM (SELECT f.eps FROM atlas_foundation.financials_quarterly f, im
            WHERE f.instrument_id = im.instrument_id AND f.consolidated ORDER BY f.period_end DESC LIMIT 4) q)
    SELECT to_char(px.date,'YYYY-MM-DD') AS as_of, px.close,
      td.ema_21, td.ema_50, td.ema_200, td.rsi_14, td.atr_14, td.bb_width,
      td.vol_ratio_30d, td.vol_ratio_60d, td.pos_52w,
      td.rs_1m_n500, td.rs_3m_n500, td.rs_6m_n500, td.rs_3m_sector,
      (px.close - td.ema_50)  / NULLIF(td.ema_50,0)  * 100 AS dist_ema50,
      (px.close - td.ema_200) / NULLIF(td.ema_200,0) * 100 AS dist_ema200,
      vw.vwap_252, (px.close - vw.vwap_252) / NULLIF(vw.vwap_252,0) * 100 AS vwap_dist,
      dl.delivery_pct, dl.delivery_avg_30d, dl.delivery_avg_60d, dl.delivery_updown_asym,
      sh.promoter_pct, fin.eps_ttm, px.close / NULLIF(fin.eps_ttm,0) AS pe_ttm
    FROM px LEFT JOIN td ON true LEFT JOIN vw ON true LEFT JOIN dl ON true LEFT JOIN sh ON true LEFT JOIN fin ON true`;if(0===e.length)return null;let a=e[0],l=t=>null==a[t]?null:(0,s.Ro)(a[t]);return{as_of:a.as_of,close:l("close"),ema21:l("ema_21"),ema50:l("ema_50"),ema200:l("ema_200"),rsi:l("rsi_14"),dist_ema50:l("dist_ema50"),dist_ema200:l("dist_ema200"),atr:l("atr_14"),bb_width:l("bb_width"),vol_ratio_30d:l("vol_ratio_30d"),vol_ratio_60d:l("vol_ratio_60d"),pos_52w:l("pos_52w"),rs_1m:l("rs_1m_n500"),rs_3m:l("rs_3m_n500"),rs_6m:l("rs_6m_n500"),rs_sector_3m:l("rs_3m_sector"),vwap_252:l("vwap_252"),vwap_dist:l("vwap_dist"),delivery_pct:l("delivery_pct"),delivery_30d:l("delivery_avg_30d"),delivery_60d:l("delivery_avg_60d"),delivery_asym:l("delivery_updown_asym"),promoter_pct:l("promoter_pct"),pe_ttm:l("pe_ttm"),eps_ttm:l("eps_ttm")}}async function u(t){let e=await (0,n.A)`
    SELECT to_char(f.period_end,'YYYY-MM-DD') AS period_end,
      f.revenue, f.ebitda, f.pat, f.eps, f.ebitda_margin, f.net_margin, f.debt_equity_ratio
    FROM atlas_foundation.financials_quarterly f
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = f.instrument_id
    WHERE im.symbol = ${t} AND f.consolidated
    ORDER BY f.period_end DESC LIMIT 12`,a=t=>null==t?null:(0,s.Ro)(t),l=t=>{let e=null==t?null:(0,s.Ro)(t);return null==e?null:100*e},i=e.map(t=>({period_end:t.period_end,revenue:a(t.revenue),ebitda:a(t.ebitda),pat:a(t.pat),eps:a(t.eps),ebitda_margin:l(t.ebitda_margin),net_margin:l(t.net_margin),debt_equity:a(t.debt_equity_ratio)})),o=(t,e)=>null==t||null==e||0===e?null:(t-e)/Math.abs(e)*100;return i.slice(0,8).map((t,e)=>({...t,rev_yoy:o(t.revenue,i[e+4]?.revenue??null),pat_yoy:o(t.pat,i[e+4]?.pat??null)}))}async function N(t,e=20){return(await (0,n.A)`
    SELECT to_char(f.filing_date,'YYYY-MM-DD') AS date, f.category, f.category_bucket AS bucket,
           f.signal_priority AS priority, f.subject_text AS subject, f.source_url AS url
    FROM atlas_foundation.lens_filings f
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = f.instrument_id
    WHERE im.symbol = ${t}
    ORDER BY f.filing_date DESC, f.nse_seq_id DESC LIMIT ${e}`).map(t=>({date:t.date,category:t.category,bucket:t.bucket,priority:t.priority,subject:t.subject,url:t.url}))}async function L(t){return(await (0,n.A)`
    SELECT instrument_id::text AS instrument_id, symbol, name, sector
    FROM atlas_foundation.instrument_master
    WHERE symbol = ${t} AND asset_class='stock' LIMIT 1`)[0]??null}async function f(){let t=await (0,n.A)`
    SELECT to_char(max(date),'YYYY-MM-DD') AS d
    FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'`;return t[0]?.d??null}async function S(){let t=await (0,n.A)`
    WITH latest AS (SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'),
    tdl AS (SELECT max(date) d FROM atlas_foundation.technical_daily WHERE asset_class='stock'),  -- RS/ret as-of (asset_class filter uses the class_date index — an unfiltered max(date) seq-scans 6.9M rows)

    cap AS (
      SELECT instrument_id,
        CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
             WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
             WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
      FROM atlas_foundation.de_index_constituents
      WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
      GROUP BY instrument_id
    ),
    rs AS (  -- rs_3m_sector is the CANONICAL stored RS-vs-sector (stock 3M − sector-index 3M,
             -- both calendar-anchored via backfill_sector_rs); read it, never recompute inline.
      SELECT instrument_id, rs_1m_n500, rs_3m_n500, rs_6m_n500, ret_3m, rs_3m_sector
      FROM atlas_foundation.technical_daily
      WHERE asset_class='stock' AND date=(SELECT d FROM tdl)
    ),
    liq AS (  -- ≈20-session avg traded value (₹ Cr): a 30-calendar-day window ≈ 20 NSE sessions
      SELECT instrument_id, avg(close * volume) / 1e7 AS liq_cr
      FROM atlas_foundation.ohlcv_stock
      WHERE date >= (SELECT d FROM tdl) - INTERVAL '30 days' AND close > 0 AND volume > 0
      GROUP BY instrument_id
    ),
    j AS (
      SELECT l.instrument_id, im.symbol, im.name, im.sector, COALESCE(c.cap,'micro') AS cap,
             l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va,
             l.composite::float comp
      FROM atlas_foundation.atlas_lens_scores_daily l
      JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)
    ),
    dec AS (
      SELECT instrument_id, symbol, name, sector, cap,
        CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_tech,
        CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fund,
        CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_cat,
        CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
        CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_val,
        CASE WHEN comp IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(comp IS NULL) ORDER BY comp) END d_composite
      FROM j
    )
    SELECT d.symbol, d.name, d.sector, d.cap,
      d.d_tech, d.d_fund, d.d_cat, d.d_flow, d.d_val,
      (COALESCE((d.d_composite>=10)::int,0)) AS lead,  -- LEADER = top decile (D10) of composite within cap cohort (one rule; 0/1)
      ((COALESCE(d.d_tech,0)+COALESCE(d.d_flow,0))::float
        / NULLIF((d.d_tech IS NOT NULL)::int+(d.d_flow IS NOT NULL)::int,0)) AS strength,
      rs.rs_1m_n500, rs.rs_3m_n500, rs.rs_6m_n500,
      rs.rs_3m_sector, rs.ret_3m, liq.liq_cr
    FROM dec d
    LEFT JOIN rs  ON rs.instrument_id  = d.instrument_id
    LEFT JOIN liq ON liq.instrument_id = d.instrument_id
    ORDER BY strength DESC NULLS LAST
  `,e=t=>null==t?null:(0,s.Ro)(t);return t.map(t=>({symbol:t.symbol,name:t.name,sector:t.sector,cap:t.cap,d_tech:e(t.d_tech),d_fund:e(t.d_fund),d_cat:e(t.d_cat),d_flow:e(t.d_flow),d_val:e(t.d_val),lead:(0,s.oT)(t.lead,0),strength:e(t.strength),rs_1m:e(t.rs_1m_n500),rs_3m:e(t.rs_3m_n500),rs_6m:e(t.rs_6m_n500),rs_sector_3m:e(t.rs_3m_sector),ret_3m:e(t.ret_3m),liq_cr:e(t.liq_cr)}))}}};