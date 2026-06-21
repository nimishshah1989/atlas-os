"use strict";(()=>{var e={};e.id=3624,e.ids=[3624],e.modules={3295:e=>{e.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},10846:e=>{e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},12755:(e,t,r)=>{r.d(t,{Ee:()=>a,P3:()=>s,V8:()=>d,al:()=>i,gC:()=>l,uJ:()=>o});var n=r(5069);async function a(){return(0,n.A)`
    SELECT
      l.rank,
      l.genome_id::text,
      l.strategy_name,
      l.promoted_at,
      l.sortino_oos::text,
      l.calmar_oos::text,
      l.alpha_30d::text,
      l.regime_breakdown,
      g.generation
    FROM atlas_strategy_leaderboard l
    JOIN atlas_strategy_genomes g ON g.id = l.genome_id
    ORDER BY l.rank
  `}async function s(){return(await (0,n.A)`
    SELECT id::text, generated_at, insight_bullets, parameter_importance, top_genome_deltas
    FROM atlas_strategy_insights
    ORDER BY generated_at DESC
    LIMIT 1
  `)[0]??null}async function i(){return(await (0,n.A)`
    SELECT
      COUNT(*) FILTER (WHERE status = 'active')   AS active_count,
      COUNT(*) FILTER (WHERE status = 'killed')   AS killed_count,
      COUNT(*) FILTER (WHERE status = 'promoted') AS promoted_count,
      MAX(born_at)                                AS last_born_at
    FROM atlas_strategy_genomes
  `)[0]??{active_count:0,killed_count:0,promoted_count:0,last_born_at:null}}async function o(e){return(0,n.A)`
    SELECT
      p.date,
      u.ticker,
      u.company_name,
      p.position_type,
      p.entry_date,
      p.entry_price::text,
      p.shares::text,
      p.current_value::text,
      p.unrealized_pnl::text,
      p.holding_days,
      p.tax_status,
      p.entry_signals
    FROM atlas_strategy_positions_daily p
    JOIN atlas.atlas_universe_stocks u ON u.id = p.instrument_id
    WHERE p.genome_id = ${e}
      AND p.date = (SELECT MAX(date) FROM atlas_strategy_positions_daily WHERE genome_id = ${e})
    ORDER BY p.current_value DESC
  `}async function l(){return(0,n.A)`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas_strategy_recommendations_daily
    )
    SELECT
      r.date,
      r.genome_id::text,
      r.rank,
      r.instrument_id::text,
      u.ticker,
      u.company_name,
      r.action,
      r.conviction::text,
      r.position_size_pct::text,
      r.stop_price::text,
      r.genome_alpha_oos::text,
      r.genome_information_ratio::text,
      r.genome_hit_rate::text,
      r.genome_t_stat::text,
      r.confidence_band,
      l.strategy_name
    FROM atlas_strategy_recommendations_daily r
    JOIN atlas_strategy_leaderboard l ON l.genome_id = r.genome_id
    LEFT JOIN atlas.atlas_universe_stocks u ON u.id = r.instrument_id
    WHERE r.date = (SELECT d FROM latest)
    ORDER BY r.rank, r.conviction DESC
  `}async function d(){return(await (0,n.A)`
    SELECT id::text, created_at, config_json, is_active, label
    FROM atlas_portfolio_config
    WHERE is_active = TRUE
    ORDER BY created_at DESC LIMIT 1
  `)[0]??null}},19121:e=>{e.exports=require("next/dist/server/app-render/action-async-storage.external.js")},21820:e=>{e.exports=require("os")},27910:e=>{e.exports=require("stream")},29021:e=>{e.exports=require("fs")},29294:e=>{e.exports=require("next/dist/server/app-render/work-async-storage.external.js")},33873:e=>{e.exports=require("path")},34631:e=>{e.exports=require("tls")},55511:e=>{e.exports=require("crypto")},63033:e=>{e.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},65384:(e,t,r)=>{r.r(t),r.d(t,{default:()=>l,dynamic:()=>s});var n=r(37413),a=r(12755);let s="force-dynamic";function i(e,t=2){if(null===e)return"—";let r=Number(e);return Number.isFinite(r)?`${(100*r).toFixed(t)}%`:"—"}function o(e,t=2){if(null===e)return"—";let r=Number(e);return Number.isFinite(r)?r.toFixed(t):"—"}async function l(){let e=await (0,a.gC)();if(0===e.length)return(0,n.jsxs)("main",{className:"min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto",children:[(0,n.jsx)("h1",{className:"font-serif text-3xl text-ink-900 mb-2",children:"Today's Recommendations"}),(0,n.jsx)("p",{className:"text-ink-600 mb-8",children:"No recommendations yet. The Strategy Lab nightly job has not produced a leaderboard or today's picks have not been written."})]});let t=e[0].date,r=new Map;for(let t of e)r.has(t.genome_id)||r.set(t.genome_id,[]),r.get(t.genome_id).push(t);return(0,n.jsxs)("main",{className:"min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto",children:[(0,n.jsxs)("header",{className:"mb-8",children:[(0,n.jsx)("h1",{className:"font-serif text-3xl text-ink-900",children:"Today's Recommendations"}),(0,n.jsxs)("p",{className:"text-sm text-ink-500 mt-1",children:["As of ",new Date(t).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"})]})]}),(0,n.jsx)("div",{className:"space-y-8",children:Array.from(r.entries()).map(([e,t])=>{var r;let a=t[0];return(0,n.jsxs)("section",{className:"border border-paper-rule rounded-lg bg-white",children:[(0,n.jsxs)("header",{className:"px-5 py-4 border-b border-paper-rule flex items-baseline justify-between",children:[(0,n.jsxs)("div",{children:[(0,n.jsx)("div",{className:"font-serif text-xl text-ink-900",children:a.strategy_name}),(0,n.jsxs)("div",{className:"text-xs text-ink-500 mt-0.5",children:["Rank #",a.rank," \xb7 genome ",e.slice(0,8)]})]}),(0,n.jsxs)("div",{className:`px-3 py-1 text-xs font-medium border rounded ${"HIGH"===(r=a.confidence_band)?"text-teal-700 bg-teal-50 border-teal-200":"MEDIUM"===r?"text-amber-700 bg-amber-50 border-amber-200":"text-stone-600 bg-stone-50 border-stone-200"}`,children:[a.confidence_band," confidence"]})]}),(0,n.jsxs)("div",{className:"px-5 py-3 grid grid-cols-4 gap-4 text-sm border-b border-paper-rule bg-stone-50/50",children:[(0,n.jsxs)("div",{children:[(0,n.jsx)("div",{className:"text-xs text-ink-500",children:"Alpha (OOS)"}),(0,n.jsx)("div",{className:"font-mono text-ink-900",children:i(a.genome_alpha_oos,2)})]}),(0,n.jsxs)("div",{children:[(0,n.jsx)("div",{className:"text-xs text-ink-500",children:"Information ratio"}),(0,n.jsx)("div",{className:"font-mono text-ink-900",children:o(a.genome_information_ratio,2)})]}),(0,n.jsxs)("div",{children:[(0,n.jsx)("div",{className:"text-xs text-ink-500",children:"Hit rate"}),(0,n.jsx)("div",{className:"font-mono text-ink-900",children:i(a.genome_hit_rate,0)})]}),(0,n.jsxs)("div",{children:[(0,n.jsx)("div",{className:"text-xs text-ink-500",children:"Alpha t-stat"}),(0,n.jsx)("div",{className:"font-mono text-ink-900",children:o(a.genome_t_stat,2)})]})]}),(0,n.jsxs)("table",{className:"w-full text-sm",children:[(0,n.jsx)("thead",{className:"text-xs text-ink-500 border-b border-paper-rule",children:(0,n.jsxs)("tr",{children:[(0,n.jsx)("th",{className:"text-left px-5 py-2 font-normal",children:"Stock"}),(0,n.jsx)("th",{className:"text-right px-5 py-2 font-normal",children:"Size"}),(0,n.jsx)("th",{className:"text-right px-5 py-2 font-normal",children:"Stop"}),(0,n.jsx)("th",{className:"text-right px-5 py-2 font-normal",children:"Conviction"}),(0,n.jsx)("th",{className:"text-left px-5 py-2 font-normal",children:"Action"})]})}),(0,n.jsx)("tbody",{children:t.map(e=>(0,n.jsxs)("tr",{className:"border-b border-paper-rule/40 last:border-0",children:[(0,n.jsxs)("td",{className:"px-5 py-2",children:[(0,n.jsx)("div",{className:"font-medium text-ink-900",children:e.ticker??e.instrument_id.slice(0,8)}),e.company_name?(0,n.jsx)("div",{className:"text-xs text-ink-500",children:e.company_name}):null]}),(0,n.jsx)("td",{className:"px-5 py-2 text-right font-mono",children:i(e.position_size_pct,2)}),(0,n.jsx)("td",{className:"px-5 py-2 text-right font-mono",children:function(e){if(null===e)return"—";let t=Number(e);return Number.isFinite(t)?`₹${t.toLocaleString("en-IN",{maximumFractionDigits:2})}`:"—"}(e.stop_price)}),(0,n.jsx)("td",{className:"px-5 py-2 text-right font-mono",children:o(e.conviction,2)}),(0,n.jsx)("td",{className:"px-5 py-2 font-medium text-ink-900",children:e.action})]},`${e.genome_id}-${e.instrument_id}-${e.action}`))})]})]},e)})})]})}},74998:e=>{e.exports=require("perf_hooks")},91645:e=>{e.exports=require("net")},94151:(e,t,r)=>{r.r(t),r.d(t,{GlobalError:()=>i.a,__next_app__:()=>x,pages:()=>c,routeModule:()=>m,tree:()=>d});var n=r(65239),a=r(48088),s=r(88170),i=r.n(s),o=r(30893),l={};for(let e in o)0>["default","tree","pages","GlobalError","__next_app__","routeModule"].indexOf(e)&&(l[e]=()=>o[e]);r.d(t,l);let d={children:["",{children:["strategies",{children:["lab",{children:["today",{children:["__PAGE__",{},{page:[()=>Promise.resolve().then(r.bind(r,65384)),"/home/ubuntu/atlas-os/frontend/src/app/strategies/lab/today/page.tsx"]}]},{}]},{}]},{}]},{layout:[()=>Promise.resolve().then(r.bind(r,21339)),"/home/ubuntu/atlas-os/frontend/src/app/layout.tsx"],error:[()=>Promise.resolve().then(r.bind(r,54431)),"/home/ubuntu/atlas-os/frontend/src/app/error.tsx"],loading:[()=>Promise.resolve().then(r.bind(r,67393)),"/home/ubuntu/atlas-os/frontend/src/app/loading.tsx"],"not-found":[()=>Promise.resolve().then(r.t.bind(r,57398,23)),"next/dist/client/components/not-found-error"],forbidden:[()=>Promise.resolve().then(r.t.bind(r,89999,23)),"next/dist/client/components/forbidden-error"],unauthorized:[()=>Promise.resolve().then(r.t.bind(r,65284,23)),"next/dist/client/components/unauthorized-error"]}]}.children,c=["/home/ubuntu/atlas-os/frontend/src/app/strategies/lab/today/page.tsx"],x={require:r,loadChunk:()=>Promise.resolve()},m=new n.AppPageRouteModule({definition:{kind:a.RouteKind.APP_PAGE,page:"/strategies/lab/today/page",pathname:"/strategies/lab/today",bundlePath:"",filename:"",appPaths:[]},userland:{loaderTree:d}})}};var t=require("../../../../webpack-runtime.js");t.C(e);var r=e=>t(t.s=e),n=t.X(0,[4447,3971,9626,4613],()=>r(94151));module.exports=n})();