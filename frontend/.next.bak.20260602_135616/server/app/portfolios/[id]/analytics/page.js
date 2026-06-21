(()=>{var e={};e.id=5271,e.ids=[5271],e.modules={3295:e=>{"use strict";e.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},10846:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},15632:(e,t,r)=>{"use strict";r.d(t,{PortfolioAnalyticsClient:()=>g});var a=r(60687),s=r(85814),n=r.n(s),i=r(43210),o=r(49513),l=r(61678),c=r(85168),d=r(27747),u=r(9920),p=r(23812),x=r(66424);function f(e,t=2,r=!1){if(null===e)return"—";let a=e.toFixed(t);return r&&e>0?`+${a}`:a}function m(e,t=!0){if(null===e)return"—";let r=(100*e).toFixed(2);return t&&e>0?`+${r}%`:`${r}%`}function h(e){return null===e?"text-ink-primary":e>0?"text-signal-pos":e<0?"text-signal-neg":"text-ink-primary"}function _(e){let t=new Date(e);if(isNaN(t.getTime()))return e;let r=String(t.getDate()).padStart(2,"0"),a=t.toLocaleString("en-US",{month:"short"}),s=t.getFullYear();return`${r}-${a}-${s}`}function y(e,t,r){return s=>{let{cx:n=0,cy:i=0,index:o=0,payload:l}=s;if(o!==r-1||!l)return null;let c=l[t],d=(100*c).toFixed(1);return(0,a.jsxs)("g",{children:[(0,a.jsx)("circle",{cx:n,cy:i,r:3,fill:e}),(0,a.jsxs)("text",{x:n+6,y:i+4,fill:e,fontSize:10,fontFamily:"var(--font-mono)",children:[c>0?"+":"",d,"%"]})]})}}function v({label:e,value:t,subLabel:r,valueClass:s="text-ink-primary",tooltip:n}){return(0,a.jsxs)("div",{className:"flex flex-col items-center justify-center py-4 px-3 border-r border-paper-rule last:border-r-0",title:n,children:[(0,a.jsx)("span",{className:"font-mono text-[11px] uppercase tracking-wider text-ink-3 mb-1 text-center",children:e}),(0,a.jsx)("span",{className:`font-mono text-[22px] font-semibold tabular-nums leading-tight ${s}`,children:t}),(0,a.jsx)("span",{className:"font-sans text-[11px] text-ink-4 mt-1 text-center",children:r})]})}function b({active:e,payload:t,label:r}){return e&&t&&0!==t.length?(0,a.jsxs)("div",{className:"bg-paper border border-paper-rule rounded-[2px] px-3 py-2 shadow-sm",children:[(0,a.jsx)("div",{className:"font-sans text-[11px] text-ink-3 mb-1",children:r?_(r):""}),t.map(e=>{let t=(100*e.value).toFixed(2),r=e.value>0?"+":"";return(0,a.jsxs)("div",{className:"font-mono text-[12px]",style:{color:e.color},children:[e.name,": ",r,t,"%"]},e.name)})]}):null}function g({portfolioId:e,portfolioName:t,analytics:r}){if(!r)return(0,a.jsxs)("div",{className:"min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto",children:[(0,a.jsx)("h1",{className:"font-serif text-2xl text-ink-primary mb-6",children:t}),(0,a.jsxs)("div",{className:"flex flex-col items-center justify-center py-20 gap-3",children:[(0,a.jsx)("p",{className:"font-sans text-sm text-ink-3",children:"No closed positions yet. Analytics require at least 1 completed trade."}),(0,a.jsx)(n(),{href:`/portfolios/${e}`,className:"font-sans text-sm text-accent hover:underline",children:"← Back to portfolio"})]})]});let s=(0,i.useMemo)(()=>{var e;let t,a;return e=r.daily_returns,t=1,a=1,e.map(e=>(t*=1+e.portfolio_return,a*=1+e.nifty50_return,{date:e.date,portfolio:t-1,nifty50:a-1}))},[r.daily_returns]),g=(0,i.useMemo)(()=>y("#1D9E75","portfolio",s.length),[s.length]),E=(0,i.useMemo)(()=>y("#9A8F82","nifty50",s.length),[s.length]),w=r.daily_returns[0]?.date??null,A=r.daily_returns[r.daily_returns.length-1]?.date??null,j=`/api/portfolios/${e}/tv-export`;return(0,a.jsxs)("div",{className:"min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto",children:[(0,a.jsxs)("div",{className:"flex items-start justify-between flex-wrap gap-4 mb-6",children:[(0,a.jsx)("h1",{className:"font-serif text-2xl text-ink-primary",children:t}),(0,a.jsx)("a",{href:j,download:!0,className:"inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[2px] bg-accent text-white font-sans text-sm hover:bg-accent/90 transition-colors",children:"↓ Export to TradingView CSV"})]}),(0,a.jsxs)("div",{className:"grid grid-cols-2 md:grid-cols-7 border border-paper-rule rounded-[2px] bg-paper mb-6 overflow-x-auto",children:[(0,a.jsx)(v,{label:"Sharpe",value:f(r.sharpe,2),subLabel:"Risk-adj return",valueClass:h(r.sharpe),tooltip:null===r.sharpe?"Requires sufficient return history":void 0}),(0,a.jsx)(v,{label:"Sortino",value:f(r.sortino,2),subLabel:"Downside risk",valueClass:h(r.sortino),tooltip:null===r.sortino?"Requires sufficient return history":void 0}),(0,a.jsx)(v,{label:"Calmar",value:f(r.calmar,2),subLabel:"Return / Max DD",valueClass:h(r.calmar),tooltip:null===r.calmar?"Requires drawdown data":void 0}),(0,a.jsx)(v,{label:"Beta",value:f(r.beta,2),subLabel:"vs Nifty 50",valueClass:"text-ink-primary",tooltip:null===r.beta?"Requires 30+ trading days of data":void 0}),(0,a.jsx)(v,{label:"Alpha (Jensen)",value:m(r.alpha),subLabel:"Excess return",valueClass:h(r.alpha),tooltip:null===r.alpha?"Requires benchmark data":void 0}),(0,a.jsx)(v,{label:"Max Drawdown",value:m(r.max_drawdown,!1),subLabel:"Peak to trough",valueClass:h(r.max_drawdown)}),(0,a.jsx)(v,{label:"TWR",value:m(r.twr),subLabel:"Time-weighted",valueClass:h(r.twr)})]}),(0,a.jsxs)("div",{className:"mb-6",children:[(0,a.jsx)("h2",{className:"font-sans text-[10px] font-semibold text-ink-3 uppercase tracking-wider mb-3",children:"Cumulative Returns"}),(0,a.jsx)("div",{className:"border border-paper-rule rounded-[2px] bg-paper p-4",children:(0,a.jsx)("div",{className:"h-[180px] md:h-[240px]",children:(0,a.jsx)(o.u,{width:"100%",height:"100%",children:(0,a.jsxs)(l.b,{data:s,margin:{top:8,right:48,left:0,bottom:0},children:[(0,a.jsx)(c.d,{stroke:"rgba(194,184,168,0.3)",strokeDasharray:"3 3"}),(0,a.jsx)(d.W,{dataKey:"date",tick:{fontSize:10,fill:"#9A8F82",fontFamily:"var(--font-mono)"},tickLine:!1,tickFormatter:e=>{let t=new Date(e);return isNaN(t.getTime())?e:`${t.toLocaleString("en-US",{month:"short"})} '${String(t.getFullYear()).slice(2)}`},minTickGap:60}),(0,a.jsx)(u.h,{tick:{fontSize:10,fill:"#9A8F82",fontFamily:"var(--font-mono)"},tickLine:!1,axisLine:!1,tickFormatter:e=>`${(100*e).toFixed(0)}%`,width:48}),(0,a.jsx)(p.m,{content:(0,a.jsx)(b,{})}),(0,a.jsx)(x.N1,{type:"monotone",dataKey:"portfolio",name:"Portfolio",stroke:"#1D9E75",strokeWidth:2,dot:g,activeDot:{r:3,fill:"#1D9E75"}}),(0,a.jsx)(x.N1,{type:"monotone",dataKey:"nifty50",name:"Nifty 50",stroke:"#9A8F82",strokeWidth:1.5,strokeDasharray:"5 3",dot:E,activeDot:{r:3,fill:"#9A8F82"}})]})})})})]}),(0,a.jsxs)("div",{className:"grid grid-cols-1 md:grid-cols-2 gap-4",children:[(0,a.jsxs)("div",{className:"border border-paper-rule rounded-[2px] bg-paper p-4",children:[(0,a.jsx)("h3",{className:"font-sans text-[10px] font-semibold text-ink-3 uppercase tracking-wider mb-3",children:"Benchmark Comparison"}),(0,a.jsxs)("div",{className:"space-y-2",children:[(0,a.jsxs)("div",{className:"flex items-center justify-between",children:[(0,a.jsx)("span",{className:"font-sans text-[12px] text-ink-3",children:"Alpha (Jensen's)"}),(0,a.jsx)("span",{className:`font-mono text-[13px] font-semibold tabular-nums ${h(r.alpha)}`,children:m(r.alpha)})]}),(0,a.jsxs)("div",{className:"flex items-center justify-between",children:[(0,a.jsx)("span",{className:"font-sans text-[12px] text-ink-3",children:"Beta"}),(0,a.jsx)("span",{className:"font-mono text-[13px] text-ink-primary tabular-nums",children:f(r.beta,2)})]}),(0,a.jsxs)("div",{className:"flex items-center justify-between",children:[(0,a.jsx)("span",{className:"font-sans text-[12px] text-ink-3",children:"Annualised Return"}),(0,a.jsx)("span",{className:`font-mono text-[13px] font-semibold tabular-nums ${h(r.annualised_return)}`,children:m(r.annualised_return)})]}),null!==r.beta&&(0,a.jsxs)("p",{className:"font-sans text-[11px] text-ink-4 mt-2",children:["Beta ",r.beta.toFixed(2)," indicates the portfolio is"," ",r.beta>1?"more":"less"," volatile than Nifty 50."]})]})]}),(0,a.jsxs)("div",{className:"border border-paper-rule rounded-[2px] bg-paper p-4",children:[(0,a.jsx)("h3",{className:"font-sans text-[10px] font-semibold text-ink-3 uppercase tracking-wider mb-3",children:"Observation Summary"}),(0,a.jsxs)("div",{className:"space-y-2",children:[(0,a.jsxs)("div",{className:"flex items-center justify-between",children:[(0,a.jsx)("span",{className:"font-sans text-[12px] text-ink-3",children:"Trading Days"}),(0,a.jsx)("span",{className:"font-mono text-[13px] text-ink-primary tabular-nums",children:r.observation_days})]}),w&&A&&(0,a.jsxs)("div",{className:"flex items-center justify-between",children:[(0,a.jsx)("span",{className:"font-sans text-[12px] text-ink-3",children:"Date Range"}),(0,a.jsxs)("span",{className:"font-mono text-[11px] text-ink-3 tabular-nums",children:[_(w)," — ",_(A)]})]}),(0,a.jsxs)("div",{className:"flex items-center justify-between",children:[(0,a.jsx)("span",{className:"font-sans text-[12px] text-ink-3",children:"Risk-Free Rate (Rf)"}),(0,a.jsxs)("span",{className:"font-mono text-[13px] text-ink-3 tabular-nums",children:[(100*r.risk_free_rate_used).toFixed(2),"%"]})]})]})]})]})]})}},19121:e=>{"use strict";e.exports=require("next/dist/server/app-render/action-async-storage.external.js")},21820:e=>{"use strict";e.exports=require("os")},25858:(e,t,r)=>{"use strict";r.r(t),r.d(t,{default:()=>d,revalidate:()=>c});var a=r(37413);let s=process.env.ATLAS_INTERNAL_API_BASE_URL??"http://13.206.34.214:8002";async function n(e,t={}){let r,a=process.env.ATLAS_INTERNAL_SECRET;if(!a)return{ok:!1,error_code:"config_missing",message:"ATLAS_INTERNAL_SECRET not set on server",status:0};let{method:i="GET",body:o}=t;try{r=await fetch(`${s}${e}`,{method:i,headers:{Authorization:`Bearer ${a}`,...null!=o?{"Content-Type":"application/json"}:{}},body:null!=o?JSON.stringify(o):void 0,cache:"no-store"})}catch(e){return{ok:!1,error_code:"network_error",message:e instanceof Error?e.message:String(e),status:0}}let l=await r.json().catch(()=>null);return r.ok?{ok:!0,data:l?.data??l,status:r.status}:{ok:!1,error_code:l?.detail?.error_code??l?.error_code??"api_error",message:l?.detail?.message??l?.message??`HTTP ${r.status}`,status:r.status}}async function i(e){let t=await n(`/v1/portfolios/${e}/analytics`);if(!t.ok)return null;let r=t.data;return{...r,daily_returns:r.daily_returns??[]}}var o=r(48158),l=r(94879);let c=300;async function d({params:e}){let{id:t}=await e,[r,s,n]=await Promise.all([i(t),(0,l.tn)(t),(0,l.sr)(t)]),c=(s??n)?.name??`Portfolio ${t.slice(0,8)}`;return(0,a.jsx)(o.PortfolioAnalyticsClient,{portfolioId:t,portfolioName:c,analytics:r})}},27779:(e,t,r)=>{Promise.resolve().then(r.bind(r,48158))},27910:e=>{"use strict";e.exports=require("stream")},29021:e=>{"use strict";e.exports=require("fs")},29294:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-async-storage.external.js")},33873:e=>{"use strict";e.exports=require("path")},34631:e=>{"use strict";e.exports=require("tls")},43797:(e,t,r)=>{"use strict";r.r(t),r.d(t,{GlobalError:()=>i.a,__next_app__:()=>u,pages:()=>d,routeModule:()=>p,tree:()=>c});var a=r(65239),s=r(48088),n=r(88170),i=r.n(n),o=r(30893),l={};for(let e in o)0>["default","tree","pages","GlobalError","__next_app__","routeModule"].indexOf(e)&&(l[e]=()=>o[e]);r.d(t,l);let c={children:["",{children:["portfolios",{children:["[id]",{children:["analytics",{children:["__PAGE__",{},{page:[()=>Promise.resolve().then(r.bind(r,25858)),"/home/ubuntu/atlas-os/frontend/src/app/portfolios/[id]/analytics/page.tsx"]}]},{}]},{}]},{}]},{layout:[()=>Promise.resolve().then(r.bind(r,21339)),"/home/ubuntu/atlas-os/frontend/src/app/layout.tsx"],error:[()=>Promise.resolve().then(r.bind(r,54431)),"/home/ubuntu/atlas-os/frontend/src/app/error.tsx"],loading:[()=>Promise.resolve().then(r.bind(r,67393)),"/home/ubuntu/atlas-os/frontend/src/app/loading.tsx"],"not-found":[()=>Promise.resolve().then(r.t.bind(r,57398,23)),"next/dist/client/components/not-found-error"],forbidden:[()=>Promise.resolve().then(r.t.bind(r,89999,23)),"next/dist/client/components/forbidden-error"],unauthorized:[()=>Promise.resolve().then(r.t.bind(r,65284,23)),"next/dist/client/components/unauthorized-error"]}]}.children,d=["/home/ubuntu/atlas-os/frontend/src/app/portfolios/[id]/analytics/page.tsx"],u={require:r,loadChunk:()=>Promise.resolve()},p=new a.AppPageRouteModule({definition:{kind:s.RouteKind.APP_PAGE,page:"/portfolios/[id]/analytics/page",pathname:"/portfolios/[id]/analytics",bundlePath:"",filename:"",appPaths:[]},userland:{loaderTree:c}})},48158:(e,t,r)=>{"use strict";r.d(t,{PortfolioAnalyticsClient:()=>s});var a=r(12907);let s=(0,a.registerClientReference)(function(){throw Error("Attempted to call PortfolioAnalyticsClient() from the server but PortfolioAnalyticsClient is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/v6/PortfolioAnalyticsClient.tsx","PortfolioAnalyticsClient");(0,a.registerClientReference)(function(){throw Error("Attempted to call the default export of \"/home/ubuntu/atlas-os/frontend/src/components/v6/PortfolioAnalyticsClient.tsx\" from the server, but it's on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/components/v6/PortfolioAnalyticsClient.tsx","default")},55511:e=>{"use strict";e.exports=require("crypto")},63033:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},74998:e=>{"use strict";e.exports=require("perf_hooks")},85168:(e,t,r)=>{"use strict";r.d(t,{d:()=>F});var a=r(43210),s=r(10521),n=r(22989),i=r(64279),o=r(53566),l=r(16862),c=r(51426),d=r(39102),u=r(43209),p=r(83409),x=r(73865),f=r(99857),m=r(12128),h=r(3081),_=r(30405),y=["x1","y1","x2","y2","key"],v=["offset"],b=["xAxisId","yAxisId"],g=["xAxisId","yAxisId"];function E(e,t){var r=Object.keys(e);if(Object.getOwnPropertySymbols){var a=Object.getOwnPropertySymbols(e);t&&(a=a.filter(function(t){return Object.getOwnPropertyDescriptor(e,t).enumerable})),r.push.apply(r,a)}return r}function w(e){for(var t=1;t<arguments.length;t++){var r=null!=arguments[t]?arguments[t]:{};t%2?E(Object(r),!0).forEach(function(t){var a,s,n;a=e,s=t,n=r[t],(s=function(e){var t=function(e,t){if("object"!=typeof e||!e)return e;var r=e[Symbol.toPrimitive];if(void 0!==r){var a=r.call(e,t||"default");if("object"!=typeof a)return a;throw TypeError("@@toPrimitive must return a primitive value.")}return("string"===t?String:Number)(e)}(e,"string");return"symbol"==typeof t?t:t+""}(s))in a?Object.defineProperty(a,s,{value:n,enumerable:!0,configurable:!0,writable:!0}):a[s]=n}):Object.getOwnPropertyDescriptors?Object.defineProperties(e,Object.getOwnPropertyDescriptors(r)):E(Object(r)).forEach(function(t){Object.defineProperty(e,t,Object.getOwnPropertyDescriptor(r,t))})}return e}function A(){return(A=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var a in r)({}).hasOwnProperty.call(r,a)&&(e[a]=r[a])}return e}).apply(null,arguments)}function j(e,t){if(null==e)return{};var r,a,s=function(e,t){if(null==e)return{};var r={};for(var a in e)if(({}).hasOwnProperty.call(e,a)){if(-1!==t.indexOf(a))continue;r[a]=e[a]}return r}(e,t);if(Object.getOwnPropertySymbols){var n=Object.getOwnPropertySymbols(e);for(a=0;a<n.length;a++)r=n[a],-1===t.indexOf(r)&&({}).propertyIsEnumerable.call(e,r)&&(s[r]=e[r])}return s}var k=e=>{var{fill:t}=e;if(!t||"none"===t)return null;var{fillOpacity:r,x:s,y:n,width:i,height:o,ry:l}=e;return a.createElement("rect",{x:s,y:n,ry:l,width:i,height:o,stroke:"none",fill:t,fillOpacity:r,className:"recharts-cartesian-grid-bg"})};function N(e){var{option:t,lineItemProps:r}=e;if(a.isValidElement(t))s=a.cloneElement(t,r);else if("function"==typeof t)s=t(r);else{var s,n,{x1:i,y1:o,x2:l,y2:c,key:d}=r,u=j(r,y),p=null!=(n=(0,f.uZ)(u))?n:{},{offset:x}=p,m=j(p,v);s=a.createElement("line",A({},m,{x1:i,y1:o,x2:l,y2:c,fill:"none",key:d}))}return s}function R(e){var{x:t,width:r,horizontal:s=!0,horizontalPoints:n}=e;if(!s||!n||!n.length)return null;var{xAxisId:i,yAxisId:o}=e,l=j(e,b),c=n.map((e,n)=>{var i=w(w({},l),{},{x1:t,y1:e,x2:t+r,y2:e,key:"line-".concat(n),index:n});return a.createElement(N,{key:"line-".concat(n),option:s,lineItemProps:i})});return a.createElement("g",{className:"recharts-cartesian-grid-horizontal"},c)}function S(e){var{y:t,height:r,vertical:s=!0,verticalPoints:n}=e;if(!s||!n||!n.length)return null;var{xAxisId:i,yAxisId:o}=e,l=j(e,g),c=n.map((e,n)=>{var i=w(w({},l),{},{x1:e,y1:t,x2:e,y2:t+r,key:"line-".concat(n),index:n});return a.createElement(N,{option:s,lineItemProps:i,key:"line-".concat(n)})});return a.createElement("g",{className:"recharts-cartesian-grid-vertical"},c)}function O(e){var{horizontalFill:t,fillOpacity:r,x:s,y:n,width:i,height:o,horizontalPoints:l,horizontal:c=!0}=e;if(!c||!t||!t.length||null==l)return null;var d=l.map(e=>Math.round(e+n-n)).sort((e,t)=>e-t);n!==d[0]&&d.unshift(0);var u=d.map((e,l)=>{var c=d[l+1],u=null==c?n+o-e:c-e;if(u<=0)return null;var p=l%t.length;return a.createElement("rect",{key:"react-".concat(l),y:e,x:s,height:u,width:i,stroke:"none",fill:t[p],fillOpacity:r,className:"recharts-cartesian-grid-bg"})});return a.createElement("g",{className:"recharts-cartesian-gridstripes-horizontal"},u)}function L(e){var{vertical:t=!0,verticalFill:r,fillOpacity:s,x:n,y:i,width:o,height:l,verticalPoints:c}=e;if(!t||!r||!r.length)return null;var d=c.map(e=>Math.round(e+n-n)).sort((e,t)=>e-t);n!==d[0]&&d.unshift(0);var u=d.map((e,t)=>{var c=d[t+1],u=null==c?n+o-e:c-e;if(u<=0)return null;var p=t%r.length;return a.createElement("rect",{key:"react-".concat(t),x:e,y:i,width:u,height:l,stroke:"none",fill:r[p],fillOpacity:s,className:"recharts-cartesian-grid-bg"})});return a.createElement("g",{className:"recharts-cartesian-gridstripes-vertical"},u)}var T=(e,t)=>{var{xAxis:r,width:a,height:s,offset:n}=e;return(0,i.PW)((0,o.f)(w(w(w({},l.F),r),{},{ticks:(0,i.Rh)(r,!0),viewBox:{x:0,y:0,width:a,height:s}})),n.left,n.left+n.width,t)},C=(e,t)=>{var{yAxis:r,width:a,height:s,offset:n}=e;return(0,i.PW)((0,o.f)(w(w(w({},l.F),r),{},{ticks:(0,i.Rh)(r,!0),viewBox:{x:0,y:0,width:a,height:s}})),n.top,n.top+n.height,t)},P={horizontal:!0,vertical:!0,horizontalPoints:[],verticalPoints:[],stroke:"#ccc",fill:"none",verticalFill:[],horizontalFill:[],xAxisId:0,yAxisId:0,syncWithTicks:!1,zIndex:_.I.grid};function F(e){var t=(0,c.yi)(),r=(0,c.rY)(),i=(0,c.W7)(),o=w(w({},(0,x.e)(e,P)),{},{x:(0,n.Et)(e.x)?e.x:i.left,y:(0,n.Et)(e.y)?e.y:i.top,width:(0,n.Et)(e.width)?e.width:i.width,height:(0,n.Et)(e.height)?e.height:i.height}),{xAxisId:l,yAxisId:f,x:_,y,width:v,height:b,syncWithTicks:g,horizontalValues:E,verticalValues:j}=o,N=(0,p.r)(),F=(0,u.G)(e=>(0,d.ZB)(e,"xAxis",l,N)),I=(0,u.G)(e=>(0,d.ZB)(e,"yAxis",f,N));if(!(0,m.F)(v)||!(0,m.F)(b)||!(0,n.Et)(_)||!(0,n.Et)(y))return null;var D=o.verticalCoordinatesGenerator||T,M=o.horizontalCoordinatesGenerator||C,{horizontalPoints:$,verticalPoints:q}=o;if((!$||!$.length)&&"function"==typeof M){var B=E&&E.length,W=M({yAxis:I?w(w({},I),{},{ticks:B?E:I.ticks}):void 0,width:null!=t?t:v,height:null!=r?r:b,offset:i},!!B||g);(0,s.R)(Array.isArray(W),"horizontalCoordinatesGenerator should return Array but instead it returned [".concat(typeof W,"]")),Array.isArray(W)&&($=W)}if((!q||!q.length)&&"function"==typeof D){var z=j&&j.length,U=D({xAxis:F?w(w({},F),{},{ticks:z?j:F.ticks}):void 0,width:null!=t?t:v,height:null!=r?r:b,offset:i},!!z||g);(0,s.R)(Array.isArray(U),"verticalCoordinatesGenerator should return Array but instead it returned [".concat(typeof U,"]")),Array.isArray(U)&&(q=U)}return a.createElement(h.g,{zIndex:o.zIndex},a.createElement("g",{className:"recharts-cartesian-grid"},a.createElement(k,{fill:o.fill,fillOpacity:o.fillOpacity,x:o.x,y:o.y,width:o.width,height:o.height,ry:o.ry}),a.createElement(O,A({},o,{horizontalPoints:$})),a.createElement(L,A({},o,{verticalPoints:q})),a.createElement(R,A({},o,{offset:i,horizontalPoints:$,xAxis:F,yAxis:I})),a.createElement(S,A({},o,{offset:i,verticalPoints:q,xAxis:F,yAxis:I}))))}F.displayName="CartesianGrid"},91645:e=>{"use strict";e.exports=require("net")},93435:(e,t,r)=>{Promise.resolve().then(r.bind(r,15632))},94879:(e,t,r)=>{"use strict";r.d(t,{JL:()=>s,Q5:()=>o,sr:()=>i,tn:()=>n});var a=r(5069);async function s(){return(await (0,a.A)`
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
  `).filter(e=>!function(e){let t=e.trim().toLowerCase();return t.includes("(auto-created)")||t.startsWith("validate_")}(e.name))}async function n(e){return(await (0,a.A)`
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
  `)[0]??null}async function i(e){return(await (0,a.A)`
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
  `)[0]??null}async function o(e,t,r=50){return"static"===t?(0,a.A)`
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
      LIMIT ${r}
    `:(0,a.A)`
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
    LIMIT ${r}
  `}}};var t=require("../../../../webpack-runtime.js");t.C(e);var r=e=>t(t.s=e),a=t.X(0,[4447,3971,9626,346,6835,4613],()=>r(43797));module.exports=a})();