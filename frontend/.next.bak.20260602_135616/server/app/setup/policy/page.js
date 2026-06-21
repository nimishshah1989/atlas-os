(()=>{var e={};e.id=2531,e.ids=[2531],e.modules={171:(e,t,a)=>{"use strict";a.d(t,{Hn:()=>n,JD:()=>r,Pu:()=>i,_y:()=>s});let s={stage_1:"Stage 1 Base",stage_2a:"Stage 2A",stage_2b:"Stage 2B",stage_2c:"Stage 2C",stage_3:"Stage 3 Top",stage_4:"Stage 4 Decline",uninvestable:"Uninvestable"},r={direct_equity:"Direct Equity",etf:"ETF",mutual_fund:"Mutual Fund",mixed:"Mixed"};function n(e){return null==e?"—":s[e]??e}function i(e){return null==e?"—":r[e]??e}},3295:e=>{"use strict";e.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},4536:(e,t,a)=>{let{createProxy:s}=a(39844);e.exports=s("/home/ubuntu/atlas-os/frontend/node_modules/next/dist/client/app-dir/link.js")},10846:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},19121:e=>{"use strict";e.exports=require("next/dist/server/app-render/action-async-storage.external.js")},19194:(e,t,a)=>{Promise.resolve().then(a.t.bind(a,85814,23)),Promise.resolve().then(a.bind(a,65040))},21820:e=>{"use strict";e.exports=require("os")},27910:e=>{"use strict";e.exports=require("stream")},27992:(e,t,a)=>{"use strict";a.d(t,{Yp:()=>c,qf:()=>l});var s=a(5069);async function r(){return(await (0,s.A)`
    SELECT
      cash_floor_pct::text,
      respect_regime_cap,
      max_per_stock_pct::text,
      max_per_sector_pct::text,
      max_small_cap_pct::text,
      min_holdings::text,
      max_positions::text,
      buy_states,
      min_within_state_rank::text,
      min_rs_rank::text,
      hard_stop_pct::text,
      state_exit_trim,
      state_exit_full,
      trailing_stop_pct::text,
      instrument_universe,
      benchmark,
      rebalance_cadence
    FROM atlas.atlas_portfolio_policy
    WHERE is_house_default = TRUE
    LIMIT 1
  `)[0]??null}async function n(e){return(await (0,s.A)`
    SELECT
      cash_floor_pct::text,
      respect_regime_cap,
      max_per_stock_pct::text,
      max_per_sector_pct::text,
      max_small_cap_pct::text,
      min_holdings::text,
      max_positions::text,
      buy_states,
      min_within_state_rank::text,
      min_rs_rank::text,
      hard_stop_pct::text,
      state_exit_trim,
      state_exit_full,
      trailing_stop_pct::text,
      instrument_universe,
      benchmark,
      rebalance_cadence
    FROM atlas.atlas_portfolio_policy
    WHERE portfolio_id = ${e}
    LIMIT 1
  `)[0]??null}function i(e,t){return null!=t?{value:t,source:"overridden"}:{value:e,source:"inherited"}}function o(e,t){let a=t??{};return{cash_floor_pct:i(e.cash_floor_pct,a.cash_floor_pct??null),respect_regime_cap:i(e.respect_regime_cap,a.respect_regime_cap??null),max_per_stock_pct:i(e.max_per_stock_pct,a.max_per_stock_pct??null),max_per_sector_pct:i(e.max_per_sector_pct,a.max_per_sector_pct??null),max_small_cap_pct:i(e.max_small_cap_pct,a.max_small_cap_pct??null),min_holdings:i(e.min_holdings,a.min_holdings??null),max_positions:i(e.max_positions,a.max_positions??null),buy_states:i(e.buy_states,a.buy_states??null),min_within_state_rank:i(e.min_within_state_rank,a.min_within_state_rank??null),min_rs_rank:i(e.min_rs_rank,a.min_rs_rank??null),hard_stop_pct:i(e.hard_stop_pct,a.hard_stop_pct??null),state_exit_trim:i(e.state_exit_trim,a.state_exit_trim??null),state_exit_full:i(e.state_exit_full,a.state_exit_full??null),trailing_stop_pct:i(e.trailing_stop_pct,a.trailing_stop_pct??null),instrument_universe:i(e.instrument_universe,a.instrument_universe??null),benchmark:i(e.benchmark,a.benchmark??null),rebalance_cadence:i(e.rebalance_cadence,a.rebalance_cadence??null)}}async function l(e){let[t,a]=await Promise.all([r(),n(e)]);return null===t?null:o(t,a)}async function c(){let e=await r();return null===e?null:o(e,null)}},29021:e=>{"use strict";e.exports=require("fs")},29294:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-async-storage.external.js")},33873:e=>{"use strict";e.exports=require("path")},34631:e=>{"use strict";e.exports=require("tls")},39330:(e,t,a)=>{"use strict";a.d(t,{PolicyPageContainer:()=>s});let s=(0,a(12907).registerClientReference)(function(){throw Error("Attempted to call PolicyPageContainer() from the server but PolicyPageContainer is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/setup/PolicyPageContainer.tsx","PolicyPageContainer")},55511:e=>{"use strict";e.exports=require("crypto")},55986:(e,t,a)=>{Promise.resolve().then(a.t.bind(a,4536,23)),Promise.resolve().then(a.bind(a,39330))},63033:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},65040:(e,t,a)=>{"use strict";a.d(t,{PolicyPageContainer:()=>k});var s=a(60687),r=a(16189),n=a(43210),i=a(72942),o=a(171);let l={cash_floor_pct:"Cash Floor",respect_regime_cap:"Respect Regime Cap",max_per_stock_pct:"Max per Stock",max_per_sector_pct:"Max per Sector",max_small_cap_pct:"Max Small Cap",min_holdings:"Min Holdings",max_positions:"Max Positions",buy_states:"Buy States",min_within_state_rank:"Min Within-State Rank",min_rs_rank:"Min RS Rank",hard_stop_pct:"Hard Stop",state_exit_trim:"State Exit (Trim)",state_exit_full:"State Exit (Full)",trailing_stop_pct:"Trailing Stop",instrument_universe:"Instrument Universe",benchmark:"Benchmark",rebalance_cadence:"Rebalance Cadence"},c={cash_floor_pct:"Minimum cash reserve as a percentage of total portfolio value. Recommendations will not deploy below this floor — e.g. 5% means at most 95% is ever invested.",respect_regime_cap:"When enabled, the engine caps total equity deployment according to the current market regime (e.g. Risk-Off regimes trigger reduced exposure). Disabling means the mandate always targets full deployment regardless of regime.",max_per_stock_pct:"Maximum weight any single stock can hold in the portfolio. Limits idiosyncratic concentration risk — e.g. 5% means no stock can exceed 5% of AUM.",max_per_sector_pct:"Maximum combined weight for all positions in any single sector. Must be ≥ max_per_stock_pct. Prevents sector concentration — e.g. 15% means total IT exposure cannot exceed 15%.",max_small_cap_pct:"Maximum combined weight in small-cap stocks (outside Nifty 500). Caps illiquidity risk — e.g. 30% means at most 30% of the portfolio can be in small-caps.",min_holdings:"Minimum number of distinct positions the portfolio must hold. Prevents over-concentration in a handful of names. Must be ≤ max_positions.",max_positions:"Maximum number of distinct positions allowed at any time. Caps portfolio complexity and forces quality filtering.",buy_states:"The set of RS (relative-strength) state stages in which new entries are permitted. Only stocks currently in one of these states are eligible for purchase recommendations.",min_within_state_rank:"Minimum within-state rank (0–1 quantile) a stock must achieve before an entry is recommended. 0.60 means the stock must rank in the top 40% of peers in its state.",min_rs_rank:"Minimum 12-month relative-strength rank (0–1 quantile) required for entry. 0.70 means the stock's RS must be in the top 30% of the universe.",hard_stop_pct:"Hard exit trigger: exit the full position if it falls this many percent below the entry price. A mechanical loss-limit — e.g. 8% means exit if the stock is down 8% from purchase.",state_exit_trim:"RS state that triggers a partial position trim (reduce to half or a defined target). When a held stock enters this state, the system recommends trimming the position.",state_exit_full:"RS state that triggers a full exit. When a held stock enters this state, the system recommends exiting 100% of the position.",trailing_stop_pct:"Optional trailing stop: exit if the position falls this many percent below its highest post-entry close. Off = no trailing stop active.",instrument_universe:"The class of instruments eligible for this portfolio — direct_equity, etf, mutual_fund, or mixed.",benchmark:"The index used for alpha calculation, regime overlay, and relative performance attribution.",rebalance_cadence:"How frequently the engine generates rebalance recommendations: daily, weekly, or monthly."},d=[{title:"Deployment",fields:["cash_floor_pct","respect_regime_cap"]},{title:"Concentration",fields:["max_per_stock_pct","max_per_sector_pct","max_small_cap_pct","min_holdings","max_positions"]},{title:"Entry",fields:["buy_states","min_within_state_rank","min_rs_rank"]},{title:"Exit",fields:["hard_stop_pct","state_exit_trim","state_exit_full","trailing_stop_pct"]},{title:"Instrument",fields:["instrument_universe"]},{title:"Benchmark",fields:["benchmark"]},{title:"Cadence",fields:["rebalance_cadence"]}],p=Object.keys(o._y),u=["daily","weekly","monthly"];function _(e){let t={};for(let a of Object.keys(e))t[a]=e[a].value;return t}function m(e,t){return Array.isArray(e)&&Array.isArray(t)?e.length===t.length&&e.every((e,a)=>e===t[a]):null===e&&null===t||e===t}let x="font-mono text-xs w-20 border border-paper-rule rounded-[2px] px-2 py-1 bg-paper text-ink-primary disabled:opacity-50 disabled:cursor-not-allowed",h="font-mono text-xs border border-paper-rule rounded-[2px] px-2 py-1 bg-paper text-ink-primary disabled:opacity-50 disabled:cursor-not-allowed";function f({fieldKey:e,value:t,disabled:a,onChange:r}){let n="buy_states"===e?"states":"respect_regime_cap"===e?"bool":"trailing_stop_pct"===e?"trailing":"min_within_state_rank"===e||"min_rs_rank"===e?"rank":"min_holdings"===e||"max_positions"===e?"int":"state_exit_trim"===e||"state_exit_full"===e?"stage-select":"instrument_universe"===e?"universe":"rebalance_cadence"===e?"cadence":"benchmark"===e?"text":"pct",i=`field-${e}`,l=null==t?"":String(t);if("bool"===n){let n=!0===t||"true"===t;return(0,s.jsx)("div",{"data-testid":i,className:"inline-flex items-center",children:(0,s.jsx)("button",{"data-testid":`toggle-${e}`,type:"button",disabled:a,onClick:()=>r(!n),className:`font-sans text-xs px-3 py-1 rounded-[2px] border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${n?"bg-accent/10 border-accent/40 text-accent":"bg-paper border-paper-rule text-ink-secondary"}`,children:n?"Yes":"No"})})}if("states"===n){let e=Array.isArray(t)?t:[];return(0,s.jsx)("div",{"data-testid":i,className:"flex flex-wrap gap-2",children:p.map(t=>(0,s.jsxs)("label",{className:`flex items-center gap-1 font-sans text-xs cursor-pointer ${a?"opacity-50 cursor-not-allowed":""}`,children:[(0,s.jsx)("input",{type:"checkbox",value:t,checked:e.includes(t),disabled:a,onChange:()=>{a||r(e.includes(t)?e.filter(e=>e!==t):[...e,t])},className:"w-3 h-3"}),(0,s.jsx)("span",{children:(0,o.Hn)(t)})]},t))})}if("trailing"===n){let n=null==t||""===t;return(0,s.jsx)("div",{"data-testid":i,className:"flex items-center gap-2",children:n?(0,s.jsxs)(s.Fragment,{children:[(0,s.jsx)("span",{"data-testid":"trailing-off-indicator",className:"font-mono text-xs text-ink-tertiary",children:"Off"}),!a&&(0,s.jsx)("button",{type:"button",onClick:()=>r("0"),className:"font-sans text-[11px] text-accent hover:underline",children:"Enable"})]}):(0,s.jsxs)(s.Fragment,{children:[(0,s.jsx)("input",{"data-testid":`input-${e}`,type:"number",step:"0.1",value:l,disabled:a,onChange:e=>r(e.target.value),className:x}),!a&&(0,s.jsx)("button",{"data-testid":"trailing-clear-btn",type:"button",onClick:()=>r(null),className:"font-sans text-[11px] text-ink-tertiary hover:text-ink-primary",children:"Clear"})]})})}return"stage-select"===n?(0,s.jsx)("div",{"data-testid":i,children:(0,s.jsxs)("select",{value:l,disabled:a,onChange:e=>r(e.target.value),className:h,children:[(0,s.jsx)("option",{value:"",children:"—"}),p.map(e=>(0,s.jsx)("option",{value:e,children:(0,o.Hn)(e)},e))]})}):"universe"===n?(0,s.jsx)("div",{"data-testid":i,children:(0,s.jsx)("select",{value:l,disabled:a,onChange:e=>r(e.target.value),className:h,children:Object.entries(o.JD).map(([e,t])=>(0,s.jsx)("option",{value:e,children:t},e))})}):"cadence"===n?(0,s.jsx)("div",{"data-testid":i,children:(0,s.jsx)("select",{value:l,disabled:a,onChange:e=>r(e.target.value),className:h,children:u.map(e=>(0,s.jsx)("option",{value:e,children:e.charAt(0).toUpperCase()+e.slice(1)},e))})}):"text"===n?(0,s.jsx)("div",{"data-testid":i,children:(0,s.jsx)("input",{"data-testid":`input-${e}`,type:"text",value:l,disabled:a,onChange:e=>r(e.target.value),className:"font-mono text-xs w-32 border border-paper-rule rounded-[2px] px-2 py-1 bg-paper text-ink-primary disabled:opacity-50 disabled:cursor-not-allowed"})}):(0,s.jsx)("div",{"data-testid":i,children:(0,s.jsx)("input",{"data-testid":`input-${e}`,type:"number",step:"rank"===n?"0.01":"int"===n?"1":"0.1",value:l,disabled:a,onChange:e=>r(e.target.value),className:x})})}function b({fieldKey:e,source:t}){let a="font-sans text-[10px] px-1.5 py-0.5 rounded-[2px] border";return"overridden"===t?(0,s.jsx)("span",{"data-testid":`source-badge-${e}`,"data-source":"overridden",className:`${a} border-accent/30 text-accent bg-accent/5`,children:"overridden"}):(0,s.jsx)("span",{"data-testid":`source-badge-${e}`,"data-source":"inherited",className:`${a} border-paper-rule text-ink-tertiary bg-paper`,children:"inherited"})}function g({fieldKey:e,field:t,mode:a,draftValue:r,isActiveOverride:n,isReverted:o,onValueChange:d,onOverride:p,onRevert:u}){let _="portfolio"===a,m=_&&"inherited"===t.source&&!n,x=_&&"inherited"===t.source&&!n,h=_&&"overridden"===t.source&&!o,g=o?"inherited":n?"overridden":t.source;return(0,s.jsxs)("div",{className:"flex items-start justify-between gap-4 py-2 border-b border-paper-rule/50 last:border-0",children:[(0,s.jsxs)("div",{className:"flex items-center gap-1 min-w-[180px]",children:[(0,s.jsx)("span",{className:"font-sans text-xs text-ink-secondary",children:l[e]}),(0,s.jsx)(i.InfoTooltip,{content:c[e]})]}),(0,s.jsxs)("div",{className:"flex items-center gap-2 flex-wrap justify-end",children:[(0,s.jsx)(f,{fieldKey:e,value:o?t.value:r,disabled:m||o,onChange:d}),_&&(0,s.jsx)(b,{fieldKey:e,source:g}),x&&(0,s.jsx)("button",{"data-testid":`override-btn-${e}`,type:"button",onClick:p,className:"font-sans text-[11px] text-accent hover:underline",children:"Override"}),h&&(0,s.jsx)("button",{"data-testid":`revert-btn-${e}`,type:"button",onClick:u,className:"font-sans text-[11px] text-ink-tertiary hover:text-signal-neg",children:"Revert"})]})]})}function y({policy:e,mode:t,onSave:a}){let[r,i]=(0,n.useState)(()=>_(e)),[o,l]=(0,n.useState)(()=>_(e)),[c,p]=(0,n.useState)(new Set),[u,x]=(0,n.useState)(new Set),h=(0,n.useCallback)((e,t)=>{l(a=>({...a,[e]:t}))},[]),f=(0,n.useCallback)(e=>{p(t=>{let a=new Set(t);return a.add(e),a})},[]),b=(0,n.useCallback)(e=>{x(t=>{let a=new Set(t);return a.add(e),a})},[]),y=(0,n.useMemo)(()=>{let a={};for(let s of Object.keys(e))"portfolio"===t?u.has(s)?a[s]=null:c.has(s)?a[s]=o[s]??null:"overridden"!==e[s].source||m(o[s]??null,r[s]??null)||(a[s]=o[s]??null):m(o[s]??null,r[s]??null)||(a[s]=o[s]??null);return a},[o,r,e,t,c,u]),v=Object.keys(y).length>0,k=(0,n.useCallback)(()=>{let t={...y};a(t),i(a=>{let s={...a};for(let a of Object.keys(t))s[a]=null===t[a]?e[a].value:t[a];return s}),l(a=>{let s={...a};for(let a of Object.keys(t))null===t[a]&&(s[a]=e[a].value);return s}),p(new Set),x(new Set)},[y,a,e]);return(0,s.jsxs)("div",{children:[v&&(0,s.jsx)("div",{"data-testid":"unsaved-indicator",className:"mb-4 px-3 py-2 rounded-[2px] border border-signal-warn/40 bg-signal-warn/5 font-sans text-xs text-signal-warn",children:"Unsaved changes"}),d.map(a=>(0,s.jsxs)("div",{className:"mb-6",children:[(0,s.jsx)("h3",{className:"font-sans text-[11px] font-semibold uppercase tracking-wider text-ink-tertiary mb-2",children:a.title}),(0,s.jsx)("div",{className:"rounded-[3px] border border-paper-rule bg-paper px-4 py-0.5",children:a.fields.map(a=>(0,s.jsx)(g,{fieldKey:a,field:e[a],mode:t,draftValue:o[a]??e[a].value,isActiveOverride:c.has(a),isReverted:u.has(a),onValueChange:e=>h(a,e),onOverride:()=>f(a),onRevert:()=>b(a)},a))})]},a.title)),(0,s.jsx)("div",{className:"flex items-center justify-end gap-3 pt-2 border-t border-paper-rule",children:(0,s.jsx)("button",{type:"button",disabled:!v,onClick:k,className:"font-sans text-sm px-4 py-2 rounded-[2px] bg-accent text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent/90 transition-colors",children:"Save"})})]})}function v({policy:e,portfolioId:t,portfolios:a,onPortfolioChange:r}){let[i,o]=(0,n.useState)({kind:"idle"}),[l,c]=(0,n.useState)(e);async function d(e){o({kind:"saving"});try{let a=await fetch("/api/policy",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({portfolioId:t,changes:e})}),s=await a.json();if(a.ok&&s?.data)c(s.data),o({kind:"success",policy:s.data});else{let e=s?.message??`Error ${a.status}`;o({kind:"error",message:e})}}catch(e){o({kind:"error",message:e instanceof Error?e.message:"Unknown error"})}}return(0,s.jsxs)("div",{children:[(0,s.jsxs)("div",{className:"mb-6",children:[(0,s.jsx)("label",{htmlFor:"portfolio-selector",className:"font-sans text-xs font-semibold uppercase tracking-wider text-ink-tertiary block mb-1",children:"Editing policy for"}),(0,s.jsxs)("select",{id:"portfolio-selector",value:t??"",onChange:function(t){let a=t.target.value;r(""===a?null:a),o({kind:"idle"}),c(e)},className:"font-sans text-sm border border-paper-rule rounded-[2px] px-3 py-2 bg-paper text-ink-primary focus:outline-none focus:border-accent w-72",children:[(0,s.jsx)("option",{value:"",children:"House Default"}),a.map(e=>(0,s.jsx)("option",{value:e.id,children:e.name},e.id))]})]}),"success"===i.kind&&(0,s.jsx)("div",{"data-testid":"save-success",className:"mb-4 px-3 py-2 rounded-[2px] border border-signal-pos/40 bg-signal-pos/5 font-sans text-xs text-signal-pos",children:"Policy saved successfully."}),"error"===i.kind&&(0,s.jsx)("div",{"data-testid":"save-error",className:"mb-4 px-3 py-2 rounded-[2px] border border-signal-neg/40 bg-signal-neg/5 font-sans text-xs text-signal-neg",children:i.message}),(0,s.jsx)(y,{policy:"success"===i.kind?i.policy:l,mode:null===t?"house-default":"portfolio",onSave:d})]})}function k({policy:e,portfolioId:t,portfolios:a}){let n=(0,r.useRouter)();return(0,s.jsx)(v,{policy:e,portfolioId:t,portfolios:a,onPortfolioChange:function(e){let t=e?`/setup/policy?portfolio=${e}`:"/setup/policy";n.push(t)}})}},72942:(e,t,a)=>{"use strict";a.r(t),a.d(t,{InfoTooltip:()=>o});var s=a(60687),r=a(5710),n=a(96882),i=a(43210);function o({content:e,translation:t,className:a=""}){let o=(0,i.useId)();return(0,s.jsx)(r.Kq,{delayDuration:200,children:(0,s.jsxs)(r.bL,{children:[(0,s.jsx)(r.l9,{asChild:!0,children:(0,s.jsx)("button",{"aria-label":"info","aria-describedby":o,className:`inline-flex items-center justify-center w-[18px] h-[18px] rounded-full border-2 border-ink-secondary text-ink-secondary hover:border-ink-primary hover:text-ink-primary transition-colors ml-1 shrink-0 ${a}`,children:(0,s.jsx)(n.A,{size:12,strokeWidth:2.5})})}),(0,s.jsx)(r.ZL,{children:(0,s.jsxs)(r.UC,{id:o,className:"z-50 max-w-[220px] bg-paper border border-paper-rule rounded-[2px] px-2.5 py-1.5 text-[11px] font-sans text-ink-secondary shadow-sm",sideOffset:4,children:[(0,s.jsx)("span",{children:e}),null!=t&&(0,s.jsxs)("span",{className:"block mt-0.5 text-[0.7rem] text-ink-tertiary",children:["↳\xa0",t]}),(0,s.jsx)(r.i3,{className:"fill-paper-rule"})]})})]})})}},74998:e=>{"use strict";e.exports=require("perf_hooks")},87725:(e,t,a)=>{"use strict";a.r(t),a.d(t,{GlobalError:()=>i.a,__next_app__:()=>p,pages:()=>d,routeModule:()=>u,tree:()=>c});var s=a(65239),r=a(48088),n=a(88170),i=a.n(n),o=a(30893),l={};for(let e in o)0>["default","tree","pages","GlobalError","__next_app__","routeModule"].indexOf(e)&&(l[e]=()=>o[e]);a.d(t,l);let c={children:["",{children:["setup",{children:["policy",{children:["__PAGE__",{},{page:[()=>Promise.resolve().then(a.bind(a,89895)),"/home/ubuntu/atlas-os/frontend/src/app/setup/policy/page.tsx"]}]},{}]},{}]},{layout:[()=>Promise.resolve().then(a.bind(a,21339)),"/home/ubuntu/atlas-os/frontend/src/app/layout.tsx"],error:[()=>Promise.resolve().then(a.bind(a,54431)),"/home/ubuntu/atlas-os/frontend/src/app/error.tsx"],loading:[()=>Promise.resolve().then(a.bind(a,67393)),"/home/ubuntu/atlas-os/frontend/src/app/loading.tsx"],"not-found":[()=>Promise.resolve().then(a.t.bind(a,57398,23)),"next/dist/client/components/not-found-error"],forbidden:[()=>Promise.resolve().then(a.t.bind(a,89999,23)),"next/dist/client/components/forbidden-error"],unauthorized:[()=>Promise.resolve().then(a.t.bind(a,65284,23)),"next/dist/client/components/unauthorized-error"]}]}.children,d=["/home/ubuntu/atlas-os/frontend/src/app/setup/policy/page.tsx"],p={require:a,loadChunk:()=>Promise.resolve()},u=new s.AppPageRouteModule({definition:{kind:r.RouteKind.APP_PAGE,page:"/setup/policy/page",pathname:"/setup/policy",bundlePath:"",filename:"",appPaths:[]},userland:{loaderTree:c}})},89895:(e,t,a)=>{"use strict";a.r(t),a.d(t,{default:()=>d,dynamic:()=>c});var s=a(37413),r=a(4536),n=a.n(r),i=a(94879),o=a(27992),l=a(39330);let c="force-dynamic";async function d({searchParams:e}){let t=(await e).portfolio??null,[a,r]=await Promise.all([(0,i.JL)(),t?(0,o.qf)(t):(0,o.Yp)()]);return(0,s.jsxs)("main",{className:"min-h-screen bg-paper px-8 py-6 max-w-4xl mx-auto",children:[(0,s.jsxs)("header",{className:"mb-6",children:[(0,s.jsxs)("div",{className:"flex items-center gap-2 text-xs font-sans text-ink-tertiary mb-3",children:[(0,s.jsx)(n(),{href:"/setup",className:"hover:text-ink-primary transition-colors",children:"Setup"}),(0,s.jsx)("span",{children:"/"}),(0,s.jsx)("span",{children:"Policy"})]}),(0,s.jsx)("h1",{className:"font-serif text-2xl text-ink-primary",children:"Trade Policy"}),(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary mt-1",children:"House-default rules inherited by all portfolios unless overridden."})]}),null===r?(0,s.jsx)("div",{className:"px-4 py-3 rounded-[2px] border border-signal-warn/40 bg-signal-warn/5",children:(0,s.jsxs)("p",{className:"font-sans text-sm text-signal-warn",children:["No house-default policy found. Run"," ",(0,s.jsx)("code",{className:"font-mono text-xs",children:"scripts/seed_house_policy.py"})," to seed the default row."]})}):(0,s.jsx)(l.PolicyPageContainer,{policy:r,portfolioId:t,portfolios:a})]})}},91645:e=>{"use strict";e.exports=require("net")},94879:(e,t,a)=>{"use strict";a.d(t,{JL:()=>r,Q5:()=>o,sr:()=>i,tn:()=>n});var s=a(5069);async function r(){return(await (0,s.A)`
    SELECT
      p.id,
      p.name,
      'static'::text                        AS type,
      jsonb_array_length(p.instruments)     AS instrument_count,
      bt.sharpe_ratio::text                 AS latest_sharpe,
      p.paper_trading_active,
      p.created_at
    FROM atlas.strategy_fm_custom_portfolios p
    LEFT JOIN LATERAL (
      SELECT sharpe_ratio
      FROM atlas.strategy_backtest_results
      WHERE custom_portfolio_id = p.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE

    UNION ALL

    SELECT
      sc.id,
      sc.name,
      'rule-based'::text                    AS type,
      NULL::int                             AS instrument_count,
      bt.sharpe_ratio::text                 AS latest_sharpe,
      FALSE                                 AS paper_trading_active,
      sc.created_at
    FROM atlas.strategy_configs sc
    LEFT JOIN LATERAL (
      SELECT sharpe_ratio
      FROM atlas.strategy_backtest_results
      WHERE strategy_id = sc.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE
    WHERE sc.is_fm_authored = TRUE

    ORDER BY created_at DESC
  `).filter(e=>!function(e){let t=e.trim().toLowerCase();return t.includes("(auto-created)")||t.startsWith("validate_")}(e.name))}async function n(e){return(await (0,s.A)`
    SELECT
      p.id,
      p.name,
      (
        SELECT jsonb_agg(
          elem || jsonb_build_object(
            'symbol',       u.symbol,
            'sector',       COALESCE(u.sector, 'Unknown'),
            'is_small_cap', (u.in_nifty_100 IS NOT TRUE AND u.in_nifty_500 IS NOT TRUE),
            'engine_state', ss.engine_state
          )
        )
        FROM jsonb_array_elements(p.instruments) AS elem
        LEFT JOIN LATERAL (
          -- Portfolio holdings mix stock instruments (uuid ids) and fund
          -- instruments (string ids like "F00001G6N8"). Compare as text so a
          -- fund id never gets cast to ::uuid (which would raise a SQL error).
          SELECT symbol, sector, in_nifty_100, in_nifty_500
          FROM atlas.atlas_universe_stocks
          WHERE instrument_id::text = elem->>'instrument_id'
          ORDER BY effective_from DESC
          LIMIT 1
        ) u ON TRUE
        LEFT JOIN LATERAL (
          SELECT engine_state
          FROM atlas.atlas_stock_signal_unified
          WHERE instrument_id::text = elem->>'instrument_id'
          ORDER BY date DESC
          LIMIT 1
        ) ss ON TRUE
      )                               AS instruments,
      p.backtest_id,
      p.paper_trading_active,
      p.created_at,
      p.updated_at,
      bt.sharpe_ratio::text           AS latest_sharpe,
      bt.max_drawdown::text           AS latest_max_drawdown,
      bt.alpha_vs_nifty500::text      AS latest_alpha_vs_nifty500
    FROM atlas.strategy_fm_custom_portfolios p
    LEFT JOIN LATERAL (
      SELECT sharpe_ratio, max_drawdown, alpha_vs_nifty500
      FROM atlas.strategy_backtest_results
      WHERE custom_portfolio_id = p.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE
    WHERE p.id = ${e}
  `)[0]??null}async function i(e){return(await (0,s.A)`
    SELECT
      sc.id,
      sc.name,
      sc.config,
      sc.is_active,
      sc.created_by,
      sc.created_at,
      sc.updated_at,
      bt.sharpe_ratio::text           AS latest_sharpe,
      bt.max_drawdown::text           AS latest_max_drawdown,
      bt.alpha_vs_nifty500::text      AS latest_alpha_vs_nifty500,
      bt.id::text                     AS latest_backtest_id
    FROM atlas.strategy_configs sc
    LEFT JOIN LATERAL (
      SELECT id, sharpe_ratio, max_drawdown, alpha_vs_nifty500
      FROM atlas.strategy_backtest_results
      WHERE strategy_id = sc.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE
    WHERE sc.id = ${e}
      AND sc.is_fm_authored = TRUE
  `)[0]??null}async function o(e,t,a=50){return"static"===t?(0,s.A)`
      SELECT
        id,
        backtest_type,
        start_date,
        end_date,
        sharpe_ratio::text          AS sharpe_ratio,
        max_drawdown::text          AS max_drawdown,
        total_return::text          AS total_return,
        alpha_vs_nifty500::text     AS alpha_vs_nifty500,
        alpha_vs_naive_atlas::text  AS alpha_vs_naive_atlas,
        walk_forward_oos_sharpe::text AS walk_forward_oos_sharpe,
        regime_breakdown,
        created_at
      FROM atlas.strategy_backtest_results
      WHERE custom_portfolio_id = ${e}
      ORDER BY created_at DESC
      LIMIT ${a}
    `:(0,s.A)`
    SELECT
      id,
      backtest_type,
      start_date,
      end_date,
      sharpe_ratio::text          AS sharpe_ratio,
      max_drawdown::text          AS max_drawdown,
      total_return::text          AS total_return,
      alpha_vs_nifty500::text     AS alpha_vs_nifty500,
      alpha_vs_naive_atlas::text  AS alpha_vs_naive_atlas,
      walk_forward_oos_sharpe::text AS walk_forward_oos_sharpe,
      regime_breakdown,
      created_at
    FROM atlas.strategy_backtest_results
    WHERE strategy_id = ${e}
    ORDER BY created_at DESC
    LIMIT ${a}
  `}},96882:(e,t,a)=>{"use strict";a.d(t,{A:()=>s});let s=(0,a(62688).A)("Info",[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["path",{d:"M12 16v-4",key:"1dtifu"}],["path",{d:"M12 8h.01",key:"e9boi3"}]])}};var t=require("../../../webpack-runtime.js");t.C(e);var a=e=>t(t.s=e),s=t.X(0,[4447,3971,9626,5710,4613],()=>a(87725));module.exports=s})();