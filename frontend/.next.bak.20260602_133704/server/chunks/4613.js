exports.id=4613,exports.ids=[4613],exports.modules={5069:(e,a,t)=>{"use strict";t.d(a,{A:()=>r});var s=t(43971);if(!process.env.ATLAS_DB_URL)throw Error("ATLAS_DB_URL is not defined. Set it in .env.local.");let l=process.env.ATLAS_DB_URL.includes("pooler.supabase.com");if(process.env.ATLAS_DB_URL.includes(":6543/"))throw Error("ATLAS_DB_URL must use session-mode pooler (port 5432), not transaction-mode (port 6543). M13 audit trail relies on sql.begin() + SET LOCAL which requires a pinned connection.");let r=(0,s.A)(process.env.ATLAS_DB_URL,{max:14,idle_timeout:10,max_lifetime:300,connect_timeout:10,prepare:!l,ssl:!!process.env.ATLAS_DB_URL.includes("sslmode=require")&&{rejectUnauthorized:!1}})},10592:(e,a,t)=>{"use strict";t.d(a,{A9:()=>u,Cr:()=>i,Om:()=>p,P:()=>r,aW:()=>_,en:()=>l,j5:()=>h,pg:()=>c,v9:()=>m,zP:()=>o});var s=t(5069);async function l(e=30){return await (0,s.A)`
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
    LIMIT ${e}
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
  `}let n=[{schema:"atlas",name:"atlas_index_metrics_daily",date_col:"date"},{schema:"atlas",name:"atlas_sector_metrics_daily",date_col:"date"},{schema:"atlas",name:"atlas_sector_states_daily",date_col:"date"},{schema:"atlas",name:"atlas_market_regime_daily",date_col:"date"},{schema:"atlas",name:"atlas_stock_metrics_daily",date_col:"date"},{schema:"atlas",name:"atlas_stock_states_daily",date_col:"date"},{schema:"atlas",name:"atlas_etf_metrics_daily",date_col:"date"},{schema:"atlas",name:"atlas_etf_states_daily",date_col:"date"},{schema:"atlas",name:"atlas_fund_metrics_daily",date_col:"nav_date"},{schema:"atlas",name:"atlas_fund_lens_monthly",date_col:"as_of_date"},{schema:"atlas",name:"atlas_fund_states_daily",date_col:"date"},{schema:"atlas",name:"atlas_stock_decisions_daily",date_col:"date"},{schema:"atlas",name:"atlas_etf_decisions_daily",date_col:"date"},{schema:"atlas",name:"atlas_fund_decisions_daily",date_col:"date"},{schema:"us_atlas",name:"stock_ohlcv",date_col:"date"},{schema:"us_atlas",name:"atlas_etf_metrics_daily",date_col:"date"},{schema:"us_atlas",name:"atlas_etf_states_daily",date_col:"date"},{schema:"us_atlas",name:"atlas_stock_metrics_daily",date_col:"date"},{schema:"us_atlas",name:"atlas_stock_states_daily",date_col:"date"},{schema:"us_atlas",name:"atlas_market_regime_daily",date_col:"date"},{schema:"global_atlas",name:"stock_ohlcv",date_col:"date"},{schema:"global_atlas",name:"atlas_etf_metrics_daily",date_col:"date"},{schema:"global_atlas",name:"atlas_etf_states_daily",date_col:"date"},{schema:"global_atlas",name:"atlas_market_regime_daily",date_col:"date"}];async function i(){let e=new Date;return e.setHours(0,0,0,0),Promise.all(n.map(async({schema:a,name:t,date_col:l})=>{let r="atlas"===a?t:`${a}.${t}`;if(l){let n=(await (0,s.A)`
          SELECT
            (SELECT reltuples::bigint FROM pg_class
              JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
              WHERE nspname = ${a} AND relname = ${t})::text AS row_count,
            MAX(${(0,s.A)(l)}) AS latest_date
          FROM ${(0,s.A)(a)}.${(0,s.A)(t)}
        `)[0],i=n?.latest_date?new Date(n.latest_date):null,o=i?Math.floor((e.getTime()-i.getTime())/864e5):null;return{table_name:r,row_count:Number(n?.row_count??0),latest_date:i,lag_days:o}}{let e=await (0,s.A)`
          SELECT reltuples::bigint::text AS row_count
          FROM pg_class
          JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
          WHERE nspname = ${a} AND relname = ${t}
        `;return{table_name:r,row_count:Number(e[0]?.row_count??0),latest_date:null,lag_days:null}}}))}function o(e){return"atlas_fund_lens_monthly"===e?35:2}let d=[{name:"de_source_files",date_col:"created_at"},{name:"de_equity_ohlcv",date_col:"date"},{name:"de_index_prices",date_col:"date"},{name:"de_mf_nav_daily",date_col:"nav_date"},{name:"de_etf_ohlcv",date_col:"date"},{name:"de_global_prices",date_col:"date"},{name:"de_etf_holdings",date_col:"as_of_date"},{name:"de_cron_run",date_col:"started_at"}];async function c(){let e=new Date;return e.setHours(0,0,0,0),Promise.all(d.map(async({name:a,date_col:t})=>{let l=(await (0,s.A)`
        SELECT
          (SELECT reltuples::bigint FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = 'public' AND relname = ${a})::text AS row_count,
          MAX(${(0,s.A)(t)}) AS latest_date
        FROM public.${(0,s.A)(a)}
      `)[0],r=l?.latest_date?new Date(l.latest_date):null,n=r?Math.floor((e.getTime()-r.getTime())/864e5):null;return{table_name:a,row_count:Number(l?.row_count??0),latest_date:r,lag_days:n}}))}function _(e){return 2}async function m(){let e=await (0,s.A)`
    SELECT MAX(data_date) AS d FROM atlas.atlas_health_daily
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
    FROM atlas.atlas_health_daily
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
    FROM atlas.atlas_validator_results
    WHERE ran_at >= NOW() - (${e}::int * INTERVAL '1 day')
    ORDER BY validator, ran_at DESC
  `}async function u(){return await (0,s.A)`
    SELECT DISTINCT ON (validator)
      run_id::text AS run_id,
      validator,
      ran_at,
      total_checks,
      failures,
      status
    FROM atlas.atlas_validator_results
    ORDER BY validator, ran_at DESC
  `}async function p(){let[e,a,t]=await Promise.all([(0,s.A)`
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
    `]),l=e[0]?.ts??null,r={};for(let e of a)r[e.severity]=Number(e.n);let n=t.filter(e=>"FAIL"===e.status).length;return(r.critical??0)>0||n>0?{level:"red",message:`${r.critical??0} critical anomalies \xb7 ${n} validator FAILs`,last_health_check:l}:(r.warn??0)>0?{level:"yellow",message:`${r.warn} warnings`,last_health_check:l}:{level:"green",message:"System healthy",last_health_check:l}}},14329:(e,a,t)=>{"use strict";t.r(a),t.d(a,{default:()=>l});var s=t(60687);function l({error:e,reset:a}){return(0,s.jsxs)("div",{className:"p-8 max-w-md mx-auto mt-16",children:[(0,s.jsx)("p",{className:"font-sans text-sm text-ink-secondary mb-4",children:"Something went wrong loading this page."}),(0,s.jsx)("button",{onClick:a,className:"font-sans text-sm text-accent underline",children:"Try again"})]})}t(43210)},20191:(e,a,t)=>{Promise.resolve().then(t.bind(t,30112))},21339:(e,a,t)=>{"use strict";t.r(a),t.d(a,{default:()=>p,metadata:()=>u});var s=t(37413),l=t(21338),r=t.n(l),n=t(50396),i=t.n(n),o=t(36080),d=t.n(o),c=t(61120);t(61135);var _=t(30112),m=t(10592);async function h(){let e="yellow",a="Unknown";try{let t=await (0,m.Om)();e=t.level,a=t.message}catch{}return(0,s.jsx)("span",{title:a,className:`inline-block w-2 h-2 rounded-full ${{green:"bg-signal-pos",yellow:"bg-signal-warn",red:"bg-signal-neg"}[e]}`})}let u={title:"Atlas-OS",description:"Fund manager research tool — Javeri Securities",robots:"noindex, nofollow"};function p({children:e}){return(0,s.jsx)("html",{lang:"en",className:`${r().variable} ${i().variable} ${d().variable}`,children:(0,s.jsxs)("body",{className:"bg-paper min-h-screen",children:[(0,s.jsx)(_.TopNav,{healthDot:(0,s.jsx)(c.Suspense,{fallback:(0,s.jsx)("span",{className:"inline-block w-2 h-2 rounded-full bg-paper-rule"}),children:(0,s.jsx)(h,{})})}),(0,s.jsx)("main",{className:"pt-20",children:e})]})})}},30112:(e,a,t)=>{"use strict";t.d(a,{TopNav:()=>l});var s=t(12907);(0,s.registerClientReference)(function(){throw Error("Attempted to call GROUPS() from the server but GROUPS is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/nav/TopNav.tsx","GROUPS");let l=(0,s.registerClientReference)(function(){throw Error("Attempted to call TopNav() from the server but TopNav is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/nav/TopNav.tsx","TopNav")},42901:(e,a,t)=>{Promise.resolve().then(t.bind(t,54431))},50738:(e,a,t)=>{"use strict";t.d(a,{TopNav:()=>_});var s=t(60687),l=t(85814),r=t.n(l),n=t(43210),i=t(16189),o=t(11860),d=t(12941);let c=[{key:"today",label:"MARKETS TODAY",links:[{href:"/",label:"Regime"},{href:"/india-pulse",label:"India Pulse"}]},{key:"deepdive",label:"DEEP DIVE",links:[{href:"/markets-rs",label:"Markets RS"},{href:"/sectors",label:"Sectors"},{href:"/stocks",label:"Stocks"},{href:"/etfs",label:"ETFs"},{href:"/funds",label:"Funds"}]},{key:"portfolios",label:"PORTFOLIOS",links:[{href:"/calls",label:"Calls"},{href:"/portfolios",label:"Custom Portfolios"}]},{key:"admin",label:"ADMIN",links:[{href:"/admin",label:"Overview & Health"},{href:"/setup",label:"Portfolio Setup"},{href:"/admin/thresholds",label:"Thresholds"},{href:"/admin/composite-proposals",label:"Signal Proposals"}]},{key:"reports",label:"REPORTS",links:[{href:"/intelligence/daily-brief",label:"Daily Brief"}]}];function _({healthDot:e}){let a=(0,i.usePathname)(),[t,l]=(0,n.useState)(!1),_=a.startsWith("/admin")||a.startsWith("/setup")||a.startsWith("/methodology")||a.startsWith("/health")?c[3]:a.startsWith("/intelligence/daily-brief")?c[4]:a.startsWith("/calls")||a.startsWith("/portfolios")?c[2]:a.startsWith("/india-pulse")?c[0]:a.startsWith("/markets-rs")||a.startsWith("/sectors")||a.startsWith("/stocks")||a.startsWith("/etfs")||a.startsWith("/funds")?c[1]:c[0];return(0,s.jsxs)(s.Fragment,{children:[(0,s.jsxs)("nav",{className:"fixed top-0 left-0 right-0 z-50 h-11 bg-paper border-b border-paper-rule flex items-center px-5 gap-1",children:[(0,s.jsx)(r(),{href:"/",className:"font-serif text-[15px] font-semibold text-ink-primary mr-3 shrink-0",children:"Atlas"}),(0,s.jsx)("div",{className:"hidden md:flex items-center gap-0.5",children:c.map(e=>(0,s.jsx)("button",{onClick:()=>{},className:`px-3 py-1 rounded-sm font-sans text-[12px] font-medium transition-colors ${_.key===e.key?"bg-ink-primary text-paper":"text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/30"}`,children:(0,s.jsx)(r(),{href:e.links[0].href,className:"block",children:e.label})},e.key))}),(0,s.jsxs)("div",{className:"ml-auto flex items-center gap-3",children:[e,(0,s.jsx)("button",{className:"md:hidden p-1 text-ink-secondary hover:text-ink-primary",onClick:()=>l(e=>!e),"aria-label":"Toggle menu",children:t?(0,s.jsx)(o.A,{size:18}):(0,s.jsx)(d.A,{size:18})})]})]}),(0,s.jsxs)("div",{className:"fixed top-11 left-0 right-0 z-40 h-9 bg-paper/95 border-b border-paper-rule/60 hidden md:flex items-center px-5 gap-1",children:[(0,s.jsx)("span",{className:"font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mr-3",children:_.label}),_.links.map(e=>{let t=a===e.href||"/"!==e.href&&a.startsWith(e.href);return(0,s.jsx)(r(),{href:e.href,className:`px-2.5 py-0.5 rounded-sm font-sans text-[11px] transition-colors ${t?"bg-teal/10 text-teal font-medium":"text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/30"}`,children:e.label},e.href)})]}),t&&(0,s.jsxs)("div",{className:"fixed inset-0 z-[60] md:hidden",children:[(0,s.jsx)("div",{className:"absolute inset-0 bg-ink-primary/20",onClick:()=>l(!1)}),(0,s.jsxs)("div",{className:"absolute top-0 left-0 bottom-0 w-72 bg-paper shadow-xl flex flex-col overflow-y-auto",children:[(0,s.jsxs)("div",{className:"flex items-center justify-between px-5 h-11 border-b border-paper-rule shrink-0",children:[(0,s.jsx)("span",{className:"font-serif text-[15px] font-semibold text-ink-primary",children:"Atlas"}),(0,s.jsx)("button",{onClick:()=>l(!1),"aria-label":"Close menu",children:(0,s.jsx)(o.A,{size:18,className:"text-ink-secondary"})})]}),(0,s.jsx)("div",{className:"flex-1 py-4 px-3",children:c.map(e=>(0,s.jsxs)("div",{className:"mb-4",children:[(0,s.jsx)("div",{className:"px-2 mb-1 font-sans text-[10px] text-ink-tertiary uppercase tracking-wider",children:e.label}),e.links.map(e=>{let t=a===e.href||"/"!==e.href&&a.startsWith(e.href);return(0,s.jsx)(r(),{href:e.href,onClick:()=>l(!1),className:`block px-3 py-1.5 rounded-sm font-sans text-[13px] transition-colors ${t?"bg-teal/10 text-teal font-medium":"text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/20"}`,children:e.label},e.href)})]},e.key))})]})]})]})}},54431:(e,a,t)=>{"use strict";t.r(a),t.d(a,{default:()=>s});let s=(0,t(12907).registerClientReference)(function(){throw Error("Attempted to call the default export of \"/home/ubuntu/atlas-os/frontend/src/app/error.tsx\" from the server, but it's on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/app/error.tsx","default")},61056:(e,a,t)=>{Promise.resolve().then(t.t.bind(t,86346,23)),Promise.resolve().then(t.t.bind(t,27924,23)),Promise.resolve().then(t.t.bind(t,35656,23)),Promise.resolve().then(t.t.bind(t,40099,23)),Promise.resolve().then(t.t.bind(t,38243,23)),Promise.resolve().then(t.t.bind(t,28827,23)),Promise.resolve().then(t.t.bind(t,62763,23)),Promise.resolve().then(t.t.bind(t,97173,23))},61135:()=>{},67393:(e,a,t)=>{"use strict";t.r(a),t.d(a,{default:()=>l});var s=t(37413);function l(){return(0,s.jsxs)("div",{className:"p-8 max-w-5xl mx-auto animate-pulse",children:[(0,s.jsx)("div",{className:"h-12 bg-paper-rule/40 rounded w-64 mb-4"}),(0,s.jsx)("div",{className:"h-4 bg-paper-rule/40 rounded w-96 mb-2"}),(0,s.jsx)("div",{className:"h-4 bg-paper-rule/40 rounded w-80"})]})}},78335:()=>{},80439:(e,a,t)=>{Promise.resolve().then(t.bind(t,50738))},84757:(e,a,t)=>{Promise.resolve().then(t.bind(t,14329))},96487:()=>{},97504:(e,a,t)=>{Promise.resolve().then(t.t.bind(t,16444,23)),Promise.resolve().then(t.t.bind(t,16042,23)),Promise.resolve().then(t.t.bind(t,88170,23)),Promise.resolve().then(t.t.bind(t,49477,23)),Promise.resolve().then(t.t.bind(t,29345,23)),Promise.resolve().then(t.t.bind(t,12089,23)),Promise.resolve().then(t.t.bind(t,46577,23)),Promise.resolve().then(t.t.bind(t,31307,23))}};