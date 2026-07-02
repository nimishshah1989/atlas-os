exports.id=826,exports.ids=[826],exports.modules={5069:(e,t,a)=>{"use strict";a.d(t,{A:()=>l});var n=a(43971);if(!process.env.ATLAS_DB_URL)throw Error("ATLAS_DB_URL is not defined. Set it in .env.local.");let s=process.env.ATLAS_DB_URL.includes("pooler.supabase.com");if(process.env.ATLAS_DB_URL.includes(":6543/"))throw Error("ATLAS_DB_URL must use session-mode pooler (port 5432), not transaction-mode (port 6543). M13 audit trail relies on sql.begin() + SET LOCAL which requires a pinned connection.");let l=(0,n.A)(process.env.ATLAS_DB_URL,{max:14,idle_timeout:10,max_lifetime:300,connect_timeout:10,prepare:!s,ssl:!!process.env.ATLAS_DB_URL.includes("sslmode=require")&&{rejectUnauthorized:!1}})},10592:(e,t,a)=>{"use strict";a.d(t,{A7:()=>_,A9:()=>b,Cr:()=>o,Om:()=>x,P:()=>l,aW:()=>h,en:()=>s,j5:()=>p,lc:()=>c,pg:()=>m,v9:()=>f,zP:()=>i});var n=a(5069);async function s(e=30){return await (0,n.A)`
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
  `}async function l(){return await (0,n.A)`
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
  `}let r=[{schema:"atlas_foundation",name:"technical_daily",date_col:"date"},{schema:"atlas_foundation",name:"atlas_lens_scores_daily",date_col:"date"},{schema:"atlas_foundation",name:"sector_lens_daily",date_col:"date"},{schema:"atlas_foundation",name:"fund_rank_daily",date_col:"date"},{schema:"atlas_foundation",name:"atlas_index_metrics_daily",date_col:"date"},{schema:"atlas_foundation",name:"atlas_market_regime_daily",date_col:"date"},{schema:"atlas_foundation",name:"breadth_nifty500_daily",date_col:"date"}];async function o(){let e=new Date;return e.setHours(0,0,0,0),Promise.all(r.map(async({schema:t,name:a,date_col:s})=>{if(s){let l=(await (0,n.A)`
          SELECT
            (SELECT reltuples::bigint FROM pg_class
              JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
              WHERE nspname = ${t} AND relname = ${a})::text AS row_count,
            MAX(${(0,n.A)(s)}) AS latest_date
          FROM ${(0,n.A)(t)}.${(0,n.A)(a)}
        `)[0],r=l?.latest_date?new Date(l.latest_date):null,o=r?Math.floor((e.getTime()-r.getTime())/864e5):null;return{table_name:a,row_count:Number(l?.row_count??0),latest_date:r,lag_days:o}}{let e=await (0,n.A)`
          SELECT reltuples::bigint::text AS row_count
          FROM pg_class
          JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
          WHERE nspname = ${t} AND relname = ${a}
        `;return{table_name:a,row_count:Number(e[0]?.row_count??0),latest_date:null,lag_days:null}}}))}function i(e){return"atlas_fund_lens_monthly"===e?35:2}let d=[{table:"ohlcv_stock",date_col:"date",label:"Stock prices (OHLCV)",cadence:"Daily",feeds:"Returns \xb7 RS \xb7 technicals",ok:4,warn:7},{table:"technical_daily",date_col:"date",label:"Technical metrics",cadence:"Daily",feeds:"RS \xb7 EMA \xb7 RSI \xb7 returns",ok:4,warn:7},{table:"atlas_lens_scores_daily",date_col:"date",label:"Lens scores + composite",cadence:"Daily",feeds:"Conviction score \xb7 deciles",ok:4,warn:7},{table:"sector_lens_daily",date_col:"date",label:"Sector lens vectors",cadence:"Daily",feeds:"Sector pages",ok:4,warn:7},{table:"atlas_index_metrics_daily",date_col:"date",label:"Index returns",cadence:"Daily",feeds:"Sector RS \xb7 benchmarks",ok:4,warn:7},{table:"mv_sector_cards",date_col:"as_of_date",label:"Sector cards",cadence:"Daily",feeds:"/sectors heatmap + hero",ok:4,warn:7},{table:"mv_sector_breadth",date_col:"as_of_date",label:"Sector breadth",cadence:"Daily",feeds:"Breadth table",ok:4,warn:7},{table:"de_mf_nav_daily",date_col:"nav_date",label:"Fund NAVs",cadence:"Daily",feeds:"Fund pages",ok:4,warn:7},{table:"atlas_fund_scorecard",date_col:"snapshot_date",label:"Fund scorecard",cadence:"Daily",feeds:"Fund ranking + score",ok:7,warn:14},{table:"de_mf_holdings",date_col:"as_of_date",label:"Fund holdings",cadence:"Monthly",feeds:"Fund roll-ups + look-through",ok:40,warn:60},{table:"de_etf_holdings",date_col:"as_of_date",label:"ETF holdings",cadence:"Monthly",feeds:"ETF roll-ups + look-through",ok:40,warn:60}];async function c(){let e=new Date;return e.setHours(0,0,0,0),Promise.all(d.map(async t=>{let a=(await (0,n.A)`
        SELECT
          (SELECT reltuples::bigint FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = 'atlas_foundation' AND relname = ${t.table})::text AS row_count,
          MAX(${(0,n.A)(t.date_col)}) AS latest_date
        FROM atlas_foundation.${(0,n.A)(t.table)}
      `.catch(()=>[]))[0],s=a?.latest_date?new Date(a.latest_date):null,l=s?Math.floor((e.getTime()-s.getTime())/864e5):null,r=null==l?"red":l<=t.ok?"green":l<=t.warn?"amber":"red";return{table:t.table,label:t.label,cadence:t.cadence,feeds:t.feeds,latest_date:s,lag_days:l,row_count:Number(a?.row_count??0),rag:r}}))}function _(e){return e.some(e=>"red"===e.rag)?"red":e.some(e=>"amber"===e.rag)?"amber":"green"}let u=[{name:"ohlcv_stock",date_col:"date"},{name:"ohlcv_etf",date_col:"date"},{name:"index_prices",date_col:"date"},{name:"de_mf_nav_daily",date_col:"nav_date"},{name:"de_mf_holdings",date_col:"as_of_date"},{name:"de_etf_holdings",date_col:"as_of_date"},{name:"delivery_daily",date_col:"date"}];async function m(){let e=new Date;return e.setHours(0,0,0,0),Promise.all(u.map(async({name:t,date_col:a})=>{let s=(await (0,n.A)`
        SELECT
          (SELECT reltuples::bigint FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = 'atlas_foundation' AND relname = ${t})::text AS row_count,
          MAX(${(0,n.A)(a)}) AS latest_date
        FROM atlas_foundation.${(0,n.A)(t)}
      `)[0],l=s?.latest_date?new Date(s.latest_date):null,r=l?Math.floor((e.getTime()-l.getTime())/864e5):null;return{table_name:t,row_count:Number(s?.row_count??0),latest_date:l,lag_days:r}}))}function h(e){return 2}async function f(){let e=await (0,n.A)`
    SELECT MAX(data_date) AS d FROM atlas_foundation.atlas_health_daily
  `,t=e[0]?.d;return t?await (0,n.A)`
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
    WHERE data_date = ${t}
      AND is_anomaly = TRUE
    ORDER BY
      CASE severity
        WHEN 'critical' THEN 0
        WHEN 'warn'     THEN 1
        WHEN 'info'     THEN 2
        ELSE 3
      END,
      table_name, metric_name
  `:[]}async function p(e=30){return await (0,n.A)`
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
  `}async function b(){return await (0,n.A)`
    SELECT DISTINCT ON (validator)
      run_id::text AS run_id,
      validator,
      ran_at,
      total_checks,
      failures,
      status
    FROM atlas_foundation.atlas_validator_results
    ORDER BY validator, ran_at DESC
  `}async function x(){let[e,t,a]=await Promise.all([(0,n.A)`
      SELECT MAX(computed_at) AS ts FROM atlas_foundation.atlas_health_daily
    `,(0,n.A)`
      SELECT severity, COUNT(*)::text AS n
      FROM atlas_foundation.atlas_health_daily
      WHERE data_date = (SELECT MAX(data_date) FROM atlas_foundation.atlas_health_daily)
        AND is_anomaly = TRUE
      GROUP BY severity
    `,(0,n.A)`
      SELECT DISTINCT ON (validator) validator, status
      FROM atlas_foundation.atlas_validator_results
      ORDER BY validator, ran_at DESC
    `]),s=e[0]?.ts??null,l={};for(let e of t)l[e.severity]=Number(e.n);let r=a.filter(e=>"FAIL"===e.status).length;return(l.critical??0)>0||r>0?{level:"red",message:`${l.critical??0} critical anomalies \xb7 ${r} validator FAILs`,last_health_check:s}:(l.warn??0)>0?{level:"yellow",message:`${l.warn} warnings`,last_health_check:s}:{level:"green",message:"System healthy",last_health_check:s}}},14329:(e,t,a)=>{"use strict";a.r(t),a.d(t,{default:()=>s});var n=a(60687);function s({error:e,reset:t}){return(0,n.jsxs)("div",{className:"p-8 max-w-md mx-auto mt-16",children:[(0,n.jsx)("p",{className:"font-sans text-sm text-ink-secondary mb-4",children:"Something went wrong loading this page."}),(0,n.jsx)("button",{onClick:t,className:"font-sans text-sm text-accent underline",children:"Try again"})]})}a(43210)},20191:(e,t,a)=>{Promise.resolve().then(a.bind(a,30112))},30112:(e,t,a)=>{"use strict";a.d(t,{TopNav:()=>s});var n=a(12907);let s=(0,n.registerClientReference)(function(){throw Error("Attempted to call TopNav() from the server but TopNav is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/nav/TopNav.tsx","TopNav");(0,n.registerClientReference)(function(){throw Error("Attempted to call GROUPS() from the server but GROUPS is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/nav/TopNav.tsx","GROUPS")},41879:(e,t,a)=>{"use strict";a.d(t,{TopNav:()=>p});var n=a(60687),s=a(85814),l=a.n(s),r=a(43210),o=a(16189),i=a(11860),d=a(12941),c=a(21134),_=a(363);function u(){let[e,t]=(0,r.useState)("light"),[a,s]=(0,r.useState)(!1);return(0,n.jsx)("button",{type:"button",onClick:function(){let a="dark"===e?"light":"dark";t(a),document.documentElement.setAttribute("data-theme",a);try{localStorage.setItem("atlas-theme",a)}catch{}},"aria-label":a?`Switch to ${"dark"===e?"day":"night"} view`:"Toggle day / night view",className:"grid h-7 w-7 place-items-center rounded-tile border border-edge-rule text-txt-2 transition-colors hover:border-edge-strong hover:text-txt-1",children:a&&"dark"===e?(0,n.jsx)(c.A,{size:14}):(0,n.jsx)(_.A,{size:14})})}let m=[{href:"/",label:"Market Pulse",exact:!0},{href:"/sectors",label:"Sector View"},{href:"/stocks",label:"Stocks"},{href:"/etfs",label:"ETF"},{href:"/funds",label:"Funds"},{href:"/admin",label:"Admin"}];function h(e,t){return t.exact?e===t.href:e===t.href||e.startsWith(t.href+"/")||e===t.href}function f({healthDot:e}){let t=(0,o.usePathname)(),[a,s]=(0,r.useState)(!1);return(0,n.jsxs)(n.Fragment,{children:[(0,n.jsxs)("nav",{className:"fixed inset-x-0 top-0 z-50 flex h-12 items-center gap-1 border-b border-edge-rule bg-surface-base/95 px-5 backdrop-blur",children:[(0,n.jsxs)(l(),{href:"/",className:"mr-4 flex shrink-0 items-center gap-2",children:[(0,n.jsx)("span",{className:"h-2 w-2 rounded-full bg-brand",style:{boxShadow:"0 0 8px -1px var(--color-brand)"}}),(0,n.jsx)("span",{className:"font-display text-[16px] font-bold tracking-tight text-txt-1",children:"Atlas"})]}),(0,n.jsx)("div",{className:"hidden items-center gap-0.5 md:flex",children:m.map(e=>{let a=h(t,e);return(0,n.jsxs)(l(),{href:e.href,prefetch:!1,className:`relative rounded-tile px-3 py-1.5 font-sans text-[12px] font-medium transition-colors ${a?"text-txt-1":"text-txt-3 hover:text-txt-1"}`,children:[e.label,a&&(0,n.jsx)("span",{className:"absolute inset-x-3 -bottom-px h-[2px] rounded-full bg-brand"})]},e.href)})}),(0,n.jsxs)("div",{className:"ml-auto flex items-center gap-3",children:[(0,n.jsx)(u,{}),e,(0,n.jsx)("button",{className:"p-1 text-txt-3 hover:text-txt-1 md:hidden",onClick:()=>s(e=>!e),"aria-label":"Toggle menu",children:a?(0,n.jsx)(i.A,{size:18}):(0,n.jsx)(d.A,{size:18})})]})]}),a&&(0,n.jsxs)("div",{className:"fixed inset-0 z-[60] md:hidden",children:[(0,n.jsx)("div",{className:"absolute inset-0 bg-black/50",onClick:()=>s(!1)}),(0,n.jsxs)("div",{className:"absolute inset-y-0 left-0 flex w-72 flex-col overflow-y-auto border-r border-edge-rule bg-surface-panel",children:[(0,n.jsxs)("div",{className:"flex h-12 shrink-0 items-center justify-between border-b border-edge-rule px-5",children:[(0,n.jsx)("span",{className:"font-display text-[16px] font-bold text-txt-1",children:"Atlas"}),(0,n.jsx)("button",{onClick:()=>s(!1),"aria-label":"Close menu",children:(0,n.jsx)(i.A,{size:18,className:"text-txt-3"})})]}),(0,n.jsx)("div",{className:"flex-1 p-3",children:m.map(e=>{let a=h(t,e);return(0,n.jsx)(l(),{href:e.href,onClick:()=>s(!1),className:`block rounded-tile px-3 py-2 font-sans text-[13px] transition-colors ${a?"bg-surface-raised text-txt-1":"text-txt-2 hover:bg-surface-raised hover:text-txt-1"}`,children:e.label},e.href)})})]})]})]})}function p({healthDot:e}){return(0,n.jsx)(f,{healthDot:e})}},42901:(e,t,a)=>{Promise.resolve().then(a.bind(a,54431))},54431:(e,t,a)=>{"use strict";a.r(t),a.d(t,{default:()=>n});let n=(0,a(12907).registerClientReference)(function(){throw Error("Attempted to call the default export of \"/home/ubuntu/atlas-os/frontend/src/app/error.tsx\" from the server, but it's on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/app/error.tsx","default")},61056:(e,t,a)=>{Promise.resolve().then(a.t.bind(a,86346,23)),Promise.resolve().then(a.t.bind(a,27924,23)),Promise.resolve().then(a.t.bind(a,35656,23)),Promise.resolve().then(a.t.bind(a,40099,23)),Promise.resolve().then(a.t.bind(a,38243,23)),Promise.resolve().then(a.t.bind(a,28827,23)),Promise.resolve().then(a.t.bind(a,62763,23)),Promise.resolve().then(a.t.bind(a,97173,23))},61135:()=>{},67393:(e,t,a)=>{"use strict";a.r(t),a.d(t,{default:()=>s});var n=a(37413);function s(){return(0,n.jsxs)("div",{className:"p-8 max-w-5xl mx-auto animate-pulse",children:[(0,n.jsx)("div",{className:"h-12 bg-paper-rule/40 rounded w-64 mb-4"}),(0,n.jsx)("div",{className:"h-4 bg-paper-rule/40 rounded w-96 mb-2"}),(0,n.jsx)("div",{className:"h-4 bg-paper-rule/40 rounded w-80"})]})}},78335:()=>{},80439:(e,t,a)=>{Promise.resolve().then(a.bind(a,41879))},83218:(e,t,a)=>{"use strict";a.r(t),a.d(t,{default:()=>f,metadata:()=>h});var n=a(37413),s=a(21338),l=a.n(s),r=a(50396),o=a.n(r),i=a(36080),d=a.n(i),c=a(61120);a(61135);var _=a(30112),u=a(10592);async function m(){let e="yellow",t="Unknown";try{let a=await (0,u.Om)();e=a.level,t=a.message}catch{}return(0,n.jsx)("span",{title:t,className:`inline-block w-2 h-2 rounded-full ${{green:"bg-signal-pos",yellow:"bg-signal-warn",red:"bg-signal-neg"}[e]}`})}let h={title:"Atlas-OS",description:"Fund manager research tool — Javeri Securities",robots:"noindex, nofollow"};function f({children:e}){return(0,n.jsx)("html",{lang:"en",className:`${l().variable} ${o().variable} ${d().variable}`,children:(0,n.jsxs)("body",{className:"bg-surface-base min-h-screen",children:[(0,n.jsx)("script",{dangerouslySetInnerHTML:{__html:"(function(){try{var t=localStorage.getItem('atlas-theme')||'light';document.documentElement.setAttribute('data-theme',t)}catch(e){document.documentElement.setAttribute('data-theme','light')}})()"}}),(0,n.jsx)(_.TopNav,{healthDot:(0,n.jsx)(c.Suspense,{fallback:(0,n.jsx)("span",{className:"inline-block w-2 h-2 rounded-full bg-paper-rule"}),children:(0,n.jsx)(m,{})})}),(0,n.jsx)("main",{className:"pt-12",children:e})]})})}},84757:(e,t,a)=>{Promise.resolve().then(a.bind(a,14329))},96487:()=>{},97504:(e,t,a)=>{Promise.resolve().then(a.t.bind(a,16444,23)),Promise.resolve().then(a.t.bind(a,16042,23)),Promise.resolve().then(a.t.bind(a,88170,23)),Promise.resolve().then(a.t.bind(a,49477,23)),Promise.resolve().then(a.t.bind(a,29345,23)),Promise.resolve().then(a.t.bind(a,12089,23)),Promise.resolve().then(a.t.bind(a,46577,23)),Promise.resolve().then(a.t.bind(a,31307,23))}};