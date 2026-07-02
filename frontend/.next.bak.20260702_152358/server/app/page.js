(()=>{var e={};e.id=974,e.ids=[974],e.modules={3295:e=>{"use strict";e.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},4536:(e,t,s)=>{let{createProxy:a}=s(39844);e.exports=a("/home/ubuntu/atlas-os/frontend/node_modules/next/dist/client/app-dir/link.js")},9258:(e,t,s)=>{"use strict";s.d(t,{MarketPulseBreadthCharts:()=>a});let a=(0,s(12907).registerClientReference)(function(){throw Error("Attempted to call MarketPulseBreadthCharts() from the server but MarketPulseBreadthCharts is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/v4/market-pulse/MarketPulseBreadthCharts.tsx","MarketPulseBreadthCharts")},10846:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},19121:e=>{"use strict";e.exports=require("next/dist/server/app-render/action-async-storage.external.js")},21820:e=>{"use strict";e.exports=require("os")},27910:e=>{"use strict";e.exports=require("stream")},29021:e=>{"use strict";e.exports=require("fs")},29294:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-async-storage.external.js")},33873:e=>{"use strict";e.exports=require("path")},34631:e=>{"use strict";e.exports=require("tls")},35886:(e,t,s)=>{"use strict";s.d(t,{Z:()=>r});var a=s(60687);function n({title:e,children:t}){return(0,a.jsxs)("span",{className:"group/info relative inline-flex",children:[(0,a.jsx)("button",{type:"button","aria-label":e?`About ${e}`:"More info",className:"grid h-[17px] w-[17px] place-items-center rounded-full border border-brand/50 bg-brand/5 font-num text-[10px] font-semibold italic leading-none text-brand transition-colors hover:border-brand hover:bg-brand/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",children:"i"}),(0,a.jsxs)("span",{role:"tooltip",className:"pointer-events-none absolute left-1/2 top-[150%] z-50 w-[280px] -translate-x-1/2 rounded-tile border border-edge-rule bg-surface-raised p-3 text-[11.5px] leading-[1.55] text-txt-2 opacity-0 shadow-panel transition-opacity duration-150 group-hover/info:opacity-100 group-focus-within/info:opacity-100",children:[e&&(0,a.jsx)("span",{className:"mb-1 block font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:e}),t]})]})}function r({title:e,eyebrow:t,info:s,action:r,children:o,className:l="",bodyClassName:i=""}){let c=e||t||s||r;return(0,a.jsxs)("section",{className:`rounded-panel border border-edge-hair bg-surface-panel shadow-panel ${l}`,children:[c&&(0,a.jsxs)("header",{className:"flex items-center gap-2.5 border-b border-edge-hair px-5 py-3.5",children:[(0,a.jsxs)("div",{className:"min-w-0",children:[t&&(0,a.jsx)("div",{className:"font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:t}),e&&(0,a.jsx)("h2",{className:"font-display text-[15px] font-medium leading-tight text-txt-1",children:e})]}),s&&(0,a.jsx)(n,{title:s.title,children:s.body}),r&&(0,a.jsx)("div",{className:"ml-auto shrink-0",children:r})]}),(0,a.jsx)("div",{className:i||"px-5 py-4",children:o})]})}},45671:(e,t,s)=>{"use strict";s.r(t),s.d(t,{TermInfo:()=>a});let a=(0,s(12907).registerClientReference)(function(){throw Error("Attempted to call TermInfo() from the server but TermInfo is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/v6/shared/TermInfo.tsx","TermInfo")},54747:(e,t,s)=>{"use strict";s.r(t),s.d(t,{GlobalError:()=>o.a,__next_app__:()=>m,pages:()=>d,routeModule:()=>_,tree:()=>c});var a=s(65239),n=s(48088),r=s(88170),o=s.n(r),l=s(30893),i={};for(let e in l)0>["default","tree","pages","GlobalError","__next_app__","routeModule"].indexOf(e)&&(i[e]=()=>l[e]);s.d(t,i);let c=["",{children:["__PAGE__",{},{page:[()=>Promise.resolve().then(s.bind(s,89646)),"/home/ubuntu/atlas-os/frontend/src/app/page.tsx"]}]},{layout:[()=>Promise.resolve().then(s.bind(s,83218)),"/home/ubuntu/atlas-os/frontend/src/app/layout.tsx"],error:[()=>Promise.resolve().then(s.bind(s,54431)),"/home/ubuntu/atlas-os/frontend/src/app/error.tsx"],loading:[()=>Promise.resolve().then(s.bind(s,67393)),"/home/ubuntu/atlas-os/frontend/src/app/loading.tsx"],"not-found":[()=>Promise.resolve().then(s.t.bind(s,57398,23)),"next/dist/client/components/not-found-error"],forbidden:[()=>Promise.resolve().then(s.t.bind(s,89999,23)),"next/dist/client/components/forbidden-error"],unauthorized:[()=>Promise.resolve().then(s.t.bind(s,65284,23)),"next/dist/client/components/unauthorized-error"]}],d=["/home/ubuntu/atlas-os/frontend/src/app/page.tsx"],m={require:s,loadChunk:()=>Promise.resolve()},_=new a.AppPageRouteModule({definition:{kind:n.RouteKind.APP_PAGE,page:"/page",pathname:"/",bundlePath:"",filename:"",appPaths:[]},userland:{loaderTree:c}})},55511:e=>{"use strict";e.exports=require("crypto")},56822:(e,t,s)=>{"use strict";s.d(t,{Ko:()=>r,Wi:()=>i,Z4:()=>d,_p:()=>c,af:()=>l,ru:()=>o});var a=s(5069),n=s(6707);async function r(){return(await (0,a.A)`
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
  `).map(e=>({as_of_date:e.as_of_date,sector_name:e.sector_name,constituent_count:e.constituent_count,ret_1w:(0,n.Ro)(e.ret_1w),ret_1m:(0,n.Ro)(e.ret_1m),ret_3m:(0,n.Ro)(e.ret_3m),ret_6m:(0,n.Ro)(e.ret_6m),ret_12m:(0,n.Ro)(e.ret_12m),rs_1m:(0,n.Ro)(e.rs_1m),rs_3m:(0,n.Ro)(e.rs_3m),rs_6m:(0,n.Ro)(e.rs_6m),vol_60d_ann:(0,n.Ro)(e.vol_60d_ann),pct_above_ema21:(0,n.Ro)(e.pct_above_ema21),pct_above_ema200:(0,n.Ro)(e.pct_above_ema200),pct_at_52wh:(0,n.Ro)(e.pct_at_52wh),hhi_concentration:(0,n.Ro)(e.hhi_concentration),buy_signal_count:e.buy_signal_count,confidence_distribution:e.confidence_distribution,verdict:e.verdict,verdict_abbr:e.verdict_abbr}))}async function o(){let e=await (0,a.A)`
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
  `,t={};for(let s of e)(t[s.sector]??=[]).push({sector:s.sector,symbol:s.symbol,name:s.name,ret_1d:(0,n.Ro)(s.r1d),ret_1w:(0,n.Ro)(s.r1w),ret_1m:(0,n.Ro)(s.r1m),ret_3m:(0,n.Ro)(s.r3m),ret_6m:(0,n.Ro)(s.r6m),ret_12m:(0,n.Ro)(s.r12m),ff_weight:(0,n.Ro)(s.ff_weight)});return t}async function l(e){return(await (0,a.A)`
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
    ${null!=e?(0,a.A)`AND sector_name = ${e}`:(0,a.A)``}
    ORDER BY sector_name
  `).map(e=>({as_of_date:e.as_of_date,sector_name:e.sector_name,constituent_count:e.constituent_count,pct_above_ema21:(0,n.Ro)(e.pct_above_ema21),pct_above_ema50:(0,n.Ro)(e.pct_above_ema50),pct_above_ema200:(0,n.Ro)(e.pct_above_ema200),pct_at_52wh:(0,n.Ro)(e.pct_at_52wh),breadth_by_window:e.breadth_by_window??[],breadth_by_strength:e.breadth_by_strength??null,top_movers:e.top_movers??[],bottom_movers:e.bottom_movers??[]}))}async function i(){return(await (0,a.A)`
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
  `).map(e=>({sector_name:e.sector_name,ema21_now:(0,n.Ro)(e.ema21_now),ema21_1w:(0,n.Ro)(e.ema21_1w),ema21_1m:(0,n.Ro)(e.ema21_1m)}))}async function c(){return(await (0,a.A)`
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
  `).map(e=>({as_of_date:e.as_of_date,sector_name:e.sector_name,rs_ratio_current:(0,n.Ro)(e.rs_ratio_current),rs_momentum_current:(0,n.Ro)(e.rs_momentum_current),quadrant_current:e.quadrant_current,trail_6w:e.trail_6w??[],constituent_count:e.constituent_count}))}async function d(e){let t=await (0,a.A)`
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
    WHERE sector_name = ${e}
    LIMIT 1
  `;if(0===t.length)return null;let s=t[0];return{sector_name:s.sector_name,verdict:s.verdict,constituent_count:s.constituent_count,data_as_of:s.data_as_of,returns:s.returns,rs_windows:s.rs_windows,pct_above_ema21:(0,n.Ro)(s.pct_above_ema21),pct_above_ema200:(0,n.Ro)(s.pct_above_ema200),pct_at_52wh:(0,n.Ro)(s.pct_at_52wh),constituents_top30:s.constituents_top30??[],open_signals:s.open_signals??[],strength_dist:s.strength_dist??{very_strong:0,strong:0,neutral:0,weak:0,very_weak:0},top_picks_top10:s.top_picks_top10??[],sub_industries:[]}}},60021:(e,t,s)=>{"use strict";s.d(t,{Z:()=>r});var a=s(37413);function n({title:e,children:t}){return(0,a.jsxs)("span",{className:"group/info relative inline-flex",children:[(0,a.jsx)("button",{type:"button","aria-label":e?`About ${e}`:"More info",className:"grid h-[17px] w-[17px] place-items-center rounded-full border border-brand/50 bg-brand/5 font-num text-[10px] font-semibold italic leading-none text-brand transition-colors hover:border-brand hover:bg-brand/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",children:"i"}),(0,a.jsxs)("span",{role:"tooltip",className:"pointer-events-none absolute left-1/2 top-[150%] z-50 w-[280px] -translate-x-1/2 rounded-tile border border-edge-rule bg-surface-raised p-3 text-[11.5px] leading-[1.55] text-txt-2 opacity-0 shadow-panel transition-opacity duration-150 group-hover/info:opacity-100 group-focus-within/info:opacity-100",children:[e&&(0,a.jsx)("span",{className:"mb-1 block font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:e}),t]})]})}function r({title:e,eyebrow:t,info:s,action:r,children:o,className:l="",bodyClassName:i=""}){let c=e||t||s||r;return(0,a.jsxs)("section",{className:`rounded-panel border border-edge-hair bg-surface-panel shadow-panel ${l}`,children:[c&&(0,a.jsxs)("header",{className:"flex items-center gap-2.5 border-b border-edge-hair px-5 py-3.5",children:[(0,a.jsxs)("div",{className:"min-w-0",children:[t&&(0,a.jsx)("div",{className:"font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:t}),e&&(0,a.jsx)("h2",{className:"font-display text-[15px] font-medium leading-tight text-txt-1",children:e})]}),s&&(0,a.jsx)(n,{title:s.title,children:s.body}),r&&(0,a.jsx)("div",{className:"ml-auto shrink-0",children:r})]}),(0,a.jsx)("div",{className:i||"px-5 py-4",children:o})]})}},63033:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},64868:(e,t,s)=>{"use strict";s.d(t,{E:()=>l,x:()=>i});var a=s(5069),n=s(6707);let r={ret_1d:null,ret_1w:null,ret_1m:null,ret_3m:null,ret_6m:null,ret_12m:null};function o(e){return{ret_1d:(0,n.Ro)(e.ret_1d),ret_1w:(0,n.Ro)(e.ret_1w),ret_1m:(0,n.Ro)(e.ret_1m),ret_3m:(0,n.Ro)(e.ret_3m),ret_6m:(0,n.Ro)(e.ret_6m),ret_12m:(0,n.Ro)(e.ret_12m)}}async function l(){let e=await (0,a.A)`
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
  `,t=new Map(e.filter(e=>"NIFTY 50"===e.index_code||"NIFTY 500"===e.index_code).map(e=>[e.index_code,o(e)]));return{sectors:e.filter(e=>null!=e.sector_name).map(e=>({sector_name:e.sector_name,nse_index_code:e.index_code,ret:o(e)})),bases:{"NIFTY 50":t.get("NIFTY 50")??r,"NIFTY 500":t.get("NIFTY 500")??r},as_of:e[0]?.date??null}}async function i(e){let t=await (0,a.A)`
    SELECT s.date::text AS date, s.index_code, (s.close / n.close)::text AS ratio
    FROM atlas_foundation.index_prices s
    JOIN atlas_foundation.index_prices n
      ON n.date = s.date AND n.index_code = 'NIFTY 50'
    WHERE s.index_code = (
      SELECT primary_nse_index FROM atlas_foundation.atlas_sector_master
      WHERE sector_name = ${e} AND is_active = true
      LIMIT 1
    )
      AND n.close > 0
      AND s.close > 0
    ORDER BY s.date
  `;return{sector_name:e,index_code:t[0]?.index_code??null,daily:t.map(e=>({time:e.date,value:(0,n.Ro)(e.ratio)})).filter(e=>null!=e.value&&Number.isFinite(e.value))}}},66614:(e,t,s)=>{"use strict";function a(e){return null==e||e<1?"var(--color-surface-inset)":`var(--decile-${Math.min(10,Math.max(1,Math.round(e)))})`}s.d(t,{c:()=>a})},74998:e=>{"use strict";e.exports=require("perf_hooks")},83001:(e,t,s)=>{"use strict";s.d(t,{SectorLeadershipBoard:()=>a});let a=(0,s(12907).registerClientReference)(function(){throw Error("Attempted to call SectorLeadershipBoard() from the server but SectorLeadershipBoard is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/v4/market-pulse/SectorLeadershipBoard.tsx","SectorLeadershipBoard")},89646:(e,t,s)=>{"use strict";s.r(t),s.d(t,{default:()=>P,revalidate:()=>Y});var a=s(37413),n=s(5069);async function r(){return(await (0,n.A)`
    WITH latest_full AS (
      SELECT *
      FROM atlas_foundation.atlas_market_regime_daily
      WHERE pct_above_ema_50 IS NOT NULL
      ORDER BY date DESC
      LIMIT 1
    ),
    latest_any AS (
      SELECT *
      FROM atlas_foundation.atlas_market_regime_daily
      ORDER BY date DESC
      LIMIT 1
    )
    SELECT
      la.date,
      la.nifty500_close, la.nifty500_ema_50, la.nifty500_ema_200,
      la.nifty500_above_ema_50, la.nifty500_above_ema_200,
      la.nifty500_ema_50_slope, la.nifty500_ema_200_slope,
      COALESCE(la.pct_above_ema_20,  lf.pct_above_ema_20)  AS pct_above_ema_20,
      COALESCE(la.pct_above_ema_50,  lf.pct_above_ema_50)  AS pct_above_ema_50,
      COALESCE(la.pct_above_ema_200, lf.pct_above_ema_200) AS pct_above_ema_200,
      COALESCE(la.advances_count,    lf.advances_count)    AS advances_count,
      COALESCE(la.declines_count,    lf.declines_count)    AS declines_count,
      COALESCE(la.unchanged_count,   lf.unchanged_count)   AS unchanged_count,
      COALESCE(la.ad_ratio,          lf.ad_ratio)          AS ad_ratio,
      COALESCE(la.ad_line,           lf.ad_line)           AS ad_line,
      COALESCE(la.ad_line_slope_21,  lf.ad_line_slope_21)  AS ad_line_slope_21,
      COALESCE(la.mcclellan_oscillator, lf.mcclellan_oscillator) AS mcclellan_oscillator,
      COALESCE(la.mcclellan_summation,  lf.mcclellan_summation)  AS mcclellan_summation,
      COALESCE(la.new_52w_highs,     lf.new_52w_highs)     AS new_52w_highs,
      COALESCE(la.new_52w_lows,      lf.new_52w_lows)      AS new_52w_lows,
      COALESCE(la.net_new_highs,     lf.net_new_highs)     AS net_new_highs,
      COALESCE(la.new_high_low_ratio, lf.new_high_low_ratio) AS new_high_low_ratio,
      COALESCE(la.pct_in_strong_states, lf.pct_in_strong_states) AS pct_in_strong_states,
      COALESCE(la.pct_weinstein_pass,   lf.pct_weinstein_pass)   AS pct_weinstein_pass,
      la.india_vix, la.realized_vol_5d_nifty500, la.vol_252_median_nifty500,
      la.regime_state, la.deployment_multiplier, la.dislocation_active, la.dislocation_started
    FROM latest_any la
    LEFT JOIN latest_full lf ON true
  `)[0]??null}async function o(e=10){return(0,n.A)`
    SELECT to_char(date, 'YYYY-MM-DD') AS date,
           n_members, above_21, above_50, above_200, gc_50_200, net_new_highs,
           avg_rsi_14, idx_ret_3m
    FROM atlas_foundation.breadth_nifty500_daily
    WHERE date >= NOW() - (${e} || ' years')::INTERVAL
    ORDER BY date ASC
  `}let l={lc:"NIFTY 100",mc:"NIFTY MIDCAP 150",sc:"NIFTY SMLCAP 250"},i=[["1W",6],["1M",22],["3M",64],["6M",127],["1Y",253]];async function c(){let e=await (0,n.A)`
    SELECT index_code, close::text,
           row_number() OVER (PARTITION BY index_code ORDER BY date DESC) AS rn
    FROM atlas_foundation.index_prices
    WHERE index_code IN (${l.lc}, ${l.mc}, ${l.sc})
      AND date >= NOW() - INTERVAL '2 years' AND close > 0
  `,t={};for(let s of e)(t[s.index_code]??=new Map).set(Number(s.rn),parseFloat(s.close));let s=(e,s)=>{let a=t[e];if(!a)return null;let n=a.get(1),r=a.get(s);return null!=n&&null!=r&&r>0?n/r-1:null},a=i.map(([e,t])=>{let a=s(l.sc,t),n=s(l.mc,t),r=s(l.lc,t);return{label:e,sc:a,mc:n,lc:r,sc_lc:null!=a&&null!=r?a-r:null,mc_lc:null!=n&&null!=r?n-r:null}}),r=await (0,n.A)`
    WITH r AS (
      SELECT s.date, s.close / l.close AS ratio
      FROM atlas_foundation.index_prices s
      JOIN atlas_foundation.index_prices l ON l.date = s.date AND l.index_code = ${l.lc}
      WHERE s.index_code = ${l.sc} AND s.date >= NOW() - INTERVAL '1 year' AND l.close > 0
    )
    SELECT ((SELECT ratio FROM r ORDER BY date DESC LIMIT 1) - avg(ratio)) / NULLIF(stddev(ratio), 0) AS z
    FROM r
  `.catch(()=>[{z:null}]);return{windows:a,smallcap_rs_z:r[0]?.z!=null?parseFloat(r[0].z):null}}let d=[["NIFTY 50","Nifty 50"],["NIFTY BANK","Bank Nifty"],["NIFTY MIDCAP 150","Midcap 150"],["NIFTY SMLCAP 250","Smallcap 250"]];async function m(){let e=await (0,n.A)`
    SELECT index_code, to_char(date,'YYYY-MM-DD') AS date, close::text
    FROM atlas_foundation.index_prices
    WHERE index_code = ANY(${d.map(e=>e[0])}) AND close > 0
      AND date >= CURRENT_DATE - 60
    ORDER BY index_code, date
  `,t=new Map;for(let s of e){let e=Number(s.close);Number.isFinite(e)&&(t.get(s.index_code)??t.set(s.index_code,[]).get(s.index_code)).push(e)}let s=(e,t)=>e.length>t&&e[e.length-1-t]?(e[e.length-1]-e[e.length-1-t])/e[e.length-1-t]*100:null;return d.map(([e,a])=>{let n=t.get(e)??[];return{code:e,label:a,close:n.length?n[n.length-1]:null,d1:s(n,1),d1w:s(n,5),d1m:s(n,21)}})}var _=s(96742),u=s(64868),x=s(56822),p=s(32936),h=s(60021),f=s(83001),b=s(45671);let g=(e,t)=>`${e>=0?"+":""}${e.toFixed(t)}`,v=e=>null==e?"var(--color-txt-2)":e>0?"var(--color-sig-pos)":e<0?"var(--color-sig-neg)":"var(--color-txt-2)",N=({children:e,color:t})=>(0,a.jsx)("span",{className:"font-num text-[12px] tabular-nums",style:{color:t??"var(--color-txt-1)"},children:e}),E=({children:e,right:t})=>(0,a.jsx)("th",{className:`px-2 py-2 font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3 ${t?"text-right":"text-left"}`,children:e});function w({state:e,deploymentPct:t}){let s=e.toLowerCase(),n=/on|bull|strong|expansion/.test(s)?"var(--color-sig-pos)":/off|bear|weak|contraction|stress/.test(s)?"var(--color-sig-neg)":/caution|neutral|mixed|transition/.test(s)?"var(--color-sig-warn)":"var(--color-brand)";return(0,a.jsxs)("div",{className:"inline-flex items-center gap-2.5 rounded-full border border-edge-rule bg-surface-raised px-3.5 py-1.5",children:[(0,a.jsx)("span",{className:"h-2 w-2 rounded-full",style:{background:n,boxShadow:`0 0 8px -1px ${n}`}}),(0,a.jsx)("span",{className:"font-display text-[13px] font-semibold",style:{color:n},children:e}),null!=t&&(0,a.jsxs)("span",{className:"font-num text-[11px] tabular-nums text-txt-2",children:["\xb7 ",t,"% deployed"]})]})}let y=e=>null==e?"—":Math.round(e).toLocaleString("en-IN"),j=e=>{let t=e.toLowerCase();return t.includes("golden")?"golden_cross":t.includes("new high")?"net_new_highs":t.includes("ema")?"above_ema_count":void 0};function A({rows:e,total:t,asOf:s}){return(0,a.jsxs)(h.Z,{eyebrow:"Participation",title:"Market breadth",info:{title:"Market breadth",body:"How many of the Nifty 500 are taking part — counts of names, not percentages. Above-EMA rows count names trading above that moving average; golden crosses are names whose 50-EMA sits above their 200-EMA; net new highs is 52-week highs minus lows. Each column is the count on that day, so you can read the trend directly."},bodyClassName:"px-2 pb-3 pt-1",children:[(0,a.jsxs)("p",{className:"px-2 pb-2 font-sans text-[11.5px] leading-snug text-txt-2",children:["Number of Nifty 500 stocks",t?(0,a.jsxs)(a.Fragment,{children:[" out of ",(0,a.jsx)("span",{className:"font-num tabular-nums text-txt-1",children:y(t)})]}):""," participating — compare today with a week and a month ago to see if breadth is widening or narrowing."]}),(0,a.jsxs)("table",{className:"tbl-centered w-full border-collapse",children:[(0,a.jsx)("thead",{children:(0,a.jsxs)("tr",{className:"border-b border-edge-hair",children:[(0,a.jsx)(E,{children:"Metric"}),(0,a.jsx)(E,{right:!0,children:"Today"}),(0,a.jsx)(E,{right:!0,children:"1 wk ago"}),(0,a.jsx)(E,{right:!0,children:"1 mo ago"})]})}),(0,a.jsx)("tbody",{children:e.map(e=>(0,a.jsxs)("tr",{className:"border-b border-edge-hair/60 last:border-0",children:[(0,a.jsxs)("td",{className:"px-2 py-1.5 font-sans text-[12px] text-txt-2",children:[e.label,j(e.label)&&(0,a.jsx)(b.TermInfo,{term:j(e.label)})]}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(N,{children:y(e.today)})}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(N,{color:"var(--color-txt-3)",children:y(e.wkAgo)})}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(N,{color:"var(--color-txt-3)",children:y(e.moAgo)})})]},e.label))})]}),s&&(0,a.jsxs)("p",{className:"px-2 pt-2 font-num text-[9px] uppercase tracking-wider text-txt-3",children:["as of ",s]})]})}function S({data:e}){let t=e=>null==e?"—":`${g(100*e,1)}%`,s=e.smallcap_rs_z;return(0,a.jsxs)(h.Z,{eyebrow:"Cap-tier leadership",title:"Returns by size",info:{title:"Returns by size",body:"Total return of each size cohort over five windows, plus the small/mid-cap spread vs large-cap. A positive spread means smaller caps are leading. The z-score gauges how stretched small-cap leadership is vs its own 1-year norm."},bodyClassName:"px-2 pb-3 pt-1",children:[(0,a.jsxs)("p",{className:"px-2 pb-2 font-sans text-[11.5px] leading-snug text-txt-2",children:["How each size band has performed. ",(0,a.jsx)("span",{className:"text-txt-1",children:"SC−LC"})," / ",(0,a.jsx)("span",{className:"text-txt-1",children:"MC−LC"})," are small- and mid-cap returns minus large-cap — positive means smaller companies are leading the market."]}),(0,a.jsxs)("table",{className:"tbl-centered w-full border-collapse",children:[(0,a.jsx)("thead",{children:(0,a.jsxs)("tr",{className:"border-b border-edge-hair",children:[(0,a.jsx)(E,{children:"Window"}),(0,a.jsxs)(E,{right:!0,children:["Small 250",(0,a.jsx)(b.TermInfo,{term:"tier_return"})]}),(0,a.jsxs)(E,{right:!0,children:["Mid 150",(0,a.jsx)(b.TermInfo,{term:"tier_return"})]}),(0,a.jsxs)(E,{right:!0,children:["Nifty 100",(0,a.jsx)(b.TermInfo,{term:"tier_return"})]}),(0,a.jsxs)(E,{right:!0,children:["SC−LC",(0,a.jsx)(b.TermInfo,{term:"tier_return"})]}),(0,a.jsxs)(E,{right:!0,children:["MC−LC",(0,a.jsx)(b.TermInfo,{term:"tier_return"})]})]})}),(0,a.jsx)("tbody",{children:e.windows.map(e=>(0,a.jsxs)("tr",{className:"border-b border-edge-hair/60 last:border-0",children:[(0,a.jsx)("td",{className:"px-2 py-1.5 font-num text-[11px] uppercase tracking-wider text-txt-3",children:e.label}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(N,{color:v(e.sc),children:t(e.sc)})}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(N,{color:v(e.mc),children:t(e.mc)})}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(N,{color:v(e.lc),children:t(e.lc)})}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(N,{color:v(e.sc_lc),children:t(e.sc_lc)})}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(N,{color:v(e.mc_lc),children:t(e.mc_lc)})})]},e.label))})]}),null!=s&&(0,a.jsxs)("p",{className:"px-2 pt-2.5 font-sans text-[11px] text-txt-2",children:["Small-cap relative strength",(0,a.jsx)(b.TermInfo,{term:"smallcap_rs_z"})," is"," ",(0,a.jsxs)("span",{className:"font-num tabular-nums",style:{color:v(s)},children:[g(s,1),"σ"]})," ","vs its 1-year norm — ",Math.abs(s)>=1.5?"stretched":"within normal range","."]})]})}function R({top:e,weak:t,stocksBySector:s}){return(0,a.jsxs)(h.Z,{eyebrow:"Rotation",title:"Sector leadership",info:{title:"How to read this",body:(0,a.jsxs)(a.Fragment,{children:["Each sector is scored by the ",(0,a.jsx)("strong",{children:"average conviction decile"})," of its stocks — where each stock sits from 1 (bottom) to 10 (top) versus peers of its own size. ",(0,a.jsx)("strong",{children:"Tech"})," counts names with leading price action (top three deciles); ",(0,a.jsx)("strong",{children:"fund"})," counts names with leading financials. ",(0,a.jsx)("strong",{children:"Click any sector to expand it"})," into a table of its stocks scored across every lens."]})},children:[(0,a.jsxs)("p",{className:"mb-2.5 font-sans text-[11.5px] leading-snug text-txt-2",children:["The 5 strongest and 5 weakest sectors by their stocks’ average conviction (1–10). ",(0,a.jsx)("span",{className:"text-txt-1",children:"Click a sector"})," to expand its stocks scored across all five lenses."]}),(0,a.jsx)(f.SectorLeadershipBoard,{top:e,weak:t,stocksBySector:s})]})}let C=e=>null==e?"—":e.toLocaleString("en-IN",{maximumFractionDigits:0}),L=e=>null==e?"—":`${e>=0?"+":""}${e.toFixed(1)}%`,T=e=>null==e?"var(--color-txt-3)":e>0?"var(--color-sig-pos)":e<0?"var(--color-sig-neg)":"var(--color-txt-2)";function M({quotes:e}){return(0,a.jsx)("div",{className:"mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4",children:e.map(e=>(0,a.jsxs)("div",{className:"rounded-tile border border-edge-rule bg-surface-raised px-3.5 py-2.5",children:[(0,a.jsxs)("div",{className:"flex items-baseline justify-between gap-2",children:[(0,a.jsx)("span",{className:"font-sans text-[11px] font-medium text-txt-2",children:e.label}),(0,a.jsx)("span",{className:"font-num text-[12px] tabular-nums",style:{color:T(e.d1)},children:L(e.d1)})]}),(0,a.jsx)("div",{className:"mt-1 font-num text-[20px] font-semibold leading-none tabular-nums text-txt-1",children:C(e.close)}),(0,a.jsxs)("div",{className:"mt-1.5 flex gap-3 font-num text-[10px] tabular-nums text-txt-3",children:[(0,a.jsxs)("span",{children:["1w ",(0,a.jsx)("span",{style:{color:T(e.d1w)},children:L(e.d1w)})]}),(0,a.jsxs)("span",{children:["1m ",(0,a.jsx)("span",{style:{color:T(e.d1m)},children:L(e.d1m)})]})]})]},e.code))})}var O=s(9258);let k=e=>null==e?"—":Math.round(e).toLocaleString("en-IN"),I=e=>null==e?"—":`${e>=0?"+":""}${Math.round(e).toLocaleString("en-IN")}`,F=e=>null==e?"neutral":e>=50?"pos":"neg";async function D(){var e;let t=await r().catch(()=>null);if(!t)return(0,a.jsx)("div",{className:"min-h-screen bg-surface-base font-sans text-txt-1",children:(0,a.jsx)("div",{className:"mx-auto max-w-[1680px] px-6 py-10",children:(0,a.jsx)(h.Z,{title:"No regime data",children:(0,a.jsx)("p",{className:"font-sans text-[13px] text-txt-2",children:"Run the nightly pipeline first."})})})});let s=await (0,_.Q9)().catch(()=>[]),[n,l,i,d,f]=await Promise.all([o(10).catch(()=>[]),c().catch(()=>({windows:[],smallcap_rs_z:null})),m().catch(()=>[]),(0,u.E)().catch(()=>null),(0,x.af)().catch(()=>[])]),b=d?.bases["NIFTY 50"],g=new Map((d?.sectors??[]).map(e=>[e.sector_name,{rs_1w:null!=e.ret.ret_1w&&b?.ret_1w!=null?e.ret.ret_1w-b.ret_1w:null,rs_1m:null!=e.ret.ret_1m&&b?.ret_1m!=null?e.ret.ret_1m-b.ret_1m:null,rs_3m:null!=e.ret.ret_3m&&b?.ret_3m!=null?e.ret.ret_3m-b.ret_3m:null}])),v=new Map(f.map(e=>[e.sector_name,{ema21:null!=e.pct_above_ema21?Math.round(e.pct_above_ema21*e.constituent_count):null,ema50:null!=e.pct_above_ema50?Math.round(e.pct_above_ema50*e.constituent_count):null,emaTotal:e.constituent_count??null}])),N=_.kL,E=new Map,y={};for(let e of s){if(!e.sector||null==e.strength)continue;let t=E.get(e.sector)??{sum:0,n:0,tech:0,fund:0};t.sum+=e.strength,t.n+=1,(e.d_tech??0)>=N&&(t.tech+=1),(e.d_fund??0)>=N&&(t.fund+=1),E.set(e.sector,t),(y[e.sector]??=[]).push({symbol:e.symbol,name:e.name,d_tech:e.d_tech,d_fund:e.d_fund,d_cat:e.d_cat,d_flow:e.d_flow,d_val:e.d_val,lead:e.lead,strength:e.strength})}let j=[...E.entries()].filter(([,e])=>e.n>=5).map(([e,t])=>{let s=g.get(e),a=v.get(e);return{name:e,avg:t.sum/t.n,n:t.n,techLeaders:t.tech,fundLeaders:t.fund,rs_1w:s?.rs_1w??null,rs_1m:s?.rs_1m??null,rs_3m:s?.rs_3m??null,ema21:a?.ema21??null,ema50:a?.ema50??null,emaTotal:a?.emaTotal??null}}).sort((e,t)=>t.avg-e.avg),C=j.slice(0,5),L=j.slice(-5).reverse(),T=e=>n.length>e?n[n.length-1-e]:null,D=(e,t)=>{let s=e=>e?e[t]:null;return{label:e,today:s(T(0)),wkAgo:s(T(5)),moAgo:s(T(21))}},Y=n.length?n[n.length-1]:null,P=Number.isFinite(parseFloat(String(t.deployment_multiplier)))?Math.round(100*parseFloat(String(t.deployment_multiplier))):null,$=((e=t.date)?e instanceof Date?e.toISOString().slice(0,10):String(e).slice(0,10):null)??(Y?Y.date:null),B=(e,t)=>t?Math.round(e/t*100):null;return(0,a.jsx)("div",{className:"min-h-screen bg-surface-base font-sans text-txt-1",children:(0,a.jsxs)("div",{className:"mx-auto max-w-[1680px] px-6 py-7",children:[(0,a.jsxs)("header",{className:"mb-6 flex flex-wrap items-end justify-between gap-4",children:[(0,a.jsxs)("div",{children:[(0,a.jsx)("p",{className:"font-num text-[10px] uppercase tracking-[0.2em] text-txt-3",children:"Market Pulse \xb7 NSE"}),(0,a.jsx)("h1",{className:"mt-1.5 font-display text-[32px] font-bold leading-none tracking-tight text-txt-1",children:"Markets Today"}),$&&(0,a.jsxs)("p",{className:"mt-2 font-num text-[11px] tabular-nums text-txt-3",children:["as of ",$]})]}),(0,a.jsx)(w,{state:t.regime_state,deploymentPct:P})]}),i.length>0&&(0,a.jsx)(M,{quotes:i}),(0,a.jsxs)("div",{className:"mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6",children:[Y&&(0,a.jsxs)(a.Fragment,{children:[[["Above 21-EMA",Y.above_21,21],["Above 50-EMA",Y.above_50,50],["Above 200-EMA",Y.above_200,200]].map(([e,t,s])=>{let n=B(t,Y.n_members);return(0,a.jsx)(p.h,{label:e,value:k(t),tone:F(n),href:`/stocks?ema=${s}`,sub:`${n??"—"}% of ${k(Y.n_members)}`},s)}),(0,a.jsx)(p.h,{label:"Golden cross",value:k(Y.gc_50_200),tone:"brand",sub:"50-EMA > 200-EMA",href:"/stocks?gc=1"}),(0,a.jsx)(p.h,{label:"Net new highs",value:I(Y.net_new_highs),tone:Y.net_new_highs>=0?"pos":"neg",sub:"52-week H − L",href:"/stocks?nh=1"})]}),(0,a.jsx)(p.h,{label:"Smallcap RS",value:null==l.smallcap_rs_z?"—":`${l.smallcap_rs_z>=0?"+":""}${l.smallcap_rs_z.toFixed(1)}`,unit:"σ",tone:null==l.smallcap_rs_z?"neutral":l.smallcap_rs_z>=0?"pos":"neg",sub:"vs large-cap \xb7 1y"})]}),j.length>0&&(0,a.jsx)("div",{className:"mb-6",children:(0,a.jsx)(R,{top:C,weak:L,stocksBySector:y})}),(0,a.jsxs)("div",{className:"mb-6 grid grid-cols-1 gap-5 lg:grid-cols-2",children:[Y&&(0,a.jsx)(A,{rows:[D("Above 21-EMA","above_21"),D("Above 50-EMA","above_50"),D("Above 200-EMA","above_200"),D("Golden crosses","gc_50_200"),D("Net new highs","net_new_highs")],total:Y.n_members,asOf:Y.date}),l.windows.length>0&&(0,a.jsx)(S,{data:l})]}),n.length>1&&(0,a.jsx)("div",{className:"mb-6",children:(0,a.jsx)(O.MarketPulseBreadthCharts,{series:n})})]})})}let Y=300;function P(){return(0,a.jsx)(D,{})}},90383:(e,t,s)=>{Promise.resolve().then(s.t.bind(s,4536,23)),Promise.resolve().then(s.bind(s,9258)),Promise.resolve().then(s.bind(s,83001)),Promise.resolve().then(s.bind(s,45671))},90476:(e,t,s)=>{"use strict";s.d(t,{MarketPulseBreadthCharts:()=>c});var a=s(60687),n=s(43210),r=s(45875),o=s(35886);let l=[{key:"above_21",label:"Above 21-EMA",color:"teal"},{key:"above_50",label:"Above 50-EMA",color:"pos"},{key:"above_200",label:"Above 200-EMA",color:"warn"},{key:"net_new_highs",label:"Net new highs \xb7 52w H − L",color:"pos"}],i=[{label:"1Y",years:1},{label:"2Y",years:2},{label:"5Y",years:5},{label:"10Y",years:10},{label:"All",years:null}];function c({series:e}){let[t,s]=(0,n.useState)(5);if(e.length<2)return null;let c=null==t?e:e.slice(-Math.round(252*t));return(0,a.jsxs)(o.Z,{eyebrow:"Participation",title:"Breadth — count of Nifty 500 names",info:{title:"Breadth history",body:"How many of the ~500 Nifty 500 constituents sit above each trend EMA, plus the net 52-week new-high count (highs − lows). Counts are instruments (integers), tracked daily over up to 10 years — rising breadth = a broadening advance. Use the window toggle to zoom the history."},children:[(0,a.jsxs)("div",{className:"mb-3 flex items-center gap-2",children:[(0,a.jsx)("span",{className:"font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:"History"}),(0,a.jsx)("div",{className:"inline-flex rounded-tile border border-edge-rule bg-surface-inset p-0.5",children:i.map(e=>(0,a.jsx)("button",{type:"button",onClick:()=>s(e.years),className:`font-num text-[10px] px-2 py-0.5 rounded-tile transition-colors ${t===e.years?"bg-surface-raised text-txt-1 font-semibold":"text-txt-3 hover:text-txt-1"}`,children:e.label},e.label))}),(0,a.jsxs)("span",{className:"font-num text-[10px] tabular-nums text-txt-3",children:[c.length.toLocaleString("en-IN")," days"]})]}),(0,a.jsx)("div",{className:"grid grid-cols-1 gap-5 sm:grid-cols-2",children:l.map(e=>{let t=c.map(t=>({time:t.date,value:t[e.key]}));return(0,a.jsxs)("div",{children:[(0,a.jsx)("p",{className:"mb-1.5 font-num text-[10px] uppercase tracking-wider text-txt-3",children:e.label}),(0,a.jsx)(r.AtlasLightweightChart,{height:148,precision:0,series:[{name:e.label,color:e.color,data:t}]})]},e.key)})})]})}},91645:e=>{"use strict";e.exports=require("net")},98631:(e,t,s)=>{Promise.resolve().then(s.t.bind(s,85814,23)),Promise.resolve().then(s.bind(s,90476)),Promise.resolve().then(s.bind(s,99769)),Promise.resolve().then(s.bind(s,22337))},99769:(e,t,s)=>{"use strict";s.d(t,{SectorLeadershipBoard:()=>v});var a=s(60687),n=s(43210),r=s(85814),o=s.n(r),l=s(66614);let i={sm:{h:8,w:4,gap:2},md:{h:11,w:6,gap:2.5},lg:{h:15,w:7,gap:3}};function c({decile:e,size:t="md"}){let s=i[t],n=(0,l.c)(e);return(0,a.jsx)("span",{className:"inline-flex items-center",style:{gap:s.gap},"aria-hidden":"true",children:Array.from({length:10},(t,r)=>{let o=null!=e&&r<e;return(0,a.jsx)("span",{style:{height:s.h,width:s.w,borderRadius:1.5,background:o?n:"var(--color-surface-inset)",boxShadow:o?void 0:"inset 0 0 0 1px var(--color-edge-rule)"}},r)})})}var d=s(22337);let m=[["d_tech","Technical"],["d_fund","Fundamental"],["d_cat","Catalyst"],["d_flow","Flow"],["d_val","Value"]];function _({d:e}){return null==e?(0,a.jsx)("span",{className:"font-num text-[11px] text-txt-3",children:"—"}):(0,a.jsxs)("span",{className:"inline-block rounded px-1.5 py-0.5 font-num text-[11px] font-medium tabular-nums",style:{background:`color-mix(in srgb, ${(0,l.c)(e)} 22%, transparent)`,color:(0,l.c)(e)},children:["D",e]})}function u({name:e,stocks:t}){let s=[...t].sort((e,t)=>(t.strength??0)-(e.strength??0));return(0,a.jsxs)("div",{className:"mt-2 mb-3 overflow-x-auto rounded-tile border border-edge-rule bg-surface-base/60",children:[(0,a.jsxs)("div",{className:"flex items-center justify-between px-3 pt-2.5",children:[(0,a.jsxs)("span",{className:"font-sans text-[12px] text-txt-2",children:[(0,a.jsx)("span",{className:"font-medium text-txt-1",children:e})," — every stock’s decile (1–10) per lens. Higher = stronger; click a name to open it."]}),(0,a.jsx)(o(),{href:`/sectors/${encodeURIComponent(e)}`,className:"shrink-0 font-num text-[11px] text-brand hover:underline",children:"Open sector →"})]}),(0,a.jsxs)("table",{className:"tbl-centered mt-1.5 w-full border-collapse",children:[(0,a.jsx)("thead",{children:(0,a.jsxs)("tr",{className:"border-b border-edge-hair",children:[(0,a.jsx)("th",{className:"px-3 py-1.5 text-left font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3",children:"Stock"}),m.map(([,e])=>(0,a.jsxs)("th",{className:"px-2 py-1.5 text-right font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3",children:[e,(0,a.jsx)(d.TermInfo,{term:"decile"})]},e)),(0,a.jsxs)("th",{className:"px-3 py-1.5 text-right font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3",children:["Leads",(0,a.jsx)(d.TermInfo,{term:"lead"})]})]})}),(0,a.jsx)("tbody",{children:s.map(e=>(0,a.jsxs)("tr",{className:"border-b border-edge-hair/50 last:border-0 hover:bg-surface-raised",children:[(0,a.jsxs)("td",{className:"px-3 py-1.5",children:[(0,a.jsx)(o(),{href:`/stocks/${e.symbol}`,className:"font-num text-[12px] font-medium text-txt-1 hover:text-brand",children:e.symbol}),e.name&&(0,a.jsx)("span",{className:"ml-1.5 hidden truncate font-sans text-[11px] text-txt-3 sm:inline",children:e.name})]}),m.map(([t])=>(0,a.jsx)("td",{className:"px-2 py-1.5 text-right",children:(0,a.jsx)(_,{d:e[t]})},t)),(0,a.jsxs)("td",{className:"px-3 py-1.5 text-right font-num text-[11px] tabular-nums text-txt-2",children:[e.lead,(0,a.jsx)("span",{className:"text-txt-3",children:"/4"})]})]},e.symbol))})]})]})}let x=e=>null==e?"—":`${e>=0?"+":"−"}${Math.abs(100*e).toFixed(1)}`,p=e=>null==e?"text-txt-3":e>5e-4?"text-sig-pos":e<-5e-4?"text-sig-neg":"text-txt-2",h=(e,t)=>null==e?"—":null!=t?`${e}/${t}`:`${e}`,f="px-2 py-1 text-right font-num text-[9px] font-medium uppercase tracking-[0.1em] text-txt-3";function b({s:e,open:t,onToggle:s}){let n=e.avg>=6?"var(--color-sig-pos)":e.avg<4?"var(--color-sig-neg)":"var(--color-txt-1)";return(0,a.jsxs)("tr",{onClick:s,"aria-expanded":t,className:`cursor-pointer border-b border-edge-hair/60 transition-colors hover:bg-surface-raised ${t?"bg-surface-raised":""}`,children:[(0,a.jsx)("td",{className:"px-2 py-1.5",children:(0,a.jsxs)("span",{className:"flex items-center gap-1.5 truncate font-sans text-[12.5px] font-medium text-txt-1",children:[(0,a.jsx)("span",{className:"font-num text-[10px] text-txt-3",children:t?"▾":"▸"}),e.name]})}),(0,a.jsx)("td",{className:"px-2 py-1.5",children:(0,a.jsxs)("span",{className:"flex items-center justify-end gap-1.5",children:[(0,a.jsx)(c,{decile:Math.round(e.avg),size:"sm"}),(0,a.jsx)("span",{className:"w-[34px] shrink-0 text-right font-num text-[12px] tabular-nums",style:{color:n},children:e.avg.toFixed(1)})]})}),(0,a.jsx)("td",{className:`px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums ${p(e.rs_1w)}`,children:x(e.rs_1w)}),(0,a.jsx)("td",{className:`px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums ${p(e.rs_1m)}`,children:x(e.rs_1m)}),(0,a.jsx)("td",{className:`px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums ${p(e.rs_3m)}`,children:x(e.rs_3m)}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-2",children:h(e.ema21,e.emaTotal)}),(0,a.jsx)("td",{className:"px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-2",children:h(e.ema50,e.emaTotal)})]})}function g({rows:e,open:t,toggle:s}){return(0,a.jsxs)("table",{className:"tbl-centered w-full border-collapse",children:[(0,a.jsx)("thead",{children:(0,a.jsxs)("tr",{className:"border-b border-edge-rule",children:[(0,a.jsx)("th",{className:"px-2 py-1 text-left font-num text-[9px] font-medium uppercase tracking-[0.1em] text-txt-3",children:"Sector"}),(0,a.jsxs)("th",{className:f,children:["Conviction",(0,a.jsx)(d.TermInfo,{term:"strength"})]}),(0,a.jsxs)("th",{className:f,title:"Sector index vs Nifty 50, 1 week",children:["RS 1W",(0,a.jsx)(d.TermInfo,{term:"rs"})]}),(0,a.jsxs)("th",{className:f,title:"Sector index vs Nifty 50, 1 month",children:["RS 1M",(0,a.jsx)(d.TermInfo,{term:"rs"})]}),(0,a.jsxs)("th",{className:f,title:"Sector index vs Nifty 50, 3 months",children:["RS 3M",(0,a.jsx)(d.TermInfo,{term:"rs"})]}),(0,a.jsxs)("th",{className:f,title:"Constituents above their 21-EMA",children:[">EMA21",(0,a.jsx)(d.TermInfo,{term:"above_ema_count"})]}),(0,a.jsxs)("th",{className:f,title:"Constituents above their 50-EMA",children:[">EMA50",(0,a.jsx)(d.TermInfo,{term:"above_ema_count"})]})]})}),(0,a.jsx)("tbody",{children:e.map(e=>(0,a.jsx)(b,{s:e,open:t===e.name,onToggle:()=>s(e.name)},e.name))})]})}function v({top:e,weak:t,stocksBySector:s}){let[r,o]=(0,n.useState)(null),l=e=>o(t=>t===e?null:e);return(0,a.jsxs)("div",{className:"space-y-4",children:[(0,a.jsxs)("div",{children:[(0,a.jsx)("p",{className:"mb-1 font-num text-[9px] uppercase tracking-[0.14em] text-sig-pos",children:"Leading \xb7 strongest conviction"}),(0,a.jsx)(g,{rows:e,open:r,toggle:l})]}),(0,a.jsxs)("div",{children:[(0,a.jsx)("p",{className:"mb-1 font-num text-[9px] uppercase tracking-[0.14em] text-sig-neg",children:"Lagging \xb7 weakest conviction"}),(0,a.jsx)(g,{rows:t,open:r,toggle:l})]}),(0,a.jsx)("p",{className:"font-num text-[9.5px] text-txt-3",children:"Conviction = avg constituent decile (1–10). RS = sector index minus Nifty 50 over each window (% pts). >EMA21 / >EMA50 = constituents above that EMA, of the sector’s tracked count. Click a row for the per-stock decile breakdown."}),r&&(0,a.jsx)(u,{name:r,stocks:s[r]??[]})]})}}};var t=require("../webpack-runtime.js");t.C(e);var s=e=>t(t.s=e),a=t.X(0,[447,971,247,633,826,504,793,763],()=>s(54747));module.exports=a})();