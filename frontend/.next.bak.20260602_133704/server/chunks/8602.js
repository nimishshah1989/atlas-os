"use strict";exports.id=8602,exports.ids=[8602],exports.modules={9374:(e,t,r)=>{r.d(t,{q:()=>l});var s=r(37413),n=r(83799),a=r(20543),i=r(20787);function l({holdings:e,asOfDate:t}){return 0===e.length?(0,s.jsxs)("div",{className:"border border-paper-rule rounded-sm",children:[(0,s.jsxs)("div",{className:"px-4 py-3 border-b border-paper-rule flex items-center gap-2",children:[(0,s.jsx)(n.A,{className:"w-3.5 h-3.5 text-teal"}),(0,s.jsx)("span",{className:"font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide",children:"RS Leader & Strong Holdings"})]}),(0,s.jsx)("div",{className:"px-4 py-4",children:(0,s.jsx)("p",{className:"font-sans text-xs text-ink-tertiary",children:"None of the current holdings are classified as RS Leader or Strong."})})]}):(0,s.jsxs)("div",{className:"border border-paper-rule rounded-sm",children:[(0,s.jsxs)("div",{className:"px-4 py-3 border-b border-paper-rule flex items-center gap-2",children:[(0,s.jsx)(n.A,{className:"w-3.5 h-3.5 text-teal"}),(0,s.jsx)("span",{className:"font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide",children:"RS Leader & Strong Holdings"}),(0,s.jsxs)("span",{className:"font-sans text-[11px] text-ink-tertiary",children:[e.length," of current portfolio"]}),t&&(0,s.jsx)("span",{className:"ml-auto font-sans text-[11px] text-ink-tertiary",children:t})]}),(0,s.jsx)("div",{className:"px-4 py-3 overflow-x-auto",children:(0,s.jsxs)("table",{className:"w-full border-collapse",children:[(0,s.jsx)("thead",{children:(0,s.jsxs)("tr",{className:"border-b border-paper-rule",children:[(0,s.jsx)("th",{className:"pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary",children:"Symbol"}),(0,s.jsx)("th",{className:"pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden sm:table-cell",children:"Sector"}),(0,s.jsx)("th",{className:"pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary",children:"Weight"}),(0,s.jsx)("th",{className:"pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary pl-4",children:"RS State"}),(0,s.jsx)("th",{className:"pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden md:table-cell",children:"Momentum"}),(0,s.jsx)("th",{className:"pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary",children:"RS Pctile"})]})}),(0,s.jsx)("tbody",{children:e.map(e=>(0,s.jsxs)("tr",{className:"border-b border-paper-rule last:border-0 hover:bg-paper-rule/10",children:[(0,s.jsxs)("td",{className:"py-1.5 pr-3",children:[(0,s.jsx)(i.yd,{symbol:e.symbol,className:"font-semibold"}),(0,s.jsx)("div",{className:"font-sans text-[10px] text-ink-tertiary truncate max-w-[140px]",children:e.company_name})]}),(0,s.jsx)("td",{className:"py-1.5 pr-3 hidden sm:table-cell",children:(0,s.jsx)("span",{className:"font-sans text-[10px] text-ink-secondary",children:e.sector??"—"})}),(0,s.jsx)("td",{className:"py-1.5 text-right font-mono text-xs tabular-nums text-ink-secondary",children:function(e){if(null==e)return"—";let t=100*parseFloat(e);return`${t>=0?"+":""}${t.toFixed(1)}%`}(e.weight)}),(0,s.jsx)("td",{className:"py-1.5 pl-4 pr-3",children:(0,s.jsx)(a.p0,{value:e.rs_state})}),(0,s.jsx)("td",{className:"py-1.5 pr-3 hidden md:table-cell",children:(0,s.jsx)(a.DB,{value:e.momentum_state})}),(0,s.jsx)("td",{className:"py-1.5 text-right",children:(0,s.jsx)(a.WI,{value:e.rs_pctile_3m})})]},e.instrument_id))})]})})]})}},20543:(e,t,r)=>{r.d(t,{DB:()=>g,WI:()=>a,p0:()=>x});var s=r(37413),n=r(90808);function a({value:e}){if(null==e)return(0,s.jsx)("span",{className:"font-mono text-xs text-ink-tertiary",children:"—"});let t=parseFloat(e),r=(100*t).toFixed(0),a=t>=.7?n.OK.rsLeader:t>=.4?n.OK.rsConsolidating:n.OK.rsWeak;return(0,s.jsxs)("div",{className:"flex items-center gap-2 justify-end",children:[(0,s.jsx)("div",{className:"w-10 h-1.5 bg-paper-rule rounded-full overflow-hidden",children:(0,s.jsx)("div",{className:"h-full rounded-full",style:{width:`${Math.round(100*t)}%`,background:a}})}),(0,s.jsx)("span",{className:"font-mono text-xs tabular-nums",style:{color:a},children:r})]})}let i={Leader:"bg-signal-pos/20 text-signal-pos",Strong:"bg-signal-pos/10 text-signal-pos",Consolidating:"bg-teal/15 text-teal",Emerging:"bg-signal-warn/15 text-signal-warn",Average:"bg-ink-tertiary/10 text-ink-secondary",Weak:"bg-signal-neg/10 text-signal-neg",Laggard:"bg-signal-neg/20 text-signal-neg"},l={Leader:"Leader",Strong:"Strong",Consolidating:"Consol",Emerging:"Emrg",Average:"Avg",Weak:"Weak",Laggard:"Laggard"},o={Accelerating:"bg-signal-pos/20 text-signal-pos",Improving:"bg-signal-pos/10 text-signal-pos",Flat:"bg-ink-tertiary/10 text-ink-secondary",Deteriorating:"bg-signal-neg/10 text-signal-neg",Collapsing:"bg-signal-neg/20 text-signal-neg"},d={Accelerating:"Accel",Improving:"Impr",Flat:"Flat",Deteriorating:"Det",Collapsing:"Coll"},c={Low:"bg-signal-pos/10 text-signal-pos",Normal:"bg-ink-tertiary/10 text-ink-secondary",Elevated:"bg-signal-warn/15 text-signal-warn",High:"bg-signal-neg/15 text-signal-neg","Below Trend":"bg-purple-100 text-purple-700"},m={Low:"Low",Normal:"Norm",Elevated:"Elev",High:"High","Below Trend":"↓ Trnd"};function p({label:e,style:t,raw:r}){return r?r.startsWith("ILLIQUID")?(0,s.jsx)("span",{className:"inline-flex items-center px-1 py-0.5 rounded-[2px] font-sans text-[9px] font-semibold bg-ink-tertiary/10 text-ink-tertiary",title:"Low trading volume — not tradeable",children:"Illiq"}):r.startsWith("INSUFFICIENT")?(0,s.jsx)("span",{className:"inline-flex items-center px-1 py-0.5 rounded-[2px] font-sans text-[9px] font-semibold bg-ink-tertiary/10 text-ink-tertiary",title:"Insufficient price history",children:"Insuf"}):r.startsWith("DISLOCATION")?(0,s.jsx)("span",{className:"inline-flex items-center px-1 py-0.5 rounded-[2px] font-sans text-[9px] font-semibold bg-signal-warn/10 text-signal-warn",title:"Market dislocation — suspended",children:"Disl"}):(0,s.jsx)("span",{className:`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${t}`,title:r,children:e}):(0,s.jsx)("span",{className:"font-mono text-[10px] text-ink-tertiary",children:"—"})}function x({value:e}){let t=e?i[e]??"bg-ink-tertiary/10 text-ink-secondary":"",r=e?l[e]??e:"";return(0,s.jsx)(p,{raw:e,label:r,style:t})}function g({value:e}){let t=e?o[e]??"bg-ink-tertiary/10 text-ink-secondary":"",r=e?d[e]??e:"";return(0,s.jsx)(p,{raw:e,label:r,style:t})}},20787:(e,t,r)=>{r.d(t,{Cx:()=>o,yd:()=>l});var s=r(37413),n=r(4536),a=r.n(n);function i(){return(0,s.jsx)("span",{className:"font-mono text-xs text-ink-tertiary",children:"—"})}function l({symbol:e,className:t=""}){return e?(0,s.jsx)(a(),{href:`/stocks/${encodeURIComponent(e)}`,className:`text-ink-primary hover:text-teal hover:underline transition-colors ${t}`,children:e}):i()}function o({sector:e,className:t=""}){return e?(0,s.jsx)(a(),{href:`/sectors/${encodeURIComponent(e)}`,className:`text-ink-secondary hover:text-teal hover:underline transition-colors ${t}`,children:e}):i()}},26373:(e,t,r)=>{r.d(t,{A:()=>o});var s=r(61120);let n=e=>e.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),a=(...e)=>e.filter((e,t,r)=>!!e&&""!==e.trim()&&r.indexOf(e)===t).join(" ").trim();var i={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:2,strokeLinecap:"round",strokeLinejoin:"round"};let l=(0,s.forwardRef)(({color:e="currentColor",size:t=24,strokeWidth:r=2,absoluteStrokeWidth:n,className:l="",children:o,iconNode:d,...c},m)=>(0,s.createElement)("svg",{ref:m,...i,width:t,height:t,stroke:e,strokeWidth:n?24*Number(r)/Number(t):r,className:a("lucide",l),...c},[...d.map(([e,t])=>(0,s.createElement)(e,t)),...Array.isArray(o)?o:[o]])),o=(e,t)=>{let r=(0,s.forwardRef)(({className:r,...i},o)=>(0,s.createElement)(l,{ref:o,iconNode:t,className:a(`lucide-${n(e)}`,r),...i}));return r.displayName=`${e}`,r}},38904:(e,t,r)=>{r.d(t,{X:()=>l});var s=r(43210),n=r(49605),a=r(12042),i=["axis"],l=(0,s.forwardRef)((e,t)=>s.createElement(a.P,{chartName:"ComposedChart",defaultTooltipEventType:"axis",validateTooltipEventTypes:i,tooltipPayloadSearcher:n.uN,categoricalChartProps:e,ref:t}))},78246:(e,t,r)=>{r.d(t,{AI:()=>n,Jw:()=>o,KC:()=>a,nq:()=>i,pu:()=>l});var s=r(5069);async function n(e=null,t=100){if(t<1||t>500)throw Error(`limit must be between 1 and 500, got: ${t}`);return null!==e?(0,s.A)`
      SELECT
        instrument_id,
        date,
        symbol,
        company_name,
        sector,
        tier,
        rs_pctile_3m::text   AS rs_pctile_3m,
        rs_pctile_1m::text   AS rs_pctile_1m,
        ret_6m::text         AS ret_6m,
        rs_state,
        momentum_state,
        state_since_date
      FROM atlas.mv_rs_leaders_daily
      WHERE sector = ${e}
      ORDER BY rs_pctile_3m DESC NULLS LAST
      LIMIT ${t}
    `:(0,s.A)`
    SELECT
      instrument_id,
      date,
      symbol,
      company_name,
      sector,
      tier,
      rs_pctile_3m::text   AS rs_pctile_3m,
      rs_pctile_1m::text   AS rs_pctile_1m,
      ret_6m::text         AS ret_6m,
      rs_state,
      momentum_state,
      state_since_date
    FROM atlas.mv_rs_leaders_daily
    ORDER BY rs_pctile_3m DESC NULLS LAST
    LIMIT ${t}
  `}async function a(){return(0,s.A)`
    SELECT
      instrument_id,
      date,
      symbol,
      company_name,
      sector,
      tier,
      new_rs_state,
      prior_rs_state,
      momentum_state,
      state_since_date,
      rs_pctile_3m::text   AS rs_pctile_3m
    FROM atlas.mv_breakout_candidates
    ORDER BY rs_pctile_3m DESC NULLS LAST
  `}async function i(){return(0,s.A)`
    SELECT
      instrument_id,
      date,
      symbol,
      company_name,
      sector,
      tier,
      new_rs_state,
      prior_rs_state,
      momentum_state,
      state_since_date,
      rs_pctile_3m::text   AS rs_pctile_3m
    FROM atlas.mv_deterioration_watch
    ORDER BY rs_pctile_3m DESC NULLS LAST
  `}async function l(e){return(0,s.A)`
    SELECT
      h.instrument_id,
      l.symbol,
      l.company_name,
      l.sector,
      (h.weight_pct / 100)::text AS weight,
      l.rs_state,
      l.rs_pctile_3m::text       AS rs_pctile_3m,
      l.momentum_state
    FROM de_mf_holdings h
    INNER JOIN atlas.mv_rs_leaders_daily l USING (instrument_id)
    WHERE h.mstar_id   = ${e}
      AND h.as_of_date = (
        SELECT MAX(as_of_date) FROM de_mf_holdings WHERE mstar_id = ${e}
      )
    ORDER BY l.rs_pctile_3m DESC NULLS LAST
  `}async function o(e){return(0,s.A)`
    SELECT
      h.instrument_id,
      l.symbol,
      l.company_name,
      l.sector,
      h.weight::text       AS weight,
      l.rs_state,
      l.rs_pctile_3m::text AS rs_pctile_3m,
      l.momentum_state
    FROM de_etf_holdings h
    INNER JOIN atlas.mv_rs_leaders_daily l USING (instrument_id)
    WHERE h.ticker    = ${e}
      AND h.as_of_date = (
        SELECT MAX(as_of_date) FROM de_etf_holdings WHERE ticker = ${e}
      )
    ORDER BY l.rs_pctile_3m DESC NULLS LAST
  `}},83799:(e,t,r)=>{r.d(t,{A:()=>s});let s=(0,r(26373).A)("TrendingUp",[["polyline",{points:"22 7 13.5 15.5 8.5 10.5 2 17",key:"126l90"}],["polyline",{points:"16 7 22 7 22 13",key:"kwv8wd"}]])},90808:(e,t,r)=>{r.d(t,{OK:()=>s,ql:()=>n});let s={rsLeader:"#2F6B43",rsStrong:"#1D9E75",rsEmerging:"#25394A",rsConsolidating:"#B8860B",rsAverage:"#8C8278",rsWeak:"#B0492C",rsLaggard:"#B0492C",momAccelerating:"#2F6B43",momImproving:"#1D9E75",momFlat:"#8C8278",momDeteriorating:"#B8860B",momCollapsing:"#B0492C",riskOn:"#2F6B43",constructive:"#1D9E75",cautious:"#B8860B",riskOff:"#B0492C",grid:"#C2B8A8",inkTertiary:"#8C8278",paper:"#F8F4EC"};function n(e){switch(e){case"Leader":return s.rsLeader;case"Strong":return s.rsStrong;case"Emerging":return s.rsEmerging;case"Consolidating":return s.rsConsolidating;case"Average":return s.rsAverage;case"Weak":return s.rsWeak;case"Laggard":return s.rsLaggard;default:return s.inkTertiary}}}};