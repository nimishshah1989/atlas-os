(()=>{var e={};e.id=9541,e.ids=[9541],e.modules={2041:(e,t,r)=>{"use strict";r.d(t,{E:()=>o});var s=r(43210),a=r(49605),n=r(12042),i=["axis","item"],o=(0,s.forwardRef)((e,t)=>s.createElement(n.P,{chartName:"BarChart",defaultTooltipEventType:"axis",validateTooltipEventTypes:i,tooltipPayloadSearcher:a.uN,categoricalChartProps:e,ref:t}))},3295:e=>{"use strict";e.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},5074:(e,t,r)=>{Promise.resolve().then(r.bind(r,38945))},10846:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},12755:(e,t,r)=>{"use strict";r.d(t,{Ee:()=>a,P3:()=>n,V8:()=>d,al:()=>i,gC:()=>l,uJ:()=>o});var s=r(5069);async function a(){return(0,s.A)`
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
  `}async function n(){return(await (0,s.A)`
    SELECT id::text, generated_at, insight_bullets, parameter_importance, top_genome_deltas
    FROM atlas_strategy_insights
    ORDER BY generated_at DESC
    LIMIT 1
  `)[0]??null}async function i(){return(await (0,s.A)`
    SELECT
      COUNT(*) FILTER (WHERE status = 'active')   AS active_count,
      COUNT(*) FILTER (WHERE status = 'killed')   AS killed_count,
      COUNT(*) FILTER (WHERE status = 'promoted') AS promoted_count,
      MAX(born_at)                                AS last_born_at
    FROM atlas_strategy_genomes
  `)[0]??{active_count:0,killed_count:0,promoted_count:0,last_born_at:null}}async function o(e){return(0,s.A)`
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
  `}async function l(){return(0,s.A)`
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
  `}async function d(){return(await (0,s.A)`
    SELECT id::text, created_at, config_json, is_active, label
    FROM atlas_portfolio_config
    WHERE is_active = TRUE
    ORDER BY created_at DESC LIMIT 1
  `)[0]??null}},19121:e=>{"use strict";e.exports=require("next/dist/server/app-render/action-async-storage.external.js")},21755:(e,t,r)=>{"use strict";r.r(t),r.d(t,{default:()=>o,dynamic:()=>i});var s=r(37413),a=r(12755),n=r(65871);let i="force-dynamic";async function o(){let[e,t,r]=await Promise.all([(0,a.P3)(),(0,a.al)(),(0,a.Ee)()]);return(0,s.jsxs)("main",{className:"min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto",children:[(0,s.jsxs)("header",{className:"mb-6",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide",children:"Strategy Lab"}),(0,s.jsx)("h1",{className:"font-serif text-2xl text-ink-primary mt-1",children:"Engine Room"})]}),(0,s.jsx)(n.EngineRoom,{insights:e,health:t,leaderboard:r})]})}},21820:e=>{"use strict";e.exports=require("os")},27910:e=>{"use strict";e.exports=require("stream")},29021:e=>{"use strict";e.exports=require("fs")},29294:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-async-storage.external.js")},33873:e=>{"use strict";e.exports=require("path")},34631:e=>{"use strict";e.exports=require("tls")},38945:(e,t,r)=>{"use strict";r.d(t,{EngineRoom:()=>_});var s=r(60687),a=r(49513),n=r(2041),i=r(27747),o=r(9920),l=r(23812),d=r(23801),c=r(25679);let p="#1D9E75",x={backgroundColor:"#ffffff",border:"1px solid #e2e8f0",borderRadius:"2px",fontFamily:"var(--font-sans)",fontSize:"11px",color:"#1e293b",padding:"6px 8px"},m={fontSize:9,fill:"#94a3b8"};function u({data:e}){let t=Object.entries(e).sort((e,t)=>t[1]-e[1]).slice(0,12).map(([e,t])=>({name:e,value:Number(t.toFixed(3))}));return t.length?(0,s.jsx)(a.u,{width:"100%",height:240,children:(0,s.jsxs)(n.E,{data:t,layout:"vertical",margin:{top:4,right:12,bottom:4,left:120},children:[(0,s.jsx)(i.W,{type:"number",tick:m,tickLine:!1,axisLine:!1,tickFormatter:e=>e.toFixed(2)}),(0,s.jsx)(o.h,{type:"category",dataKey:"name",tick:m,tickLine:!1,axisLine:!1,width:116}),(0,s.jsx)(l.m,{contentStyle:x,formatter:e=>["number"==typeof e?e.toFixed(3):"—","Importance"]}),(0,s.jsx)(d.yP,{dataKey:"value",radius:[0,2,2,0],isAnimationActive:!1,children:t.map((e,t)=>(0,s.jsx)(c.f,{fill:0===t?p:`${p}${Math.max(40,255-18*t).toString(16).padStart(2,"0")}`},`cell-${t}`))})]})}):(0,s.jsx)("div",{className:"flex items-center justify-center h-32",children:(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary",children:"No parameter data yet — engine still optimizing."})})}function g({health:e}){let t=e.active_count+e.killed_count+e.promoted_count,r=t>0?(e.promoted_count/t*100).toFixed(1):"0.0",a=e.last_born_at?new Date(e.last_born_at).toLocaleDateString("en-IN",{day:"2-digit",month:"short"}):"—";return(0,s.jsxs)("div",{className:"grid grid-cols-2 gap-3",children:[[{label:"Active Genomes",value:e.active_count,cls:"text-teal-600"},{label:"Promoted to Leaderboard",value:e.promoted_count,cls:"text-blue-600"},{label:"Killed This Cycle",value:e.killed_count,cls:"text-red-500"},{label:"Promotion Rate",value:`${r}%`,cls:"text-ink-primary"}].map(({label:e,value:t,cls:r})=>(0,s.jsxs)("div",{className:"border border-paper-rule rounded-[2px] p-3 bg-paper",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide",children:e}),(0,s.jsx)("p",{className:`font-mono text-xl font-semibold mt-1 ${r}`,children:t})]},e)),(0,s.jsxs)("div",{className:"col-span-2 border border-paper-rule rounded-[2px] p-3 bg-paper",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide",children:"Last Genome Born"}),(0,s.jsx)("p",{className:"font-mono text-sm font-semibold text-ink-primary mt-1",children:a})]})]})}function h({leaderboard:e}){return(0,s.jsxs)("div",{className:"border border-paper-rule rounded-[2px] p-4 bg-paper",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3",children:"Generation Tree"}),0===e.length?(0,s.jsx)("p",{className:"font-sans text-sm text-ink-tertiary",children:"No promoted strategies yet."}):(0,s.jsx)("div",{className:"space-y-2",children:e.slice(0,8).map(e=>(0,s.jsxs)("div",{className:"flex items-center gap-3",children:[(0,s.jsxs)("span",{className:"font-mono text-xs text-ink-tertiary w-6",children:["#",e.rank]}),(0,s.jsxs)("div",{className:"flex-1",children:[(0,s.jsxs)("div",{className:"flex items-center gap-2",children:[(0,s.jsx)("span",{className:"font-sans text-xs text-ink-primary",children:e.strategy_name}),(0,s.jsxs)("span",{className:"font-sans text-xs text-ink-tertiary",children:["Gen ",e.generation]})]}),(0,s.jsx)("div",{className:"h-1 bg-paper-rule rounded-full mt-1 overflow-hidden",children:(0,s.jsx)("div",{className:"h-full rounded-full",style:{width:`${Math.min(100,30*Number(e.sortino_oos??0))}%`,backgroundColor:p}})})]}),(0,s.jsx)("span",{className:"font-mono text-xs text-ink-primary w-12 text-right",children:e.sortino_oos?Number(e.sortino_oos).toFixed(2):"—"})]},e.genome_id))})]})}function _({insights:e,health:t,leaderboard:r}){let a=e?.generated_at?new Date(e.generated_at).toLocaleString("en-IN",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}):"—";return(0,s.jsxs)("div",{className:"space-y-6",children:[(0,s.jsxs)("div",{className:"flex items-center justify-between",children:[(0,s.jsxs)("p",{className:"font-sans text-xs text-ink-tertiary",children:["Last optimization run: ",(0,s.jsx)("span",{className:"font-mono",children:a})]}),(0,s.jsxs)("span",{className:"font-sans text-xs px-2 py-1 rounded-[2px] bg-teal-50 text-teal-700 border border-teal-200",children:[t.active_count," genomes active"]})]}),(0,s.jsxs)("div",{className:"grid grid-cols-2 gap-6",children:[(0,s.jsx)("div",{className:"space-y-4",children:(0,s.jsxs)("div",{className:"border border-paper-rule rounded-[2px] p-4 bg-paper",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-4",children:"Parameter Importance"}),(0,s.jsx)(u,{data:e?.parameter_importance??{}})]})}),(0,s.jsx)("div",{className:"space-y-4",children:(0,s.jsxs)("div",{className:"border border-paper-rule rounded-[2px] p-4 bg-paper",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-4",children:"Gene Pool Health"}),(0,s.jsx)(g,{health:t})]})})]}),(0,s.jsx)(h,{leaderboard:r}),e&&e.insight_bullets.length>0&&(0,s.jsxs)("div",{className:"border border-paper-rule rounded-[2px] p-5 bg-paper",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3",children:"Overnight Insight Feed"}),(0,s.jsx)("ul",{className:"space-y-3",children:e.insight_bullets.map((e,t)=>(0,s.jsxs)("li",{className:"font-sans text-sm text-ink-primary flex gap-3 pb-3 border-b border-paper-rule last:border-0 last:pb-0",children:[(0,s.jsx)("span",{className:"text-teal-600 font-mono text-xs mt-0.5 flex-shrink-0",children:String(t+1).padStart(2,"0")}),(0,s.jsx)("span",{children:e.replace(/^\d+\.\s*/,"")})]},t))})]}),(!e||0===e.insight_bullets.length)&&(0,s.jsx)("div",{className:"border border-paper-rule rounded-[2px] p-5 bg-paper text-center",children:(0,s.jsx)("p",{className:"font-sans text-sm text-ink-tertiary",children:"No insights generated yet. Engine runs nightly after market close."})})]})}},42026:(e,t,r)=>{Promise.resolve().then(r.bind(r,65871))},55511:e=>{"use strict";e.exports=require("crypto")},63033:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},65871:(e,t,r)=>{"use strict";r.d(t,{EngineRoom:()=>s});let s=(0,r(12907).registerClientReference)(function(){throw Error("Attempted to call EngineRoom() from the server but EngineRoom is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/trading/EngineRoom.tsx","EngineRoom")},74998:e=>{"use strict";e.exports=require("perf_hooks")},82053:(e,t,r)=>{"use strict";r.r(t),r.d(t,{GlobalError:()=>i.a,__next_app__:()=>p,pages:()=>c,routeModule:()=>x,tree:()=>d});var s=r(65239),a=r(48088),n=r(88170),i=r.n(n),o=r(30893),l={};for(let e in o)0>["default","tree","pages","GlobalError","__next_app__","routeModule"].indexOf(e)&&(l[e]=()=>o[e]);r.d(t,l);let d={children:["",{children:["strategies",{children:["lab",{children:["engine",{children:["__PAGE__",{},{page:[()=>Promise.resolve().then(r.bind(r,21755)),"/home/ubuntu/atlas-os/frontend/src/app/strategies/lab/engine/page.tsx"]}]},{}]},{}]},{}]},{layout:[()=>Promise.resolve().then(r.bind(r,21339)),"/home/ubuntu/atlas-os/frontend/src/app/layout.tsx"],error:[()=>Promise.resolve().then(r.bind(r,54431)),"/home/ubuntu/atlas-os/frontend/src/app/error.tsx"],loading:[()=>Promise.resolve().then(r.bind(r,67393)),"/home/ubuntu/atlas-os/frontend/src/app/loading.tsx"],"not-found":[()=>Promise.resolve().then(r.t.bind(r,57398,23)),"next/dist/client/components/not-found-error"],forbidden:[()=>Promise.resolve().then(r.t.bind(r,89999,23)),"next/dist/client/components/forbidden-error"],unauthorized:[()=>Promise.resolve().then(r.t.bind(r,65284,23)),"next/dist/client/components/unauthorized-error"]}]}.children,c=["/home/ubuntu/atlas-os/frontend/src/app/strategies/lab/engine/page.tsx"],p={require:r,loadChunk:()=>Promise.resolve()},x=new s.AppPageRouteModule({definition:{kind:a.RouteKind.APP_PAGE,page:"/strategies/lab/engine/page",pathname:"/strategies/lab/engine",bundlePath:"",filename:"",appPaths:[]},userland:{loaderTree:d}})},91645:e=>{"use strict";e.exports=require("net")}};var t=require("../../../../webpack-runtime.js");t.C(e);var r=e=>t(t.s=e),s=t.X(0,[4447,3971,9626,346,3801,4613],()=>r(82053));module.exports=s})();