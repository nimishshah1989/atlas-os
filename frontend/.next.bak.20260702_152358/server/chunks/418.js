exports.id=418,exports.ids=[418],exports.modules={4536:(e,t,n)=>{let{createProxy:s}=n(39844);e.exports=s("/home/ubuntu/atlas-os/frontend/node_modules/next/dist/client/app-dir/link.js")},6707:(e,t,n)=>{"use strict";n.d(t,{Ro:()=>a,oT:()=>r});let s=new Set(["—","-","N/A","n/a","NaN","nan","null","undefined"]);function a(e){if(null==e)return null;let t="string"==typeof e?e.trim():e;if(""===t||"string"==typeof t&&s.has(t))return null;let n=Number(t);if(!Number.isFinite(n))throw TypeError(`toNumber: "${e}" is not a valid number`);return n}function r(e,t){let n=a(e);return null===n?t:n}new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",minimumFractionDigits:2,maximumFractionDigits:2})},22337:(e,t,n)=>{"use strict";n.r(t),n.d(t,{TermInfo:()=>l});var s=n(60687),a=n(43210),r=n(51215),i=n(84504);function l({term:e,title:t,body:n}){let l=e?i.V[e]:void 0,o=t??l?.title,d=n??l?.body,c=(0,a.useRef)(null),[m,u]=(0,a.useState)(!1),[h,x]=(0,a.useState)(null),_=(0,a.useCallback)(()=>{let e=c.current;if(!e)return;let t=e.getBoundingClientRect(),n=t.top<130;x({left:t.left+t.width/2,top:n?t.bottom+6:t.top-6,below:n})},[]);return d?(0,s.jsxs)("span",{className:"relative inline-flex align-middle",children:[(0,s.jsx)("button",{ref:c,type:"button","aria-label":`What is ${o}?`,onClick:e=>{e.preventDefault(),e.stopPropagation(),_(),u(e=>!e)},onMouseEnter:()=>{_(),u(!0)},onMouseLeave:()=>u(!1),onFocus:()=>{_(),u(!0)},onBlur:()=>u(!1),className:"ml-1 inline-flex h-[14px] w-[14px] items-center justify-center rounded-full text-txt-3 hover:text-brand focus:text-brand focus:outline-none",children:(0,s.jsxs)("svg",{viewBox:"0 0 24 24",width:"12",height:"12",fill:"none",stroke:"currentColor",strokeWidth:"2",strokeLinecap:"round",strokeLinejoin:"round","aria-hidden":"true",children:[(0,s.jsx)("path",{d:"M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"}),(0,s.jsx)("circle",{cx:"12",cy:"12",r:"2.6"})]})}),m&&h&&"undefined"!=typeof document&&(0,r.createPortal)((0,s.jsxs)("span",{role:"tooltip",style:{position:"fixed",left:h.left,top:h.top,transform:h.below?"translate(-50%, 0)":"translate(-50%, -100%)"},className:"pointer-events-none z-[100] block w-[260px] rounded-tile border border-edge-rule bg-surface-raised px-3 py-2 text-left shadow-panel",children:[(0,s.jsx)("span",{className:"block font-num text-[10px] font-semibold uppercase tracking-[0.12em] text-txt-1",children:o}),(0,s.jsx)("span",{className:"mt-1 block font-sans text-[11.5px] leading-[1.45] text-txt-2",children:d})]}),document.body)]}):null}},32936:(e,t,n)=>{"use strict";n.d(t,{h:()=>l});var s=n(37413),a=n(4536),r=n.n(a);let i={pos:"var(--color-sig-pos)",neg:"var(--color-sig-neg)",warn:"var(--color-sig-warn)",neutral:"var(--color-txt-1)",brand:"var(--color-brand)"};function l({label:e,value:t,unit:n,sub:a,delta:l,tone:o="neutral",href:d,children:c}){let m=(0,s.jsxs)(s.Fragment,{children:[(0,s.jsxs)("div",{className:"flex items-center justify-between gap-2",children:[(0,s.jsx)("span",{className:"font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:e}),d&&(0,s.jsx)("span",{className:"font-num text-[12px] text-txt-3 transition-colors group-hover/stat:text-brand",children:"→"})]}),(0,s.jsxs)("div",{className:"mt-2 flex items-baseline gap-1",children:[(0,s.jsx)("span",{className:"font-display text-[30px] font-semibold leading-none tracking-tight tabular-nums",style:{color:i[o]},children:t}),n&&(0,s.jsx)("span",{className:"font-num text-[13px] text-txt-2",children:n})]}),c&&(0,s.jsx)("div",{className:"mt-2.5",children:c}),(a||l)&&(0,s.jsxs)("div",{className:"mt-2 flex items-center gap-2",children:[a&&(0,s.jsx)("span",{className:"font-sans text-[11px] text-txt-2",children:a}),l&&(0,s.jsx)("span",{className:"font-num text-[11px] tabular-nums",style:{color:i[l.tone]},children:l.value})]})]}),u="group/stat block rounded-tile border border-edge-hair bg-surface-raised px-4 py-3.5 shadow-tile transition-colors";return d?(0,s.jsx)(r(),{href:d,className:`${u} hover:border-edge-strong hover:bg-surface-raised`,children:m}):(0,s.jsx)("div",{className:u,children:m})}},37464:(e,t,n)=>{"use strict";n.d(t,{h:()=>l});var s=n(37413);let a={pos:"var(--color-sig-pos)",neg:"var(--color-sig-neg)",neutral:"var(--color-txt-3)"};function r(e){if(0===e.length)return[0,1];let t=Math.min(...e),n=Math.max(...e);t===n&&(t-=1,n+=1);let s=(n-t)*.08;return[t-s,n+s]}function i(e){if(0===e.length)return 0;let t=[...e].sort((e,t)=>e-t);return t[Math.floor(t.length/2)]}function l({points:e,xLabel:t,yLabel:n,sizeLabel:l,xFmt:o=e=>e.toFixed(0),yFmt:d=e=>e.toFixed(0)}){if(0===e.length)return(0,s.jsx)("div",{className:"flex h-64 items-center justify-center rounded-tile border border-edge-hair bg-surface-panel font-sans text-[13px] text-txt-3",children:"No data available."});let[c,m]=r(e.map(e=>e.x)),[u,h]=r(e.map(e=>e.y)),x=Math.max(...e.map(e=>Math.max(0,e.size)),1),_=e=>60+(e-c)/(m-c)*732,f=e=>386-(e-u)/(h-u)*356,N=e=>6+20*Math.sqrt(Math.max(0,e)/x),E=_(i(e.map(e=>e.x))),p=f(i(e.map(e=>e.y))),L=[...e].sort((e,t)=>t.size-e.size);return(0,s.jsxs)("div",{className:"rounded-tile border border-edge-hair bg-surface-panel",children:[(0,s.jsxs)("div",{className:"flex flex-wrap items-center gap-3 border-b border-edge-hair px-4 py-2",children:[(0,s.jsxs)("span",{className:"font-num text-[10px] uppercase tracking-wider text-txt-3",children:["Bubble size = ",l]}),(0,s.jsxs)("span",{className:"ml-auto font-num text-[10px] tabular-nums text-txt-3",children:[e.length," instruments \xb7 hover for detail, click to open"]})]}),(0,s.jsx)("div",{className:"px-2 py-2",children:(0,s.jsxs)("svg",{viewBox:"0 0 820 440",width:"100%",role:"img","aria-label":`${n} vs ${t} bubble chart`,className:"font-num",children:[[c,(c+m)/2,m].map((e,t)=>(0,s.jsxs)("g",{children:[(0,s.jsx)("line",{x1:_(e),y1:30,x2:_(e),y2:386,stroke:"var(--color-edge-hair)",strokeWidth:1}),(0,s.jsx)("text",{x:_(e),y:404,textAnchor:"middle",fontSize:10,fill:"var(--color-txt-3)",children:o(e)})]},`x${t}`)),[u,(u+h)/2,h].map((e,t)=>(0,s.jsxs)("g",{children:[(0,s.jsx)("line",{x1:60,y1:f(e),x2:792,y2:f(e),stroke:"var(--color-edge-hair)",strokeWidth:1}),(0,s.jsx)("text",{x:52,y:f(e)+3,textAnchor:"end",fontSize:10,fill:"var(--color-txt-3)",children:d(e)})]},`y${t}`)),(0,s.jsx)("line",{x1:E,y1:30,x2:E,y2:386,stroke:"var(--color-edge-rule)",strokeDasharray:"4 3",strokeWidth:1}),(0,s.jsx)("line",{x1:60,y1:p,x2:792,y2:p,stroke:"var(--color-edge-rule)",strokeDasharray:"4 3",strokeWidth:1}),(0,s.jsx)("text",{x:426,y:432,textAnchor:"middle",fontSize:11,fontWeight:600,fill:"var(--color-txt-2)",children:t}),(0,s.jsx)("text",{x:16,y:208,textAnchor:"middle",fontSize:11,fontWeight:600,fill:"var(--color-txt-2)",transform:`rotate(-90 16 ${208})`,children:n}),L.map(e=>(0,s.jsx)("a",{href:e.href,"aria-label":e.label,children:(0,s.jsx)("circle",{cx:_(e.x),cy:f(e.y),r:N(e.size),fill:a[e.tone],fillOpacity:.62,stroke:a[e.tone],strokeWidth:1,style:{cursor:"pointer"},children:(0,s.jsx)("title",{children:`${e.label}
${t}: ${o(e.x)} \xb7 ${n}: ${d(e.y)}${e.sub?`
${e.sub}`:""}`})})},e.id))]})})]})}},60021:(e,t,n)=>{"use strict";n.d(t,{Z:()=>r});var s=n(37413);function a({title:e,children:t}){return(0,s.jsxs)("span",{className:"group/info relative inline-flex",children:[(0,s.jsx)("button",{type:"button","aria-label":e?`About ${e}`:"More info",className:"grid h-[17px] w-[17px] place-items-center rounded-full border border-brand/50 bg-brand/5 font-num text-[10px] font-semibold italic leading-none text-brand transition-colors hover:border-brand hover:bg-brand/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",children:"i"}),(0,s.jsxs)("span",{role:"tooltip",className:"pointer-events-none absolute left-1/2 top-[150%] z-50 w-[280px] -translate-x-1/2 rounded-tile border border-edge-rule bg-surface-raised p-3 text-[11.5px] leading-[1.55] text-txt-2 opacity-0 shadow-panel transition-opacity duration-150 group-hover/info:opacity-100 group-focus-within/info:opacity-100",children:[e&&(0,s.jsx)("span",{className:"mb-1 block font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:e}),t]})]})}function r({title:e,eyebrow:t,info:n,action:r,children:i,className:l="",bodyClassName:o=""}){let d=e||t||n||r;return(0,s.jsxs)("section",{className:`rounded-panel border border-edge-hair bg-surface-panel shadow-panel ${l}`,children:[d&&(0,s.jsxs)("header",{className:"flex items-center gap-2.5 border-b border-edge-hair px-5 py-3.5",children:[(0,s.jsxs)("div",{className:"min-w-0",children:[t&&(0,s.jsx)("div",{className:"font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:t}),e&&(0,s.jsx)("h2",{className:"font-display text-[15px] font-medium leading-tight text-txt-1",children:e})]}),n&&(0,s.jsx)(a,{title:n.title,children:n.body}),r&&(0,s.jsx)("div",{className:"ml-auto shrink-0",children:r})]}),(0,s.jsx)("div",{className:o||"px-5 py-4",children:i})]})}},63568:(e,t,n)=>{"use strict";function s(e){let t=e.filter(e=>Number.isFinite(e)).sort((e,t)=>e-t);if(0===t.length)return[0,0];let n=e=>t[Math.min(t.length-1,Math.max(0,Math.ceil(e*t.length)-1))];return[n(.25),n(.75)]}function a(e,t,n){return null!=e&&Number.isFinite(e)?e>=n?"pos":e<t?"neg":"neutral":"neutral"}n.d(t,{B:()=>a,T:()=>s})},92639:(e,t,n)=>{"use strict";n.d(t,{HP:()=>m,Rz:()=>i,aI:()=>u,bf:()=>r,qs:()=>c});var s=n(5069),a=n(6707);async function r(e,t=5){return(0,s.A)`
    SELECT to_char(o.date,'YYYY-MM-DD') AS date, o.close::text,
           (o.close / NULLIF(n50.close, 0))::text  AS rs_n50,
           (o.close / NULLIF(n500.close, 0))::text AS rs_n500
    FROM atlas_foundation.ohlcv_etf o
    LEFT JOIN atlas_foundation.index_prices n50  ON n50.date = o.date  AND n50.index_code = 'NIFTY 50'
    LEFT JOIN atlas_foundation.index_prices n500 ON n500.date = o.date AND n500.index_code = 'NIFTY 500'
    WHERE o.ticker = ${e} AND o.close > 0
      AND o.date >= NOW() - (${t} || ' years')::INTERVAL
    ORDER BY o.date ASC
  `}let i=`
  latest AS (SELECT max(date) d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'),
  tdl AS (SELECT max(date) d FROM atlas_foundation.technical_daily WHERE asset_class='stock'),  -- asset_class filter uses the class_date index (unfiltered max(date) seq-scans 6.9M rows)
  cap AS (
    SELECT instrument_id,
      CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
           WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
           WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
    FROM atlas_foundation.de_index_constituents
    WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
    GROUP BY instrument_id),
  rs AS (SELECT instrument_id, rs_3m_n500, rs_1m_n500, ret_1d, ret_1w, ret_1m FROM atlas_foundation.technical_daily
         WHERE asset_class='stock' AND date=(SELECT d FROM tdl)),
  j AS (
    SELECT l.instrument_id, im.symbol, COALESCE(c.cap,'micro') AS cap,
           l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va,
           l.composite::float comp
    FROM atlas_foundation.atlas_lens_scores_daily l
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
    LEFT JOIN cap c ON c.instrument_id = l.instrument_id
    WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)),
  dec AS (
    SELECT instrument_id, symbol, cap, t, f, ca, fl, va, comp,
      CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_tech,
      CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fund,
      CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_cat,
      CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
      CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_val,
      CASE WHEN comp IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(comp IS NULL) ORDER BY comp) END d_composite
    FROM j),
  scored AS (
    SELECT d.instrument_id, d.symbol, d.cap, d.t, d.f, d.ca, d.fl, d.va,
      d.d_tech, d.d_fund, d.d_cat, d.d_flow, d.d_val, d.d_composite,
      -- LEADER = TOP DECILE (D10) by composite within the stock's cap cohort (FM 2026-06-30:
      -- one simple rule). lead is 0/1; a leader has lead = 1. Roll-ups filter on lead >= 1.
      (COALESCE((d.d_composite>=10)::int,0)) AS lead,
      -- strength = mean of the ACTIVE-lens deciles (Technical & Flow), matching the 2-lens conviction.
      ((COALESCE(d.d_tech,0)+COALESCE(d.d_flow,0))::float
        / NULLIF((d.d_tech IS NOT NULL)::int+(d.d_flow IS NOT NULL)::int,0)) AS strength,
      rs.rs_1m_n500, rs.rs_3m_n500, rs.ret_1d, rs.ret_1w, rs.ret_1m
    FROM dec d LEFT JOIN rs ON rs.instrument_id = d.instrument_id),
  etf_nse AS (  -- deterministic ETF identity bridge: Morningstar fund_name ⇄ NSE instrument name.
                -- 1 row per mstar_id (min ticker) so a name matching >1 NSE row can't fan out the holdings join.
    SELECT mstar_id, min(nse_ticker) AS nse_ticker FROM (
      SELECT mm.mstar_id, im.symbol AS nse_ticker
      FROM atlas_foundation.de_mf_master mm
      JOIN atlas_foundation.instrument_master im
        ON im.asset_class='etf'
       AND upper(regexp_replace(im.name,'[^A-Za-z0-9]','','g')) = upper(regexp_replace(mm.fund_name,'[^A-Za-z0-9]','','g'))
      WHERE mm.is_etf) b
    GROUP BY mstar_id)
`,l=`mm.is_etf
  AND mm.category_name NOT ILIKE ALL(ARRAY['%bond%','%gold%','%liquid%','%debt%','%silver%','%overnight%','%international%','%global%'])`;function o(e){let t=e=>null==e?null:(0,a.Ro)(e);return{fcode:e.fcode,name:e.name,category:e.category,expense:t(e.expense),nse_ticker:e.nse_ticker,n_holdings:(0,a.oT)(e.n_holdings,0),n_leaders:(0,a.oT)(e.n_leaders,0),breadth:t(e.breadth),v_tech:t(e.v_tech),v_fund:t(e.v_fund),v_cat:t(e.v_cat),v_flow:t(e.v_flow),v_val:t(e.v_val)}}let d=`
  mm.mstar_id AS fcode, mm.fund_name AS name, mm.category_name AS category, mm.expense_ratio AS expense,
  max(en.nse_ticker) AS nse_ticker,
  count(h.instrument_id) AS n_holdings,
  count(*) FILTER (WHERE COALESCE(s.lead,0) >= 1) AS n_leaders,
  sum(h.weight) FILTER (WHERE COALESCE(s.lead,0) >= 1) / NULLIF(sum(h.weight),0) AS breadth,
  sum(h.weight*s.t)  FILTER (WHERE s.t  IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.t  IS NOT NULL),0) AS v_tech,
  sum(h.weight*s.f)  FILTER (WHERE s.f  IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.f  IS NOT NULL),0) AS v_fund,
  sum(h.weight*s.ca) FILTER (WHERE s.ca IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.ca IS NOT NULL),0) AS v_cat,
  sum(h.weight*s.fl) FILTER (WHERE s.fl IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.fl IS NOT NULL),0) AS v_flow,
  sum(h.weight*s.va) FILTER (WHERE s.va IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.va IS NOT NULL),0) AS v_val`;async function c(){return(await s.A.unsafe(`
    WITH ${i}
    SELECT ${d}
    FROM atlas_foundation.de_mf_master mm
    JOIN atlas_foundation.de_etf_holdings h ON h.ticker = mm.mstar_id AND h.weight IS NOT NULL
    JOIN scored s ON s.instrument_id = h.instrument_id   -- INNER: scored, mapped holdings only (cash/unmapped excluded from the breadth base)
    LEFT JOIN etf_nse en ON en.mstar_id = mm.mstar_id
    WHERE ${l}
    GROUP BY mm.mstar_id, mm.fund_name, mm.category_name, mm.expense_ratio
    HAVING count(h.instrument_id) > 0
    ORDER BY breadth DESC NULLS LAST`)).map(o)}async function m(e){let t=await s.A.unsafe(`
    WITH ${i}
    SELECT ${d}, max(mm.isin) AS isin, max(mm.amc_name) AS amc, max(mm.primary_benchmark) AS benchmark
    FROM atlas_foundation.de_mf_master mm
    JOIN atlas_foundation.de_etf_holdings h ON h.ticker = mm.mstar_id AND h.weight IS NOT NULL
    JOIN scored s ON s.instrument_id = h.instrument_id   -- same INNER basis as the look-through table below (consistent n_holdings)
    LEFT JOIN etf_nse en ON en.mstar_id = mm.mstar_id
    WHERE mm.mstar_id = $1 AND mm.is_etf
    GROUP BY mm.mstar_id, mm.fund_name, mm.category_name, mm.expense_ratio`,[e]);if(0===t.length)return null;let n=await s.A.unsafe(`
    WITH ${i}
    SELECT h.weight, s.symbol, im.sector,
      s.d_tech, s.d_fund, s.d_cat, s.d_flow, s.d_val, COALESCE(s.lead,0) AS lead, s.strength, s.rs_3m_n500,
      s.ret_1d, s.ret_1w, s.ret_1m
    FROM atlas_foundation.de_etf_holdings h
    JOIN scored s ON s.instrument_id = h.instrument_id
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = h.instrument_id
    WHERE h.ticker = $1 AND h.weight IS NOT NULL
    ORDER BY h.weight DESC`,[e]),r=e=>null==e?null:(0,a.Ro)(e);return{...o(t[0]),isin:t[0].isin,amc:t[0].amc,benchmark:t[0].benchmark,holdings:n.map(e=>({symbol:e.symbol,weight:r(e.weight),sector:e.sector,d_tech:r(e.d_tech),d_fund:r(e.d_fund),d_cat:r(e.d_cat),d_flow:r(e.d_flow),d_val:r(e.d_val),lead:(0,a.oT)(e.lead,0),strength:r(e.strength),rs_3m:r(e.rs_3m_n500),ret_1d:r(e.ret_1d),ret_1w:r(e.ret_1w),ret_1m:r(e.ret_1m)}))}}async function u(){let e=await (0,s.A)`
    SELECT to_char(max(date),'YYYY-MM-DD') AS d
    FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'`;return e[0]?.d??null}}};