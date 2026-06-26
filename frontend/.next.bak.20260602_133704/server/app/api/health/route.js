(()=>{var a={};a.id=2772,a.ids=[2772],a.modules={3295:a=>{"use strict";a.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},5069:(a,e,t)=>{"use strict";t.d(e,{A:()=>r});var s=t(43971);if(!process.env.ATLAS_DB_URL)throw Error("ATLAS_DB_URL is not defined. Set it in .env.local.");let l=process.env.ATLAS_DB_URL.includes("pooler.supabase.com");if(process.env.ATLAS_DB_URL.includes(":6543/"))throw Error("ATLAS_DB_URL must use session-mode pooler (port 5432), not transaction-mode (port 6543). M13 audit trail relies on sql.begin() + SET LOCAL which requires a pinned connection.");let r=(0,s.A)(process.env.ATLAS_DB_URL,{max:14,idle_timeout:10,max_lifetime:300,connect_timeout:10,prepare:!l,ssl:!!process.env.ATLAS_DB_URL.includes("sslmode=require")&&{rejectUnauthorized:!1}})},10592:(a,e,t)=>{"use strict";t.d(e,{A9:()=>p,Cr:()=>n,Om:()=>h,P:()=>r,aW:()=>c,en:()=>l,j5:()=>m,pg:()=>o,v9:()=>u,zP:()=>i});var s=t(5069);async function l(a=30){return await (0,s.A)`
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
    FROM atlas.atlas_pipeline_runs
    ORDER BY started_at DESC
    LIMIT ${a}
  `}async function r(){return await (0,s.A)`
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
    FROM atlas.atlas_pipeline_runs
    ORDER BY script_name, started_at DESC
  `}let _=[{schema:"atlas",name:"atlas_index_metrics_daily",date_col:"date"},{schema:"atlas",name:"atlas_sector_metrics_daily",date_col:"date"},{schema:"atlas",name:"atlas_sector_states_daily",date_col:"date"},{schema:"atlas",name:"atlas_market_regime_daily",date_col:"date"},{schema:"atlas",name:"atlas_stock_metrics_daily",date_col:"date"},{schema:"atlas",name:"atlas_stock_states_daily",date_col:"date"},{schema:"atlas",name:"atlas_etf_metrics_daily",date_col:"date"},{schema:"atlas",name:"atlas_etf_states_daily",date_col:"date"},{schema:"atlas",name:"atlas_fund_metrics_daily",date_col:"nav_date"},{schema:"atlas",name:"atlas_fund_lens_monthly",date_col:"as_of_date"},{schema:"atlas",name:"atlas_fund_states_daily",date_col:"date"},{schema:"atlas",name:"atlas_stock_decisions_daily",date_col:"date"},{schema:"atlas",name:"atlas_etf_decisions_daily",date_col:"date"},{schema:"atlas",name:"atlas_fund_decisions_daily",date_col:"date"},{schema:"us_atlas",name:"stock_ohlcv",date_col:"date"},{schema:"us_atlas",name:"atlas_etf_metrics_daily",date_col:"date"},{schema:"us_atlas",name:"atlas_etf_states_daily",date_col:"date"},{schema:"us_atlas",name:"atlas_stock_metrics_daily",date_col:"date"},{schema:"us_atlas",name:"atlas_stock_states_daily",date_col:"date"},{schema:"us_atlas",name:"atlas_market_regime_daily",date_col:"date"},{schema:"global_atlas",name:"stock_ohlcv",date_col:"date"},{schema:"global_atlas",name:"atlas_etf_metrics_daily",date_col:"date"},{schema:"global_atlas",name:"atlas_etf_states_daily",date_col:"date"},{schema:"global_atlas",name:"atlas_market_regime_daily",date_col:"date"}];async function n(){let a=new Date;return a.setHours(0,0,0,0),Promise.all(_.map(async({schema:e,name:t,date_col:l})=>{let r="atlas"===e?t:`${e}.${t}`;if(l){let _=(await (0,s.A)`
          SELECT
            (SELECT reltuples::bigint FROM pg_class
              JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
              WHERE nspname = ${e} AND relname = ${t})::text AS row_count,
            MAX(${(0,s.A)(l)}) AS latest_date
          FROM ${(0,s.A)(e)}.${(0,s.A)(t)}
        `)[0],n=_?.latest_date?new Date(_.latest_date):null,i=n?Math.floor((a.getTime()-n.getTime())/864e5):null;return{table_name:r,row_count:Number(_?.row_count??0),latest_date:n,lag_days:i}}{let a=await (0,s.A)`
          SELECT reltuples::bigint::text AS row_count
          FROM pg_class
          JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
          WHERE nspname = ${e} AND relname = ${t}
        `;return{table_name:r,row_count:Number(a[0]?.row_count??0),latest_date:null,lag_days:null}}}))}function i(a){return"atlas_fund_lens_monthly"===a?35:2}let d=[{name:"de_source_files",date_col:"created_at"},{name:"de_equity_ohlcv",date_col:"date"},{name:"de_index_prices",date_col:"date"},{name:"de_mf_nav_daily",date_col:"nav_date"},{name:"de_etf_ohlcv",date_col:"date"},{name:"de_global_prices",date_col:"date"},{name:"de_etf_holdings",date_col:"as_of_date"},{name:"de_cron_run",date_col:"started_at"}];async function o(){let a=new Date;return a.setHours(0,0,0,0),Promise.all(d.map(async({name:e,date_col:t})=>{let l=(await (0,s.A)`
        SELECT
          (SELECT reltuples::bigint FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = 'public' AND relname = ${e})::text AS row_count,
          MAX(${(0,s.A)(t)}) AS latest_date
        FROM public.${(0,s.A)(e)}
      `)[0],r=l?.latest_date?new Date(l.latest_date):null,_=r?Math.floor((a.getTime()-r.getTime())/864e5):null;return{table_name:e,row_count:Number(l?.row_count??0),latest_date:r,lag_days:_}}))}function c(a){return 2}async function u(){let a=await (0,s.A)`
    SELECT MAX(data_date) AS d FROM atlas.atlas_health_daily
  `,e=a[0]?.d;return e?await (0,s.A)`
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
    FROM atlas.atlas_health_daily
    WHERE data_date = ${e}
      AND is_anomaly = TRUE
    ORDER BY
      CASE severity
        WHEN 'critical' THEN 0
        WHEN 'warn'     THEN 1
        WHEN 'info'     THEN 2
        ELSE 3
      END,
      table_name, metric_name
  `:[]}async function m(a=30){return await (0,s.A)`
    SELECT
      run_id::text AS run_id,
      validator,
      ran_at,
      total_checks,
      failures,
      status
    FROM atlas.atlas_validator_results
    WHERE ran_at >= NOW() - (${a}::int * INTERVAL '1 day')
    ORDER BY validator, ran_at DESC
  `}async function p(){return await (0,s.A)`
    SELECT DISTINCT ON (validator)
      run_id::text AS run_id,
      validator,
      ran_at,
      total_checks,
      failures,
      status
    FROM atlas.atlas_validator_results
    ORDER BY validator, ran_at DESC
  `}async function h(){let[a,e,t]=await Promise.all([(0,s.A)`
      SELECT MAX(computed_at) AS ts FROM atlas.atlas_health_daily
    `,(0,s.A)`
      SELECT severity, COUNT(*)::text AS n
      FROM atlas.atlas_health_daily
      WHERE data_date = (SELECT MAX(data_date) FROM atlas.atlas_health_daily)
        AND is_anomaly = TRUE
      GROUP BY severity
    `,(0,s.A)`
      SELECT DISTINCT ON (validator) validator, status
      FROM atlas.atlas_validator_results
      ORDER BY validator, ran_at DESC
    `]),l=a[0]?.ts??null,r={};for(let a of e)r[a.severity]=Number(a.n);let _=t.filter(a=>"FAIL"===a.status).length;return(r.critical??0)>0||_>0?{level:"red",message:`${r.critical??0} critical anomalies \xb7 ${_} validator FAILs`,last_health_check:l}:(r.warn??0)>0?{level:"yellow",message:`${r.warn} warnings`,last_health_check:l}:{level:"green",message:"System healthy",last_health_check:l}}},10846:a=>{"use strict";a.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},21820:a=>{"use strict";a.exports=require("os")},27910:a=>{"use strict";a.exports=require("stream")},29021:a=>{"use strict";a.exports=require("fs")},29294:a=>{"use strict";a.exports=require("next/dist/server/app-render/work-async-storage.external.js")},34631:a=>{"use strict";a.exports=require("tls")},43076:(a,e,t)=>{"use strict";t.r(e),t.d(e,{patchFetch:()=>h,routeModule:()=>c,serverHooks:()=>p,workAsyncStorage:()=>u,workUnitAsyncStorage:()=>m});var s={};t.r(s),t.d(s,{GET:()=>o,dynamic:()=>d});var l=t(96559),r=t(48088),_=t(37719),n=t(32190),i=t(10592);let d="force-dynamic";async function o(){let[a,e,t,s]=await Promise.all([(0,i.Om)(),(0,i.Cr)(),(0,i.pg)(),(0,i.en)(10)]),l=e.filter(a=>null!=a.lag_days&&a.lag_days>(0,i.zP)(a.table_name)).map(a=>({table:a.table_name,lag_days:a.lag_days})),r=t.filter(a=>null!=a.lag_days&&a.lag_days>(0,i.aW)(a.table_name)).map(a=>({table:a.table_name,lag_days:a.lag_days})),_=s.filter(a=>"failed"===a.status).map(a=>({script:a.script_name,started_at:a.started_at,error:a.error_message})),d={status:a.level,message:a.message,checked_at:new Date().toISOString(),last_health_check:a.last_health_check,pipeline:{recent_failures:_},freshness:{stale_tables:l,jip_stale_tables:r}},o="red"===a.level?503:200;return n.NextResponse.json(d,{status:o})}let c=new l.AppRouteRouteModule({definition:{kind:r.RouteKind.APP_ROUTE,page:"/api/health/route",pathname:"/api/health",filename:"route",bundlePath:"app/api/health/route"},resolvedPagePath:"/home/ubuntu/atlas-os/frontend/src/app/api/health/route.ts",nextConfigOutput:"",userland:s}),{workAsyncStorage:u,workUnitAsyncStorage:m,serverHooks:p}=c;function h(){return(0,_.patchFetch)({workAsyncStorage:u,workUnitAsyncStorage:m})}},44870:a=>{"use strict";a.exports=require("next/dist/compiled/next-server/app-route.runtime.prod.js")},55511:a=>{"use strict";a.exports=require("crypto")},63033:a=>{"use strict";a.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},74998:a=>{"use strict";a.exports=require("perf_hooks")},78335:()=>{},91645:a=>{"use strict";a.exports=require("net")},96487:()=>{}};var e=require("../../../webpack-runtime.js");e.C(a);var t=a=>e(e.s=a),s=e.X(0,[4447,3971,580],()=>t(43076));module.exports=s})();