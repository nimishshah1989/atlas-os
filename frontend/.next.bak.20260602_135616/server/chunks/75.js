"use strict";exports.id=75,exports.ids=[75],exports.modules={13877:(e,t,a)=>{a.d(t,{LV:()=>n,Md:()=>i,Qx:()=>_,jB:()=>m,nK:()=>s,od:()=>l});var r=a(5069);async function s(){return(await (0,r.A)`
    SELECT
      date::text,
      benchmark_close::text,
      benchmark_ema_50::text,
      benchmark_ema_200::text,
      benchmark_ema_50_slope::text,
      benchmark_ema_200_slope::text,
      benchmark_above_ema_50,
      benchmark_above_ema_200,
      realized_vol_5d::text,
      vol_252_median::text,
      pct_countries_above_200dma::text,
      pct_countries_above_50dma::text,
      regime_state,
      dislocation_flag
    FROM global_atlas.atlas_market_regime_daily
    ORDER BY date DESC
    LIMIT 1
  `)[0]??null}async function i(){return(0,r.A)`
    WITH latest_date AS (
      SELECT MAX(date) AS d FROM global_atlas.atlas_etf_metrics_daily
    ),
    rs_pivot AS (
      SELECT
        ticker,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_acwi,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_acwi,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '12m' THEN rs_quintile END) AS q_12m_acwi,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_vt,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_vt,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '12m' THEN rs_quintile END) AS q_12m_vt,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_eem,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_eem,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '12m' THEN rs_quintile END) AS q_12m_eem,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_gold,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_gold,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '12m' THEN rs_quintile END) AS q_12m_gold,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '3m'  THEN rs_pctile   END) AS pctile_3m_vt
      FROM global_atlas.atlas_etf_rs_states
      WHERE date = (SELECT d FROM latest_date)
      GROUP BY ticker
    )
    SELECT
      u.ticker,
      u.country,
      u.region,
      u.is_developed_market,
      m.ret_1w::text,
      m.ret_1m::text,
      m.ret_3m::text,
      m.ret_12m::text,
      m.above_30w_ma,
      m.ema_10_ratio::text,
      m.realized_vol_63::text,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      r.q_1m_acwi,
      r.q_3m_acwi,
      r.q_12m_acwi,
      r.q_1m_vt,
      r.q_3m_vt,
      r.q_12m_vt,
      r.q_1m_eem,
      r.q_3m_eem,
      r.q_12m_eem,
      r.q_1m_gold,
      r.q_3m_gold,
      r.q_12m_gold,
      m.rs_consensus_bullish,
      m.rs_consensus_bearish,
      r.pctile_3m_vt::text,
      (SELECT d FROM latest_date)::text AS data_as_of
    FROM global_atlas.atlas_universe_etfs u
    LEFT JOIN rs_pivot r ON r.ticker = u.ticker
    LEFT JOIN global_atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = (SELECT d FROM latest_date)
    LEFT JOIN global_atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = (SELECT d FROM latest_date)
    WHERE u.is_active = TRUE
    ORDER BY r.pctile_3m_vt DESC NULLS LAST
  `}async function m(e=252){if(!Number.isInteger(e)||e<1||e>3650)throw Error(`days must be between 1 and 3650, got: ${e}`);return(0,r.A)`
    SELECT
      date::text,
      regime_state,
      benchmark_close::text,
      benchmark_ema_50_slope::text,
      benchmark_ema_200_slope::text,
      benchmark_above_ema_50,
      benchmark_above_ema_200,
      pct_countries_above_50dma::text,
      pct_countries_above_200dma::text,
      realized_vol_5d::text
    FROM global_atlas.atlas_market_regime_daily
    WHERE date >= CURRENT_DATE - (${e} || ' days')::interval
    ORDER BY date ASC
  `}async function _(e){return(await (0,r.A)`
    WITH latest_date AS (
      SELECT MAX(date) AS d FROM global_atlas.atlas_etf_metrics_daily
    ),
    rs_pivot AS (
      SELECT
        ticker,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_acwi,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_acwi,
        MAX(CASE WHEN benchmark = 'acwi' AND timeframe = '12m' THEN rs_quintile END) AS q_12m_acwi,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_vt,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_vt,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '12m' THEN rs_quintile END) AS q_12m_vt,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_eem,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_eem,
        MAX(CASE WHEN benchmark = 'eem'  AND timeframe = '12m' THEN rs_quintile END) AS q_12m_eem,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '1m'  THEN rs_quintile END) AS q_1m_gold,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '3m'  THEN rs_quintile END) AS q_3m_gold,
        MAX(CASE WHEN benchmark = 'gold' AND timeframe = '12m' THEN rs_quintile END) AS q_12m_gold,
        MAX(CASE WHEN benchmark = 'vt'   AND timeframe = '3m'  THEN rs_pctile   END) AS pctile_3m_vt
      FROM global_atlas.atlas_etf_rs_states
      WHERE date = (SELECT d FROM latest_date)
      GROUP BY ticker
    )
    SELECT
      u.ticker,
      u.country,
      u.region,
      u.is_developed_market,
      m.ret_1w::text,
      m.ret_1m::text,
      m.ret_3m::text,
      m.ret_6m::text,
      m.ret_12m::text,
      m.above_30w_ma,
      m.ema_10_ratio::text,
      m.realized_vol_63::text,
      m.extension_pct::text,
      m.max_drawdown_252::text,
      m.volume_expansion::text,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.weinstein_gate_pass,
      r.q_1m_acwi,
      r.q_3m_acwi,
      r.q_12m_acwi,
      r.q_1m_vt,
      r.q_3m_vt,
      r.q_12m_vt,
      r.q_1m_eem,
      r.q_3m_eem,
      r.q_12m_eem,
      r.q_1m_gold,
      r.q_3m_gold,
      r.q_12m_gold,
      m.rs_consensus_bullish,
      m.rs_consensus_bearish,
      r.pctile_3m_vt::text,
      (SELECT d FROM latest_date)::text AS data_as_of
    FROM global_atlas.atlas_universe_etfs u
    LEFT JOIN rs_pivot r ON r.ticker = u.ticker
    LEFT JOIN global_atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = (SELECT d FROM latest_date)
    LEFT JOIN global_atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = (SELECT d FROM latest_date)
    WHERE u.ticker = ${e}
      AND u.is_active = TRUE
    LIMIT 1
  `)[0]??null}async function n(e,t=252){if(!Number.isInteger(t)||t<1||t>3650)throw Error(`days must be between 1 and 3650, got: ${t}`);return(0,r.A)`
    WITH rs_pctile AS (
      SELECT date, rs_pctile AS pctile_3m_vt
      FROM global_atlas.atlas_etf_rs_states
      WHERE ticker = ${e}
        AND benchmark = 'vt'
        AND timeframe = '3m'
    )
    SELECT
      m.date::text,
      r.pctile_3m_vt::text,
      m.ret_1m::text,
      m.ret_3m::text,
      m.ret_12m::text,
      m.ema_10_ratio::text,
      m.realized_vol_63::text,
      m.extension_pct::text,
      m.max_drawdown_252::text,
      m.volume_expansion::text,
      m.above_30w_ma
    FROM global_atlas.atlas_etf_metrics_daily m
    LEFT JOIN rs_pctile r ON r.date = m.date
    WHERE m.ticker = ${e}
      AND m.date >= CURRENT_DATE - (${t} || ' days')::interval
    ORDER BY m.date ASC
  `}async function l(e,t=252){if(!Number.isInteger(t)||t<1||t>3650)throw Error(`days must be between 1 and 3650, got: ${t}`);return(0,r.A)`
    SELECT
      date::text,
      rs_state,
      momentum_state,
      risk_state
    FROM global_atlas.atlas_etf_states_daily
    WHERE ticker = ${e}
      AND date >= CURRENT_DATE - (${t} || ' days')::interval
    ORDER BY date ASC
  `}},32455:(e,t,a)=>{a.r(t),a.d(t,{IndicatorChart:()=>q});var r=a(60687),s=a(43210),i=a(79351),m=a(11860),_=a(27747),n=a(9920),l=a(23812),o=a(46245),c=a(32620),d=a(61855),E=a(77814),N=a(2041),x=a(23801),A=a(25679),u=a(61678),b=a(66424),f=a(49513);let h="#22c55e",k="#ef4444",S="#94a3b8",p="#e2e8f0";function v(e){try{return new Date(e).toLocaleDateString("en-US",{month:"short",year:"2-digit"}).replace(" "," '")}catch{return e}}let g={backgroundColor:"#ffffff",border:`1px solid ${p}`,borderRadius:"2px",fontFamily:"var(--font-sans)",fontSize:"11px",color:"#1e293b",padding:"6px 8px"},D={fontSize:9,fill:S};function q({title:e,description:t,currentValue:a,isBullish:q,data:H,refLine:T,refLabel:C,variant:y,yFormat:w="none",invertBarColors:M=!1}){let[R,j]=(0,s.useState)(!1),L=!0===q?h:!1===q?k:S,O=function(e){switch(e){case"pct":return e=>`${(100*e).toFixed(0)}%`;case"sigma":return e=>`${e.toFixed(2)}σ`;case"ratio":return e=>e.toFixed(2);case"count":return e=>e.toFixed(0);case"large":return e=>e>=1e3?`${(e/1e3).toFixed(1)}k`:e.toFixed(0);default:return e=>String(e)}}(w),W=(0,s.useMemo)(()=>{let e=new Set;return H.filter(t=>{let a=t.date.slice(0,7);return!e.has(a)&&(e.add(a),!0)}).map(e=>e.date)},[H]);function F(t){let a=(0,r.jsx)(_.W,{dataKey:"date",ticks:W,tickFormatter:v,tick:D,tickLine:!1,axisLine:!1}),s=(0,r.jsx)(n.h,{tickFormatter:O,tick:D,tickLine:!1,axisLine:!1,width:36}),i=(0,r.jsx)(l.m,{contentStyle:g,labelFormatter:e=>(function(e){try{return new Date(e).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"})}catch{return e}})(String(e)),formatter:t=>["number"==typeof t?O(t):"—",e]}),m=void 0!==T?(0,r.jsx)(o.e_,{y:T,stroke:S,strokeDasharray:"3 3",label:C?{value:C,position:"insideTopRight",fontSize:8,fill:S}:void 0}):null,f=t?(0,r.jsx)(c.v,{dataKey:"date",height:22,stroke:p,tickFormatter:v,travellerWidth:6}):null;return"area"===y?(0,r.jsxs)(d.Q,{data:H,margin:{top:4,right:4,bottom:0,left:0},children:[a,s,i,m,(0,r.jsx)(E.Gk,{type:"monotone",dataKey:"value",stroke:L,fill:L,fillOpacity:.08,strokeWidth:1.5,dot:!1,isAnimationActive:!1,connectNulls:!0}),f]}):"bar"===y?(0,r.jsxs)(N.E,{data:H,margin:{top:4,right:4,bottom:0,left:0},children:[a,s,i,m,(0,r.jsx)(x.yP,{dataKey:"value",maxBarSize:4,isAnimationActive:!1,children:H.map((e,t)=>(0,r.jsx)(A.f,{fill:M?k:(e.value??0)>=0?h:k},`cell-${t}`))}),f]}):(0,r.jsxs)(u.b,{data:H,margin:{top:4,right:4,bottom:0,left:0},children:[a,s,i,m,(0,r.jsx)(b.N1,{type:"monotone",dataKey:"value",stroke:L,strokeWidth:1.5,dot:!1,isAnimationActive:!1,connectNulls:!0}),f]})}return(0,r.jsxs)(r.Fragment,{children:[(0,r.jsxs)("div",{className:"border border-paper-rule rounded-sm p-5 flex flex-col",children:[(0,r.jsxs)("div",{className:"flex items-start justify-between mb-2",children:[(0,r.jsx)("span",{className:"font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary pr-2",children:e}),(0,r.jsxs)("div",{className:"flex items-center gap-2 shrink-0",children:[!0===q&&(0,r.jsx)("span",{className:"font-sans text-[10px] font-medium text-signal-pos",children:"BULLISH"}),!1===q&&(0,r.jsx)("span",{className:"font-sans text-[10px] font-medium text-signal-neg",children:"BEARISH"}),(0,r.jsx)("button",{onClick:()=>j(!0),className:"text-ink-tertiary hover:text-ink-secondary transition-colors ml-1",title:"Expand chart",children:(0,r.jsx)(i.A,{className:"w-3 h-3"})})]})]}),(0,r.jsx)("p",{className:"font-sans text-xs text-ink-tertiary leading-relaxed mb-3",children:t}),(0,r.jsx)("div",{className:"font-mono text-lg font-semibold mb-4",style:{color:L},children:a}),(0,r.jsx)("div",{className:"mt-auto",children:(0,r.jsx)(f.u,{width:"100%",height:200,children:F(!1)})})]}),R&&(0,r.jsx)("div",{className:"fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6",onClick:()=>j(!1),children:(0,r.jsxs)("div",{className:"bg-paper border border-paper-rule rounded-sm p-7 w-full max-w-4xl shadow-xl",onClick:e=>e.stopPropagation(),children:[(0,r.jsxs)("div",{className:"flex items-start justify-between mb-3",children:[(0,r.jsxs)("div",{className:"flex items-center gap-3",children:[(0,r.jsx)("span",{className:"font-sans text-sm font-semibold uppercase tracking-wide text-ink-secondary",children:e}),!0===q&&(0,r.jsx)("span",{className:"font-sans text-[10px] font-medium text-signal-pos",children:"BULLISH"}),!1===q&&(0,r.jsx)("span",{className:"font-sans text-[10px] font-medium text-signal-neg",children:"BEARISH"})]}),(0,r.jsx)("button",{onClick:()=>j(!1),className:"text-ink-tertiary hover:text-ink-secondary transition-colors",children:(0,r.jsx)(m.A,{className:"w-4 h-4"})})]}),(0,r.jsx)("p",{className:"font-sans text-xs text-ink-secondary leading-relaxed mb-4",children:t}),(0,r.jsx)("div",{className:"font-mono text-2xl font-semibold mb-6",style:{color:L},children:a}),(0,r.jsx)(f.u,{width:"100%",height:400,children:F(!0)}),(0,r.jsx)("p",{className:"font-sans text-[10px] text-ink-tertiary mt-3",children:"Drag the handles below the chart to zoom into a specific period. Click outside to close."})]})})]})}}};