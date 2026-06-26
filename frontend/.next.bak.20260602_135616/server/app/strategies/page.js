(()=>{var e={};e.id=2974,e.ids=[2974],e.modules={3295:e=>{"use strict";e.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},5063:(e,t,r)=>{"use strict";r.d(t,{FB:()=>a,Ot:()=>i});var s=r(5069);async function a(e){let t=e?.tier??null,r=e?.archetype??null,a=e?.paperActive??null;return(0,s.A)`
    SELECT
      sc.id,
      sc.name,
      sc.tier,
      sc.archetype,
      sc.variant,
      sc.config,
      sc.is_active,
      sc.is_fm_authored,
      sc.created_by,
      sc.created_at,
      sc.updated_at,
      (
        SELECT COUNT(*) > 0
        FROM atlas.strategy_paper_portfolios pp
        WHERE pp.strategy_id = sc.id
      ) AS paper_active,
      bt.sharpe_ratio::text           AS latest_sharpe,
      bt.alpha_vs_nifty500::text      AS latest_alpha_vs_nifty500,
      bt.created_at                   AS latest_backtest_at
    FROM atlas.strategy_configs sc
    LEFT JOIN LATERAL (
      SELECT sharpe_ratio, alpha_vs_nifty500, created_at
      FROM atlas.strategy_backtest_results
      WHERE strategy_id = sc.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE
    WHERE sc.is_fm_authored = FALSE
      AND (${t}::text IS NULL OR sc.tier = ${t}::text)
      AND (${r}::text IS NULL OR sc.archetype = ${r}::text)
      AND (
        ${a}::boolean IS NULL
        OR (
          ${a}::boolean = TRUE
          AND EXISTS (
            SELECT 1 FROM atlas.strategy_paper_portfolios pp WHERE pp.strategy_id = sc.id
          )
        )
        OR (
          ${a}::boolean = FALSE
          AND NOT EXISTS (
            SELECT 1 FROM atlas.strategy_paper_portfolios pp WHERE pp.strategy_id = sc.id
          )
        )
      )
    ORDER BY sc.tier, sc.name
  `}async function i(e){return(await (0,s.A)`
    SELECT
      sc.id,
      sc.name,
      sc.tier,
      sc.archetype,
      sc.variant,
      sc.config,
      sc.config->>'description'           AS description,
      sc.is_active,
      sc.is_fm_authored,
      sc.created_by,
      sc.created_at,
      sc.updated_at,
      (
        SELECT COUNT(*) > 0
        FROM atlas.strategy_paper_portfolios pp
        WHERE pp.strategy_id = sc.id
      ) AS paper_active
    FROM atlas.strategy_configs sc
    WHERE sc.id = ${e}
      AND sc.is_fm_authored = FALSE
  `)[0]??null}},10846:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},12409:(e,t,r)=>{Promise.resolve().then(r.bind(r,55249))},19121:e=>{"use strict";e.exports=require("next/dist/server/app-render/action-async-storage.external.js")},21820:e=>{"use strict";e.exports=require("os")},27910:e=>{"use strict";e.exports=require("stream")},29021:e=>{"use strict";e.exports=require("fs")},29294:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-async-storage.external.js")},33873:e=>{"use strict";e.exports=require("path")},34631:e=>{"use strict";e.exports=require("tls")},55249:(e,t,r)=>{"use strict";r.d(t,{StrategiesView:()=>c});var s=r(60687),a=r(16189),i=r(43210),n=r(85814),o=r.n(n);let l=["Aggressive","Moderate","Passive"],p=["momentum_blend","sector_rotation","quality_growth","low_volatility","mean_reversion"];function c({strategies:e,initialTier:t,initialArchetype:r,initialPaperActive:n}){let c=(0,a.useRouter)(),d=(0,a.usePathname)(),x=(0,a.useSearchParams)(),u=(0,i.useCallback)(e=>{let t=new URLSearchParams(x.toString());for(let[r,s]of Object.entries(e))null==s||""===s?t.delete(r):t.set(r,s);c.push(`${d}?${t.toString()}`)},[c,d,x]),h=t??"",m=r??"",f=n??"",g=e.filter(e=>(!h||e.tier===h)&&(!m||e.archetype===m)&&("true"!==f||!!e.paper_active)&&("false"!==f||!e.paper_active));return(0,s.jsxs)("div",{children:[(0,s.jsxs)("div",{className:"flex flex-wrap items-center gap-3 mb-5 pb-4 border-b border-paper-rule",children:[(0,s.jsxs)("div",{className:"flex gap-1.5",children:[(0,s.jsx)("span",{className:"font-sans text-xs text-ink-tertiary self-center mr-1",children:"Tier:"}),l.map(e=>(0,s.jsx)("button",{type:"button",onClick:()=>u({tier:h===e?"":e}),className:`font-sans text-xs px-3 py-1 rounded-[2px] border transition-colors ${h===e?"bg-accent text-white border-accent":"text-ink-secondary border-paper-rule hover:text-ink-primary"}`,children:e},e))]}),(0,s.jsxs)("div",{className:"flex gap-1.5 flex-wrap",children:[(0,s.jsx)("span",{className:"font-sans text-xs text-ink-tertiary self-center mr-1",children:"Archetype:"}),p.map(e=>(0,s.jsx)("button",{type:"button",onClick:()=>u({archetype:m===e?"":e}),className:`font-sans text-xs px-2 py-1 rounded-[2px] border transition-colors ${m===e?"bg-accent text-white border-accent":"text-ink-secondary border-paper-rule hover:text-ink-primary"}`,children:e.replace(/_/g," ")},e))]}),(0,s.jsx)("button",{type:"button",onClick:()=>{u({paper:"true"===f?"":"true"})},className:`font-sans text-xs px-3 py-1 rounded-[2px] border transition-colors ${"true"===f?"bg-signal-pos/10 text-signal-pos border-signal-pos/30":"text-ink-secondary border-paper-rule hover:text-ink-primary"}`,children:"Paper Active"}),(h||m||f)&&(0,s.jsx)("button",{type:"button",onClick:()=>u({tier:"",archetype:"",paper:""}),className:"font-sans text-xs text-ink-tertiary hover:text-ink-primary underline decoration-dotted",children:"Clear filters"})]}),(0,s.jsx)("div",{className:"overflow-x-auto",children:(0,s.jsxs)("table",{className:"w-full text-left border-collapse",children:[(0,s.jsx)("thead",{children:(0,s.jsx)("tr",{className:"border-b border-paper-rule",children:["Name","Archetype","Tier","Sharpe","Alpha vs N500","Paper","Updated"].map(e=>(0,s.jsx)("th",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium",children:e},e))})}),(0,s.jsxs)("tbody",{children:[0===g.length&&(0,s.jsx)("tr",{children:(0,s.jsx)("td",{colSpan:7,className:"py-8 text-center font-sans text-sm text-ink-tertiary",children:"No strategies match the current filters."})}),g.map(e=>{var t;return(0,s.jsxs)("tr",{className:"border-b border-paper-rule/50 hover:bg-paper-rule/10 transition-colors cursor-pointer",children:[(0,s.jsx)("td",{className:"py-3 pr-4",children:(0,s.jsx)(o(),{href:`/strategies/${e.id}`,className:"font-sans text-sm text-ink-primary hover:text-accent transition-colors",children:e.name})}),(0,s.jsx)("td",{className:"py-3 pr-4 font-sans text-xs text-ink-secondary",children:e.archetype.replace(/_/g," ")}),(0,s.jsx)("td",{className:"py-3 pr-4",children:(0,s.jsx)("span",{className:"font-sans text-xs text-ink-secondary",children:e.tier})}),(0,s.jsx)("td",{className:"py-3 pr-4 font-mono text-sm text-ink-primary text-right",children:function(e){if(null==e)return"—";let t=parseFloat(e);return isNaN(t)?"—":t.toFixed(2)}(e.latest_sharpe)}),(0,s.jsx)("td",{className:`py-3 pr-4 font-mono text-sm text-right ${null!=e.latest_alpha_vs_nifty500&&parseFloat(e.latest_alpha_vs_nifty500)>=0?"text-signal-pos":"text-signal-neg"}`,children:function(e){if(null==e)return"—";let t=parseFloat(e);return isNaN(t)?"—":`${t>=0?"+":""}${(100*t).toFixed(2)}%`}(e.latest_alpha_vs_nifty500)}),(0,s.jsx)("td",{className:"py-3 pr-4",children:e.paper_active?(0,s.jsx)("span",{className:"inline-block w-2 h-2 rounded-full bg-signal-pos",title:"Paper trading active"}):(0,s.jsx)("span",{className:"inline-block w-2 h-2 rounded-full bg-paper-rule",title:"Paper trading inactive"})}),(0,s.jsx)("td",{className:"py-3 font-sans text-xs text-ink-tertiary",children:(t=e.latest_backtest_at)?(t instanceof Date?t:new Date(String(t))).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}):"—"})]},e.id)})]})]})})]})}},55511:e=>{"use strict";e.exports=require("crypto")},58250:(e,t,r)=>{"use strict";r.r(t),r.d(t,{default:()=>o,dynamic:()=>n});var s=r(37413),a=r(5063),i=r(67659);let n="force-dynamic";async function o({searchParams:e}){let t=await e,r={tier:t.tier??void 0,archetype:t.archetype??void 0,paperActive:"true"===t.paper||"false"!==t.paper&&void 0},n=await (0,a.FB)(r.tier||r.archetype||void 0!==r.paperActive?r:void 0),o=n.length>0?n.filter(e=>null!=e.latest_sharpe).reduce((e,t)=>e+parseFloat(t.latest_sharpe),0)/(n.filter(e=>null!=e.latest_sharpe).length||1):null,l=n.filter(e=>e.paper_active).length,p=n.reduce((e,t)=>(e[t.tier]=(e[t.tier]??0)+1,e),{});return(0,s.jsxs)("main",{className:"min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto",children:[(0,s.jsxs)("header",{className:"mb-6",children:[(0,s.jsx)("h1",{className:"font-serif text-2xl text-ink-primary",children:"Systematic Strategies"}),(0,s.jsxs)("p",{className:"font-sans text-xs text-ink-tertiary mt-1",children:[n.length," strategies \xb7 ",l," paper-active"]})]}),(0,s.jsxs)("div",{className:"grid grid-cols-2 md:grid-cols-4 gap-3 mb-6",children:[(0,s.jsxs)("div",{className:"bg-paper border border-paper-rule rounded-[2px] p-3",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide",children:"Avg Sharpe"}),(0,s.jsx)("p",{className:"font-mono text-lg font-semibold text-ink-primary mt-1",children:null!=o?o.toFixed(2):"—"})]}),["Aggressive","Moderate","Passive"].map(e=>(0,s.jsxs)("div",{className:"bg-paper border border-paper-rule rounded-[2px] p-3",children:[(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide",children:e}),(0,s.jsx)("p",{className:"font-mono text-lg font-semibold text-ink-primary mt-1",children:p[e]??0})]},e))]}),(0,s.jsx)(i.StrategiesView,{strategies:n,initialTier:t.tier,initialArchetype:t.archetype,initialPaperActive:t.paper})]})}},59609:(e,t,r)=>{Promise.resolve().then(r.bind(r,67659))},63033:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},67659:(e,t,r)=>{"use strict";r.d(t,{StrategiesView:()=>s});let s=(0,r(12907).registerClientReference)(function(){throw Error("Attempted to call StrategiesView() from the server but StrategiesView is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/app/strategies/StrategiesView.tsx","StrategiesView")},71203:(e,t,r)=>{"use strict";r.r(t),r.d(t,{GlobalError:()=>n.a,__next_app__:()=>d,pages:()=>c,routeModule:()=>x,tree:()=>p});var s=r(65239),a=r(48088),i=r(88170),n=r.n(i),o=r(30893),l={};for(let e in o)0>["default","tree","pages","GlobalError","__next_app__","routeModule"].indexOf(e)&&(l[e]=()=>o[e]);r.d(t,l);let p={children:["",{children:["strategies",{children:["__PAGE__",{},{page:[()=>Promise.resolve().then(r.bind(r,58250)),"/home/ubuntu/atlas-os/frontend/src/app/strategies/page.tsx"]}]},{}]},{layout:[()=>Promise.resolve().then(r.bind(r,21339)),"/home/ubuntu/atlas-os/frontend/src/app/layout.tsx"],error:[()=>Promise.resolve().then(r.bind(r,54431)),"/home/ubuntu/atlas-os/frontend/src/app/error.tsx"],loading:[()=>Promise.resolve().then(r.bind(r,67393)),"/home/ubuntu/atlas-os/frontend/src/app/loading.tsx"],"not-found":[()=>Promise.resolve().then(r.t.bind(r,57398,23)),"next/dist/client/components/not-found-error"],forbidden:[()=>Promise.resolve().then(r.t.bind(r,89999,23)),"next/dist/client/components/forbidden-error"],unauthorized:[()=>Promise.resolve().then(r.t.bind(r,65284,23)),"next/dist/client/components/unauthorized-error"]}]}.children,c=["/home/ubuntu/atlas-os/frontend/src/app/strategies/page.tsx"],d={require:r,loadChunk:()=>Promise.resolve()},x=new s.AppPageRouteModule({definition:{kind:a.RouteKind.APP_PAGE,page:"/strategies/page",pathname:"/strategies",bundlePath:"",filename:"",appPaths:[]},userland:{loaderTree:p}})},74998:e=>{"use strict";e.exports=require("perf_hooks")},91645:e=>{"use strict";e.exports=require("net")}};var t=require("../../webpack-runtime.js");t.C(e);var r=e=>t(t.s=e),s=t.X(0,[4447,3971,9626,4613],()=>r(71203));module.exports=s})();