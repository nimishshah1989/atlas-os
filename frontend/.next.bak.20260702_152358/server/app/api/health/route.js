(()=>{var e={};e.id=772,e.ids=[772],e.modules={3295:e=>{"use strict";e.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},5069:(e,a,t)=>{"use strict";t.d(a,{A:()=>n});var s=t(43971);if(!process.env.ATLAS_DB_URL)throw Error("ATLAS_DB_URL is not defined. Set it in .env.local.");let l=process.env.ATLAS_DB_URL.includes("pooler.supabase.com");if(process.env.ATLAS_DB_URL.includes(":6543/"))throw Error("ATLAS_DB_URL must use session-mode pooler (port 5432), not transaction-mode (port 6543). M13 audit trail relies on sql.begin() + SET LOCAL which requires a pinned connection.");let n=(0,s.A)(process.env.ATLAS_DB_URL,{max:14,idle_timeout:10,max_lifetime:300,connect_timeout:10,prepare:!l,ssl:!!process.env.ATLAS_DB_URL.includes("sslmode=require")&&{rejectUnauthorized:!1}})},10592:(e,a,t)=>{"use strict";t.d(a,{A7:()=>c,A9:()=>g,Cr:()=>o,Om:()=>A,P:()=>n,aW:()=>p,en:()=>l,j5:()=>h,lc:()=>i,pg:()=>m,v9:()=>f,zP:()=>_});var s=t(5069);async function l(e=30){return await (0,s.A)`
    SELECT
      run_id::text       AS run_id,
      script_name,
      milestone,
      phase,
      started_at,
      ended_at,
      status,
      rows_written,
      error_message,
      host,
      EXTRACT(EPOCH FROM (ended_at - started_at))::int AS duration_seconds
    FROM atlas_foundation.atlas_pipeline_runs
    ORDER BY started_at DESC
    LIMIT ${e}
  `}async function n(){return await (0,s.A)`
    SELECT DISTINCT ON (script_name)
      run_id::text       AS run_id,
      script_name,
      milestone,
      phase,
      started_at,
      ended_at,
      status,
      rows_written,
      error_message,
      host,
      EXTRACT(EPOCH FROM (ended_at - started_at))::int AS duration_seconds
    FROM atlas_foundation.atlas_pipeline_runs
    ORDER BY script_name, started_at DESC
  `}let r=[{schema:"atlas_foundation",name:"technical_daily",date_col:"date"},{schema:"atlas_foundation",name:"atlas_lens_scores_daily",date_col:"date"},{schema:"atlas_foundation",name:"sector_lens_daily",date_col:"date"},{schema:"atlas_foundation",name:"fund_rank_daily",date_col:"date"},{schema:"atlas_foundation",name:"atlas_index_metrics_daily",date_col:"date"},{schema:"atlas_foundation",name:"atlas_market_regime_daily",date_col:"date"},{schema:"atlas_foundation",name:"breadth_nifty500_daily",date_col:"date"}];async function o(){let e=new Date;return e.setHours(0,0,0,0),Promise.all(r.map(async({schema:a,name:t,date_col:l})=>{if(l){let n=(await (0,s.A)`
          SELECT
            (SELECT reltuples::bigint FROM pg_class
              JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
              WHERE nspname = ${a} AND relname = ${t})::text AS row_count,
            MAX(${(0,s.A)(l)}) AS latest_date
          FROM ${(0,s.A)(a)}.${(0,s.A)(t)}
        `)[0],r=n?.latest_date?new Date(n.latest_date):null,o=r?Math.floor((e.getTime()-r.getTime())/864e5):null;return{table_name:t,row_count:Number(n?.row_count??0),latest_date:r,lag_days:o}}{let e=await (0,s.A)`
          SELECT reltuples::bigint::text AS row_count
          FROM pg_class
          JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
          WHERE nspname = ${a} AND relname = ${t}
        `;return{table_name:t,row_count:Number(e[0]?.row_count??0),latest_date:null,lag_days:null}}}))}function _(e){return"atlas_fund_lens_monthly"===e?35:2}let d=[{table:"ohlcv_stock",date_col:"date",label:"Stock prices (OHLCV)",cadence:"Daily",feeds:"Returns \xb7 RS \xb7 technicals",ok:4,warn:7},{table:"technical_daily",date_col:"date",label:"Technical metrics",cadence:"Daily",feeds:"RS \xb7 EMA \xb7 RSI \xb7 returns",ok:4,warn:7},{table:"atlas_lens_scores_daily",date_col:"date",label:"Lens scores + composite",cadence:"Daily",feeds:"Conviction score \xb7 deciles",ok:4,warn:7},{table:"sector_lens_daily",date_col:"date",label:"Sector lens vectors",cadence:"Daily",feeds:"Sector pages",ok:4,warn:7},{table:"atlas_index_metrics_daily",date_col:"date",label:"Index returns",cadence:"Daily",feeds:"Sector RS \xb7 benchmarks",ok:4,warn:7},{table:"mv_sector_cards",date_col:"as_of_date",label:"Sector cards",cadence:"Daily",feeds:"/sectors heatmap + hero",ok:4,warn:7},{table:"mv_sector_breadth",date_col:"as_of_date",label:"Sector breadth",cadence:"Daily",feeds:"Breadth table",ok:4,warn:7},{table:"de_mf_nav_daily",date_col:"nav_date",label:"Fund NAVs",cadence:"Daily",feeds:"Fund pages",ok:4,warn:7},{table:"atlas_fund_scorecard",date_col:"snapshot_date",label:"Fund scorecard",cadence:"Daily",feeds:"Fund ranking + score",ok:7,warn:14},{table:"de_mf_holdings",date_col:"as_of_date",label:"Fund holdings",cadence:"Monthly",feeds:"Fund roll-ups + look-through",ok:40,warn:60},{table:"de_etf_holdings",date_col:"as_of_date",label:"ETF holdings",cadence:"Monthly",feeds:"ETF roll-ups + look-through",ok:40,warn:60}];async function i(){let e=new Date;return e.setHours(0,0,0,0),Promise.all(d.map(async a=>{let t=(await (0,s.A)`
        SELECT
          (SELECT reltuples::bigint FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = 'atlas_foundation' AND relname = ${a.table})::text AS row_count,
          MAX(${(0,s.A)(a.date_col)}) AS latest_date
        FROM atlas_foundation.${(0,s.A)(a.table)}
      `.catch(()=>[]))[0],l=t?.latest_date?new Date(t.latest_date):null,n=l?Math.floor((e.getTime()-l.getTime())/864e5):null,r=null==n?"red":n<=a.ok?"green":n<=a.warn?"amber":"red";return{table:a.table,label:a.label,cadence:a.cadence,feeds:a.feeds,latest_date:l,lag_days:n,row_count:Number(t?.row_count??0),rag:r}}))}function c(e){return e.some(e=>"red"===e.rag)?"red":e.some(e=>"amber"===e.rag)?"amber":"green"}let u=[{name:"ohlcv_stock",date_col:"date"},{name:"ohlcv_etf",date_col:"date"},{name:"index_prices",date_col:"date"},{name:"de_mf_nav_daily",date_col:"nav_date"},{name:"de_mf_holdings",date_col:"as_of_date"},{name:"de_etf_holdings",date_col:"as_of_date"},{name:"delivery_daily",date_col:"date"}];async function m(){let e=new Date;return e.setHours(0,0,0,0),Promise.all(u.map(async({name:a,date_col:t})=>{let l=(await (0,s.A)`
        SELECT
          (SELECT reltuples::bigint FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = 'atlas_foundation' AND relname = ${a})::text AS row_count,
          MAX(${(0,s.A)(t)}) AS latest_date
        FROM atlas_foundation.${(0,s.A)(a)}
      `)[0],n=l?.latest_date?new Date(l.latest_date):null,r=n?Math.floor((e.getTime()-n.getTime())/864e5):null;return{table_name:a,row_count:Number(l?.row_count??0),latest_date:n,lag_days:r}}))}function p(e){return 2}async function f(){let e=await (0,s.A)`
    SELECT MAX(data_date) AS d FROM atlas_foundation.atlas_health_daily
  `,a=e[0]?.d;return a?await (0,s.A)`
    SELECT
      data_date,
      table_name,
      metric_name,
      value_today::float8       AS value_today,
      value_prior_day::float8   AS value_prior_day,
      rolling_14d_avg::float8   AS rolling_14d_avg,
      rolling_14d_std::float8   AS rolling_14d_std,
      pct_change_dod::float8    AS pct_change_dod,
      z_score::float8           AS z_score,
      is_anomaly,
      severity,
      notes
    FROM atlas_foundation.atlas_health_daily
    WHERE data_date = ${a}
      AND is_anomaly = TRUE
    ORDER BY
      CASE severity
        WHEN 'critical' THEN 0
        WHEN 'warn'     THEN 1
        WHEN 'info'     THEN 2
        ELSE 3
      END,
      table_name, metric_name
  `:[]}async function h(e=30){return await (0,s.A)`
    SELECT
      run_id::text AS run_id,
      validator,
      ran_at,
      total_checks,
      failures,
      status
    FROM atlas_foundation.atlas_validator_results
    WHERE ran_at >= NOW() - (${e}::int * INTERVAL '1 day')
    ORDER BY validator, ran_at DESC
  `}async function g(){return await (0,s.A)`
    SELECT DISTINCT ON (validator)
      run_id::text AS run_id,
      validator,
      ran_at,
      total_checks,
      failures,
      status
    FROM atlas_foundation.atlas_validator_results
    ORDER BY validator, ran_at DESC
  `}async function A(){let[e,a,t]=await Promise.all([(0,s.A)`
      SELECT MAX(computed_at) AS ts FROM atlas_foundation.atlas_health_daily
    `,(0,s.A)`
      SELECT severity, COUNT(*)::text AS n
      FROM atlas_foundation.atlas_health_daily
      WHERE data_date = (SELECT MAX(data_date) FROM atlas_foundation.atlas_health_daily)
        AND is_anomaly = TRUE
      GROUP BY severity
    `,(0,s.A)`
      SELECT DISTINCT ON (validator) validator, status
      FROM atlas_foundation.atlas_validator_results
      ORDER BY validator, ran_at DESC
    `]),l=e[0]?.ts??null,n={};for(let e of a)n[e.severity]=Number(e.n);let r=t.filter(e=>"FAIL"===e.status).length;return(n.critical??0)>0||r>0?{level:"red",message:`${n.critical??0} critical anomalies \xb7 ${r} validator FAILs`,last_health_check:l}:(n.warn??0)>0?{level:"yellow",message:`${n.warn} warnings`,last_health_check:l}:{level:"green",message:"System healthy",last_health_check:l}}},10846:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},21820:e=>{"use strict";e.exports=require("os")},27910:e=>{"use strict";e.exports=require("stream")},29021:e=>{"use strict";e.exports=require("fs")},29294:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-async-storage.external.js")},34631:e=>{"use strict";e.exports=require("tls")},43076:(e,a,t)=>{"use strict";t.r(a),t.d(a,{patchFetch:()=>f,routeModule:()=>c,serverHooks:()=>p,workAsyncStorage:()=>u,workUnitAsyncStorage:()=>m});var s={};t.r(s),t.d(s,{GET:()=>i,dynamic:()=>d});var l=t(96559),n=t(48088),r=t(37719),o=t(32190),_=t(10592);let d="force-dynamic";async function i(){let[e,a,t,s]=await Promise.all([(0,_.Om)(),(0,_.Cr)(),(0,_.pg)(),(0,_.en)(10)]),l=a.filter(e=>null!=e.lag_days&&e.lag_days>(0,_.zP)(e.table_name)).map(e=>({table:e.table_name,lag_days:e.lag_days})),n=t.filter(e=>null!=e.lag_days&&e.lag_days>(0,_.aW)(e.table_name)).map(e=>({table:e.table_name,lag_days:e.lag_days})),r=s.filter(e=>"failed"===e.status).map(e=>({script:e.script_name,started_at:e.started_at,error:e.error_message})),d={status:e.level,message:e.message,checked_at:new Date().toISOString(),last_health_check:e.last_health_check,pipeline:{recent_failures:r},freshness:{stale_tables:l,jip_stale_tables:n}},i="red"===e.level?503:200;return o.NextResponse.json(d,{status:i})}let c=new l.AppRouteRouteModule({definition:{kind:n.RouteKind.APP_ROUTE,page:"/api/health/route",pathname:"/api/health",filename:"route",bundlePath:"app/api/health/route"},resolvedPagePath:"/home/ubuntu/atlas-os/frontend/src/app/api/health/route.ts",nextConfigOutput:"",userland:s}),{workAsyncStorage:u,workUnitAsyncStorage:m,serverHooks:p}=c;function f(){return(0,r.patchFetch)({workAsyncStorage:u,workUnitAsyncStorage:m})}},44870:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-route.runtime.prod.js")},55511:e=>{"use strict";e.exports=require("crypto")},63033:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},74998:e=>{"use strict";e.exports=require("perf_hooks")},78335:()=>{},91645:e=>{"use strict";e.exports=require("net")},96487:()=>{}};var a=require("../../../webpack-runtime.js");a.C(e);var t=e=>a(a.s=e),s=a.X(0,[447,971,580],()=>t(43076));module.exports=s})();