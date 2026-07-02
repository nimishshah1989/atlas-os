"use strict";exports.id=463,exports.ids=[463],exports.modules={11917:(e,t,l)=>{l.d(t,{C:()=>n});var a=l(37413);function n({slices:e,topN:t=12}){if(0===e.length)return null;let l=e.reduce((e,t)=>e+t.weight,0),n=e.slice(0,t),s=e.slice(t),r=s.reduce((e,t)=>e+t.weight,0),i=r>0?[...n,{sector:`Other (${s.length})`,weight:r,count:s.reduce((e,t)=>e+t.count,0)}]:n;return(0,a.jsxs)("div",{children:[(0,a.jsx)("div",{className:"space-y-1.5",children:i.map(e=>(0,a.jsxs)("div",{className:"flex items-center gap-3",children:[(0,a.jsx)("span",{className:"w-[170px] shrink-0 truncate font-sans text-[12px] text-txt-2",title:e.sector,children:e.sector}),(0,a.jsx)("span",{className:"relative h-[14px] flex-1 overflow-hidden rounded-tile bg-surface-inset",children:(0,a.jsx)("span",{className:"block h-full rounded-tile bg-brand/70",style:{width:`${Math.min(100,e.weight)}%`}})}),(0,a.jsxs)("span",{className:"w-[48px] shrink-0 text-right font-num text-[12px] tabular-nums text-txt-1",children:[e.weight.toFixed(1),"%"]}),(0,a.jsx)("span",{className:"w-[30px] shrink-0 text-right font-num text-[10px] tabular-nums text-txt-3",title:"holdings in this sector",children:e.count})]},e.sector))}),(0,a.jsxs)("div",{className:"mt-2 font-sans text-[11px] text-txt-3",children:[e.length," sectors \xb7 ",l.toFixed(0),"% of the portfolio mapped to a sector (rest = cash / unclassified)."]})]})}},22382:(e,t,l)=>{function a(e){let t=new Map;for(let l of e){let e=l.sector??"Unclassified",a=t.get(e)??{weight:0,count:0};a.weight+=l.weight??0,a.count+=1,t.set(e,a)}return[...t.entries()].map(([e,t])=>({sector:e,weight:t.weight,count:t.count})).sort((e,t)=>t.weight-e.weight)}function n(e){if(0===e.length)return{dates:[],rows:[]};let t=[...new Set(e.map(e=>e.d))].sort(),l=new Map(t.map((e,t)=>[e,t])),a=new Map;for(let n of e)a.has(n.sector)||a.set(n.sector,t.map(()=>null)),a.get(n.sector)[l.get(n.d)]=n.w;let n=t.length-1;return{dates:t,rows:[...a.entries()].map(([e,t])=>({sector:e,weights:t})).sort((e,t)=>(t.weights[n]??-1)-(e.weights[n]??-1))}}l.d(t,{H:()=>n,Hf:()=>i,js:()=>a});let s=e=>e.reduce((e,t)=>e+t,0)/e.length,r=e=>{let t=s(e);return Math.sqrt(e.reduce((e,l)=>e+(l-t)**2,0)/e.length)};function i(e,t=.065){let l=e.map(e=>e.nav).filter(e=>null!=e&&e>0),a=l.length,n={months:Math.max(0,a-1),ret1y:null,cagr3y:null,cagr5y:null,cagrIncept:null,volAnn:null,sharpe:null,sortino:null,maxDrawdown:null,navFrom:e[0]?.d??null,navTo:e[a-1]?.d??null};if(a<2)return n;let o=[];for(let e=1;e<a;e++)o.push(l[e]/l[e-1]-1);let d=r(o)*Math.sqrt(12),c=Math.sqrt(s(o.map(e=>Math.min(e,0)**2)))*Math.sqrt(12),m=e=>a-1>=e?Math.pow(l[a-1]/l[a-1-e],12/e)-1:null,u=a-1,_=Math.pow(l[a-1]/l[0],12/u)-1,h=l[0],f=0;for(let e of l){e>h&&(h=e);let t=e/h-1;t<f&&(f=t)}return{months:u,ret1y:m(12),cagr3y:m(36),cagr5y:m(60),cagrIncept:_,volAnn:d,sharpe:d>0?(_-t)/d:null,sortino:c>0?(_-t)/c:null,maxDrawdown:f,navFrom:e[0].d,navTo:e[a-1].d}}},24062:(e,t,l)=>{l.d(t,{j:()=>o});var a=l(75192),n=l(39802);let s={v_tech:"technical",v_fund:"fundamental",v_cat:"catalyst",v_flow:"flow"},r=[{vkey:"v_tech",dkey:"d_tech",label:"Technical",term:"rs"},{vkey:"v_fund",dkey:"d_fund",label:"Fundamental",term:"roe"},{vkey:"v_cat",dkey:"d_cat",label:"Catalyst",term:"conviction"},{vkey:"v_flow",dkey:"d_flow",label:"Flow",term:"smart_money"},{vkey:"v_val",dkey:"d_val",label:"Valuation",term:"pe"}],i=e=>null==e?null:e<=1?100*e:e;function o(e,t,l,d={},c,m={}){let u=l.length,_=null==t.breadth?null:100*t.breadth,h=r.map(e=>({...e,v:t[e.vkey]??null})).filter(e=>null!=e.v).map(e=>{let t=s[e.vkey],r=(0,a.X)(e.vkey,l.filter(t=>null!=t[e.dkey]).map(l=>({id:`${e.vkey}-${l.symbol}`,symbol:l.symbol,decile:l[e.dkey],weight:i(l.weight),value:t?d[l.symbol]?.[t]??null:null,href:`/stocks/${l.symbol}`,children:m[l.symbol]?(0,n.w)(m[l.symbol],c):void 0}))),o=l.filter(t=>null!=t[e.dkey]).length;return{id:e.vkey,label:e.label,score:e.v,term:e.term,formula:`${e.label} ${e.v.toFixed(0)} — ${o} of ${u} holdings across decile bands (weight-share bars) \xb7 holdings-weighted`,children:r.length?r:void 0}});return{title:e,headline:{label:"Leadership breadth",value:null==_?"—":`${_.toFixed(0)}%`,decile:null==_?null:Math.max(1,Math.min(10,Math.round(_/10)))},formula:null!=t.n_leaders&&null!=t.n_holdings?`= ${t.n_leaders} of ${t.n_holdings} holdings lead ≥2 lenses (weighted) \xb7 lenses below are holdings-weighted`:"= weighted share of holdings leading ≥2 conviction lenses \xb7 lenses below are holdings-weighted",lenses:h}}},31602:(e,t,l)=>{l.d(t,{q:()=>o});var a=l(5069);let n=e=>{if(null==e)return null;let t="number"==typeof e?e:Number(e);return Number.isFinite(t)?t:null},s=e=>e&&"object"==typeof e?e:{},r=(e,t=0)=>`${e>=0?"+":"−"}${Math.abs(e).toFixed(t)}`;function i(e){let t=String(e.subject??"").toLowerCase();return!!/disclosure under sebi|general update|^updates|analyst|investor meet|con\.? call|allotment of securities|change in management|trading window/.test(t)||"governance"===e.bucket}async function o(e){let t=Array.from(new Set(e.filter(Boolean)));if(0===t.length)return{};let l=await (0,a.A)`
    SELECT im.symbol, l.evidence
    FROM atlas_foundation.atlas_lens_scores_daily l
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
    WHERE l.asset_class = 'stock'
      AND l.date = (SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock')
      AND im.symbol = ANY(${t})
  `,o={};for(let e of l)o[e.symbol]=function(e){let t=e;if("string"==typeof t)try{t=JSON.parse(t)}catch{t=null}let l=s(s(t).lenses);return{technical:function(e){let t=n(s(e.relative_strength).rs_n500);return null==t?null:`RS ${r(100*t)}%`}(s(l.technical)),fundamental:function(e){let t=n(s(e.profitability).roe);return null==t?null:`ROE ${t.toFixed(0)}%`}(s(l.fundamental)),catalyst:function(e){let t=Array.isArray(e.filings)?e.filings:[];if(!t.length)return null;let l=[...t].sort((e,t)=>{let l=+!!i(e),a=+!!i(t);return l!==a?l-a:Math.abs(n(t.weighted)??0)-Math.abs(n(e.weighted)??0)})[0],a=n(l.weighted)??0;if(0===a)return null;let s="order_win"===l.category?" (order win)":"";return`${String(l.subject??"Filing")}${s} ${r(a)}`}(s(l.catalyst)),flow:function(e){let t=s(e.smart_money),l=(Array.isArray(t.signals)?t.signals:[]).find(e=>e.startsWith("mf_mom_delta"));if(l)return`MF MoM ${l.split("=")[1]??""}`;let a=n(s(e.promoter).promoter_pct);if(null!=a)return`Promoter ${a.toFixed(0)}%`;let r=s(e.accumulation),i=n(r.delivery_30d??r.delivery_avg_30d??r.delivery);return null!=i?`Delivery ${i.toFixed(0)}%`:null}(s(l.flow))}}(e.evidence);return o}},32936:(e,t,l)=>{l.d(t,{h:()=>i});var a=l(37413),n=l(4536),s=l.n(n);let r={pos:"var(--color-sig-pos)",neg:"var(--color-sig-neg)",warn:"var(--color-sig-warn)",neutral:"var(--color-txt-1)",brand:"var(--color-brand)"};function i({label:e,value:t,unit:l,sub:n,delta:i,tone:o="neutral",href:d,children:c}){let m=(0,a.jsxs)(a.Fragment,{children:[(0,a.jsxs)("div",{className:"flex items-center justify-between gap-2",children:[(0,a.jsx)("span",{className:"font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:e}),d&&(0,a.jsx)("span",{className:"font-num text-[12px] text-txt-3 transition-colors group-hover/stat:text-brand",children:"→"})]}),(0,a.jsxs)("div",{className:"mt-2 flex items-baseline gap-1",children:[(0,a.jsx)("span",{className:"font-display text-[30px] font-semibold leading-none tracking-tight tabular-nums",style:{color:r[o]},children:t}),l&&(0,a.jsx)("span",{className:"font-num text-[13px] text-txt-2",children:l})]}),c&&(0,a.jsx)("div",{className:"mt-2.5",children:c}),(n||i)&&(0,a.jsxs)("div",{className:"mt-2 flex items-center gap-2",children:[n&&(0,a.jsx)("span",{className:"font-sans text-[11px] text-txt-2",children:n}),i&&(0,a.jsx)("span",{className:"font-num text-[11px] tabular-nums",style:{color:r[i.tone]},children:i.value})]})]}),u="group/stat block rounded-tile border border-edge-hair bg-surface-raised px-4 py-3.5 shadow-tile transition-colors";return d?(0,a.jsx)(s(),{href:d,className:`${u} hover:border-edge-strong hover:bg-surface-raised`,children:m}):(0,a.jsx)("div",{className:u,children:m})}},34565:(e,t,l)=>{l.d(t,{A:()=>s});var a=l(5069);let n=["composite","technical","fundamental","catalyst","flow","valuation","policy","tech_trend","tech_rs","tech_vol_contraction","tech_volume","fund_profitability","fund_margin","fund_growth","fund_balance_sheet","fund_op_leverage","cat_earnings_strategy","cat_capital_action","cat_governance","flow_promoter","flow_institutional","flow_smart_money","flow_accumulation","val_pe_vs_sector","val_absolute_pe","val_pb","val_ev_ebitda","val_52w_position"];async function s(e){let t=Array.from(new Set(e.filter(Boolean)));if(0===t.length)return{};let l=await a.A.unsafe(`SELECT im.symbol, ${n.map(e=>`l.${e}::float AS ${e}`).join(", ")}
     FROM atlas_foundation.atlas_lens_scores_daily l
     JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
     WHERE l.asset_class='stock'
       AND l.date = (SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock')
       AND im.symbol = ANY($1)`,[t]),s={};for(let e of l){let t=String(e.symbol),l={symbol:t};for(let t of n){let a=e[t];l[t]=null==a?null:Number(a)}s[t]=l}return s}},39802:(e,t,l)=>{l.d(t,{w:()=>r});var a=l(8072);let n=[{key:"technical",label:"Technical",additive:!0,subs:[{label:"Trend",col:"tech_trend",term:"ema_stack"},{label:"Rel. strength",col:"tech_rs",term:"rs"},{label:"Vol contraction",col:"tech_vol_contraction",term:"vol_contraction"},{label:"Volume",col:"tech_volume",term:"volume_ratio"}]},{key:"flow",label:"Flow",additive:!1,subs:[{label:"Promoter",col:"flow_promoter",term:"promoter"},{label:"Institutional",col:"flow_institutional"},{label:"Smart money",col:"flow_smart_money",term:"smart_money"}]},{key:"fundamental",label:"Fundamental",additive:!0,subs:[{label:"Profitability",col:"fund_profitability",term:"roe"},{label:"Margin",col:"fund_margin",term:"op_margin"},{label:"Growth",col:"fund_growth"},{label:"Balance sheet",col:"fund_balance_sheet",term:"debt_equity"},{label:"Operating leverage",col:"fund_op_leverage"}]},{key:"catalyst",label:"Catalyst",additive:!1,subs:[{label:"Earnings & momentum",col:"cat_earnings_strategy"},{label:"Capital actions",col:"cat_capital_action"},{label:"Governance",col:"cat_governance"}]},{key:"valuation",label:"Valuation",additive:!1,subs:[{label:"PE vs sector",col:"val_pe_vs_sector",term:"pe"},{label:"Absolute PE",col:"val_absolute_pe"},{label:"P/B",col:"val_pb",term:"pb"},{label:"EV / EBITDA",col:"val_ev_ebitda",term:"ev_ebitda"},{label:"52-week position",col:"val_52w_position",term:"pos_52w"}]}],s=e=>"number"==typeof e?e:null;function r(e,t=a.kZ){return n.map(l=>{let a=s(e[l.key]);if(null==a)return null;let n="valuation"===l.key?0:t[l.key]??0,r=l.subs.map(t=>({s:t,v:s(e[t.col])})).filter(e=>null!=e.v).map(({s:t,v:a})=>({id:`${e.symbol}-${l.key}-${t.col}`,label:t.label,score:a,term:t.term}));return{id:`${e.symbol}-${l.key}`,label:n>0?l.label:`${l.label} \xb7 context`,score:a,formula:l.additive?`${l.label} ${a.toFixed(0)} = sum of the sub-component points below`:`${l.label} ${a.toFixed(0)} = weighted average of the 0–100 sub-scores below`,children:r.length?r:void 0}}).filter(e=>null!=e).sort((e,t)=>Number(0>t.label.indexOf("context"))-Number(0>e.label.indexOf("context")))}},60021:(e,t,l)=>{l.d(t,{Z:()=>s});var a=l(37413);function n({title:e,children:t}){return(0,a.jsxs)("span",{className:"group/info relative inline-flex",children:[(0,a.jsx)("button",{type:"button","aria-label":e?`About ${e}`:"More info",className:"grid h-[17px] w-[17px] place-items-center rounded-full border border-brand/50 bg-brand/5 font-num text-[10px] font-semibold italic leading-none text-brand transition-colors hover:border-brand hover:bg-brand/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",children:"i"}),(0,a.jsxs)("span",{role:"tooltip",className:"pointer-events-none absolute left-1/2 top-[150%] z-50 w-[280px] -translate-x-1/2 rounded-tile border border-edge-rule bg-surface-raised p-3 text-[11.5px] leading-[1.55] text-txt-2 opacity-0 shadow-panel transition-opacity duration-150 group-hover/info:opacity-100 group-focus-within/info:opacity-100",children:[e&&(0,a.jsx)("span",{className:"mb-1 block font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:e}),t]})]})}function s({title:e,eyebrow:t,info:l,action:s,children:r,className:i="",bodyClassName:o=""}){let d=e||t||l||s;return(0,a.jsxs)("section",{className:`rounded-panel border border-edge-hair bg-surface-panel shadow-panel ${i}`,children:[d&&(0,a.jsxs)("header",{className:"flex items-center gap-2.5 border-b border-edge-hair px-5 py-3.5",children:[(0,a.jsxs)("div",{className:"min-w-0",children:[t&&(0,a.jsx)("div",{className:"font-num text-[9px] uppercase tracking-[0.14em] text-txt-3",children:t}),e&&(0,a.jsx)("h2",{className:"font-display text-[15px] font-medium leading-tight text-txt-1",children:e})]}),l&&(0,a.jsx)(n,{title:l.title,children:l.body}),s&&(0,a.jsx)("div",{className:"ml-auto shrink-0",children:s})]}),(0,a.jsx)("div",{className:o||"px-5 py-4",children:r})]})}},75192:(e,t,l)=>{l.d(t,{X:()=>s});var a=l(17768);let n=[{lo:10,hi:10,label:"D10",rep:10},{lo:8,hi:9,label:"D8–9",rep:9},{lo:5,hi:7,label:"D5–7",rep:6},{lo:1,hi:4,label:"D1–4",rep:2}];function s(e,t){let l=t.some(e=>null!=e.weight),s=t.reduce((e,t)=>e+(t.weight??0),0),r=t.length;return n.flatMap(n=>{let i=t.filter(e=>e.decile>=n.lo&&e.decile<=n.hi).sort((e,t)=>t.decile-e.decile||(t.weight??0)-(e.weight??0));if(!i.length)return[];let o=i.length,d=l&&s>0?i.reduce((e,t)=>e+(t.weight??0),0)/s*100:o/r*100,c=i.slice(0,20).map(e=>({id:e.id,label:e.symbol,decile:e.decile,weightPct:l?e.weight:null,value:e.value??null,metrics:e.metrics,href:e.href,children:e.children}));return i.length>20&&c.push({id:`${e}-${n.label}-more`,label:`+${i.length-20} more`}),[{id:`${e}-${n.label}`,label:n.label,accent:(0,a.c)(n.rep),value:`${o} ${1===o?"name":"names"}`,weightPct:l?d:null,bar:d,children:c}]})}},92639:(e,t,l)=>{l.d(t,{HP:()=>m,Rz:()=>r,aI:()=>u,bf:()=>s,qs:()=>c});var a=l(5069),n=l(6707);async function s(e,t=5){return(0,a.A)`
    SELECT to_char(o.date,'YYYY-MM-DD') AS date, o.close::text,
           (o.close / NULLIF(n50.close, 0))::text  AS rs_n50,
           (o.close / NULLIF(n500.close, 0))::text AS rs_n500
    FROM atlas_foundation.ohlcv_etf o
    LEFT JOIN atlas_foundation.index_prices n50  ON n50.date = o.date  AND n50.index_code = 'NIFTY 50'
    LEFT JOIN atlas_foundation.index_prices n500 ON n500.date = o.date AND n500.index_code = 'NIFTY 500'
    WHERE o.ticker = ${e} AND o.close > 0
      AND o.date >= NOW() - (${t} || ' years')::INTERVAL
    ORDER BY o.date ASC
  `}let r=`
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
`,i=`mm.is_etf
  AND mm.category_name NOT ILIKE ALL(ARRAY['%bond%','%gold%','%liquid%','%debt%','%silver%','%overnight%','%international%','%global%'])`;function o(e){let t=e=>null==e?null:(0,n.Ro)(e);return{fcode:e.fcode,name:e.name,category:e.category,expense:t(e.expense),nse_ticker:e.nse_ticker,n_holdings:(0,n.oT)(e.n_holdings,0),n_leaders:(0,n.oT)(e.n_leaders,0),breadth:t(e.breadth),v_tech:t(e.v_tech),v_fund:t(e.v_fund),v_cat:t(e.v_cat),v_flow:t(e.v_flow),v_val:t(e.v_val)}}let d=`
  mm.mstar_id AS fcode, mm.fund_name AS name, mm.category_name AS category, mm.expense_ratio AS expense,
  max(en.nse_ticker) AS nse_ticker,
  count(h.instrument_id) AS n_holdings,
  count(*) FILTER (WHERE COALESCE(s.lead,0) >= 1) AS n_leaders,
  sum(h.weight) FILTER (WHERE COALESCE(s.lead,0) >= 1) / NULLIF(sum(h.weight),0) AS breadth,
  sum(h.weight*s.t)  FILTER (WHERE s.t  IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.t  IS NOT NULL),0) AS v_tech,
  sum(h.weight*s.f)  FILTER (WHERE s.f  IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.f  IS NOT NULL),0) AS v_fund,
  sum(h.weight*s.ca) FILTER (WHERE s.ca IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.ca IS NOT NULL),0) AS v_cat,
  sum(h.weight*s.fl) FILTER (WHERE s.fl IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.fl IS NOT NULL),0) AS v_flow,
  sum(h.weight*s.va) FILTER (WHERE s.va IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.va IS NOT NULL),0) AS v_val`;async function c(){return(await a.A.unsafe(`
    WITH ${r}
    SELECT ${d}
    FROM atlas_foundation.de_mf_master mm
    JOIN atlas_foundation.de_etf_holdings h ON h.ticker = mm.mstar_id AND h.weight IS NOT NULL
    JOIN scored s ON s.instrument_id = h.instrument_id   -- INNER: scored, mapped holdings only (cash/unmapped excluded from the breadth base)
    LEFT JOIN etf_nse en ON en.mstar_id = mm.mstar_id
    WHERE ${i}
    GROUP BY mm.mstar_id, mm.fund_name, mm.category_name, mm.expense_ratio
    HAVING count(h.instrument_id) > 0
    ORDER BY breadth DESC NULLS LAST`)).map(o)}async function m(e){let t=await a.A.unsafe(`
    WITH ${r}
    SELECT ${d}, max(mm.isin) AS isin, max(mm.amc_name) AS amc, max(mm.primary_benchmark) AS benchmark
    FROM atlas_foundation.de_mf_master mm
    JOIN atlas_foundation.de_etf_holdings h ON h.ticker = mm.mstar_id AND h.weight IS NOT NULL
    JOIN scored s ON s.instrument_id = h.instrument_id   -- same INNER basis as the look-through table below (consistent n_holdings)
    LEFT JOIN etf_nse en ON en.mstar_id = mm.mstar_id
    WHERE mm.mstar_id = $1 AND mm.is_etf
    GROUP BY mm.mstar_id, mm.fund_name, mm.category_name, mm.expense_ratio`,[e]);if(0===t.length)return null;let l=await a.A.unsafe(`
    WITH ${r}
    SELECT h.weight, s.symbol, im.sector,
      s.d_tech, s.d_fund, s.d_cat, s.d_flow, s.d_val, COALESCE(s.lead,0) AS lead, s.strength, s.rs_3m_n500,
      s.ret_1d, s.ret_1w, s.ret_1m
    FROM atlas_foundation.de_etf_holdings h
    JOIN scored s ON s.instrument_id = h.instrument_id
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = h.instrument_id
    WHERE h.ticker = $1 AND h.weight IS NOT NULL
    ORDER BY h.weight DESC`,[e]),s=e=>null==e?null:(0,n.Ro)(e);return{...o(t[0]),isin:t[0].isin,amc:t[0].amc,benchmark:t[0].benchmark,holdings:l.map(e=>({symbol:e.symbol,weight:s(e.weight),sector:e.sector,d_tech:s(e.d_tech),d_fund:s(e.d_fund),d_cat:s(e.d_cat),d_flow:s(e.d_flow),d_val:s(e.d_val),lead:(0,n.oT)(e.lead,0),strength:s(e.strength),rs_3m:s(e.rs_3m_n500),ret_1d:s(e.ret_1d),ret_1w:s(e.ret_1w),ret_1m:s(e.ret_1m)}))}}async function u(){let e=await (0,a.A)`
    SELECT to_char(max(date),'YYYY-MM-DD') AS d
    FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'`;return e[0]?.d??null}}};