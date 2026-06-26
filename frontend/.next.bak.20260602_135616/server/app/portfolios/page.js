(()=>{var t={};t.id=7814,t.ids=[7814],t.modules={3295:t=>{"use strict";t.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},4536:(t,e,s)=>{let{createProxy:r}=s(39844);t.exports=r("/home/ubuntu/atlas-os/frontend/node_modules/next/dist/client/app-dir/link.js")},10846:t=>{"use strict";t.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},19121:t=>{"use strict";t.exports=require("next/dist/server/app-render/action-async-storage.external.js")},21820:t=>{"use strict";t.exports=require("os")},25042:(t,e,s)=>{"use strict";s.r(e),s.d(e,{default:()=>d,dynamic:()=>l});var r=s(37413),a=s(4536),n=s.n(a),i=s(94879),o=s(50499);let l="force-dynamic";async function d(){let t=await (0,i.JL)(),e=t.filter(t=>"static"===t.type).length,s=t.filter(t=>"rule-based"===t.type).length,a=t.filter(t=>t.paper_trading_active).length;return(0,r.jsxs)("main",{className:"min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto",children:[(0,r.jsxs)("header",{className:"mb-6 flex items-start justify-between flex-wrap gap-3",children:[(0,r.jsxs)("div",{children:[(0,r.jsx)("h1",{className:"font-serif text-2xl text-ink-primary",children:"Custom Portfolios"}),(0,r.jsxs)("p",{className:"font-sans text-xs text-ink-tertiary mt-1",children:["FM-authored portfolios \xb7 ",t.length," total"]})]}),(0,r.jsx)(n(),{href:"/portfolios/new?type=static",className:"font-sans text-sm px-4 py-2 bg-accent text-white rounded-[2px] hover:bg-accent/90 transition-colors",children:"+ New Portfolio"})]}),(0,r.jsxs)("div",{className:"grid grid-cols-3 gap-3 mb-6",children:[(0,r.jsxs)("div",{className:"bg-paper border border-paper-rule rounded-[2px] p-3",children:[(0,r.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide",children:"Static"}),(0,r.jsx)("p",{className:"font-mono text-lg font-semibold text-ink-primary mt-1",children:e})]}),(0,r.jsxs)("div",{className:"bg-paper border border-paper-rule rounded-[2px] p-3",children:[(0,r.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide",children:"Rule-Based"}),(0,r.jsx)("p",{className:"font-mono text-lg font-semibold text-ink-primary mt-1",children:s})]}),(0,r.jsxs)("div",{className:"bg-paper border border-paper-rule rounded-[2px] p-3",children:[(0,r.jsx)("p",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide",children:"Paper Active"}),(0,r.jsx)("p",{className:"font-mono text-lg font-semibold text-ink-primary mt-1",children:a})]})]}),(0,r.jsx)(o.PortfoliosView,{portfolios:t})]})}},27073:(t,e,s)=>{Promise.resolve().then(s.t.bind(s,85814,23)),Promise.resolve().then(s.bind(s,56001))},27910:t=>{"use strict";t.exports=require("stream")},29021:t=>{"use strict";t.exports=require("fs")},29294:t=>{"use strict";t.exports=require("next/dist/server/app-render/work-async-storage.external.js")},33873:t=>{"use strict";t.exports=require("path")},34631:t=>{"use strict";t.exports=require("tls")},50499:(t,e,s)=>{"use strict";s.d(e,{PortfoliosView:()=>r});let r=(0,s(12907).registerClientReference)(function(){throw Error("Attempted to call PortfoliosView() from the server but PortfoliosView is on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.")},"/home/ubuntu/atlas-os/frontend/src/app/portfolios/PortfoliosView.tsx","PortfoliosView")},55511:t=>{"use strict";t.exports=require("crypto")},56001:(t,e,s)=>{"use strict";s.d(e,{PortfoliosView:()=>i});var r=s(60687),a=s(85814),n=s.n(a);function i({portfolios:t}){return 0===t.length?(0,r.jsxs)("div",{className:"text-center py-16",children:[(0,r.jsx)("p",{className:"font-sans text-sm text-ink-tertiary mb-4",children:"No portfolios yet."}),(0,r.jsx)(n(),{href:"/portfolios/new?type=static",className:"font-sans text-sm px-4 py-2 bg-accent text-white rounded-[2px] hover:bg-accent/90 transition-colors",children:"+ New Portfolio"})]}):(0,r.jsx)("div",{className:"overflow-x-auto",children:(0,r.jsxs)("table",{className:"w-full text-left border-collapse",children:[(0,r.jsx)("thead",{children:(0,r.jsx)("tr",{className:"border-b border-paper-rule",children:["Name","Type","Composition","Latest Sharpe","Paper Active","Created"].map(t=>(0,r.jsx)("th",{className:"font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium",children:t},t))})}),(0,r.jsx)("tbody",{children:t.map(t=>{var e;return(0,r.jsxs)("tr",{className:"border-b border-paper-rule/50 hover:bg-accent/5 transition-colors",children:[(0,r.jsx)("td",{className:"py-2.5 pr-4",children:(0,r.jsx)(n(),{href:`/portfolios/${t.id}`,className:"font-sans text-sm text-ink-primary hover:text-accent transition-colors",children:t.name})}),(0,r.jsx)("td",{className:"py-2.5 pr-4",children:(0,r.jsx)(o,{type:t.type})}),(0,r.jsx)("td",{className:"py-2.5 pr-4 font-sans text-xs text-ink-tertiary",children:"static"===t.type?null!=t.instrument_count?`${t.instrument_count} instrument${1!==t.instrument_count?"s":""}`:"—":"Rule-Based"}),(0,r.jsx)("td",{className:"py-2.5 pr-4 font-mono text-sm text-right",children:function(t){if(null==t)return"—";let e=parseFloat(t);return isNaN(e)?"—":e.toFixed(2)}(t.latest_sharpe)}),(0,r.jsx)("td",{className:"py-2.5 pr-4",children:t.paper_trading_active?(0,r.jsxs)("span",{className:"inline-flex items-center gap-1.5 font-sans text-xs text-signal-pos",children:[(0,r.jsx)("span",{className:"inline-block w-2 h-2 rounded-full bg-signal-pos"}),"Active"]}):(0,r.jsx)("span",{className:"font-sans text-xs text-ink-tertiary",children:"—"})}),(0,r.jsx)("td",{className:"py-2.5 font-sans text-xs text-ink-tertiary",children:((e=t.created_at)instanceof Date?e:new Date(String(e))).toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"})})]},t.id)})})]})})}function o({type:t}){return(0,r.jsx)("span",{className:`font-sans text-xs px-2 py-0.5 rounded-[2px] border capitalize ${"static"===t?"text-accent bg-accent/10 border-accent/20":"text-signal-warn bg-signal-warn/10 border-signal-warn/20"}`,children:"static"===t?"Static":"Rule-Based"})}},63033:t=>{"use strict";t.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},74998:t=>{"use strict";t.exports=require("perf_hooks")},90625:(t,e,s)=>{Promise.resolve().then(s.t.bind(s,4536,23)),Promise.resolve().then(s.bind(s,50499))},91645:t=>{"use strict";t.exports=require("net")},92915:(t,e,s)=>{"use strict";s.r(e),s.d(e,{GlobalError:()=>i.a,__next_app__:()=>p,pages:()=>c,routeModule:()=>_,tree:()=>d});var r=s(65239),a=s(48088),n=s(88170),i=s.n(n),o=s(30893),l={};for(let t in o)0>["default","tree","pages","GlobalError","__next_app__","routeModule"].indexOf(t)&&(l[t]=()=>o[t]);s.d(e,l);let d={children:["",{children:["portfolios",{children:["__PAGE__",{},{page:[()=>Promise.resolve().then(s.bind(s,25042)),"/home/ubuntu/atlas-os/frontend/src/app/portfolios/page.tsx"]}]},{}]},{layout:[()=>Promise.resolve().then(s.bind(s,21339)),"/home/ubuntu/atlas-os/frontend/src/app/layout.tsx"],error:[()=>Promise.resolve().then(s.bind(s,54431)),"/home/ubuntu/atlas-os/frontend/src/app/error.tsx"],loading:[()=>Promise.resolve().then(s.bind(s,67393)),"/home/ubuntu/atlas-os/frontend/src/app/loading.tsx"],"not-found":[()=>Promise.resolve().then(s.t.bind(s,57398,23)),"next/dist/client/components/not-found-error"],forbidden:[()=>Promise.resolve().then(s.t.bind(s,89999,23)),"next/dist/client/components/forbidden-error"],unauthorized:[()=>Promise.resolve().then(s.t.bind(s,65284,23)),"next/dist/client/components/unauthorized-error"]}]}.children,c=["/home/ubuntu/atlas-os/frontend/src/app/portfolios/page.tsx"],p={require:s,loadChunk:()=>Promise.resolve()},_=new r.AppPageRouteModule({definition:{kind:a.RouteKind.APP_PAGE,page:"/portfolios/page",pathname:"/portfolios",bundlePath:"",filename:"",appPaths:[]},userland:{loaderTree:d}})},94879:(t,e,s)=>{"use strict";s.d(e,{JL:()=>a,Q5:()=>o,sr:()=>i,tn:()=>n});var r=s(5069);async function a(){return(await (0,r.A)`
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
  `).filter(t=>!function(t){let e=t.trim().toLowerCase();return e.includes("(auto-created)")||e.startsWith("validate_")}(t.name))}async function n(t){return(await (0,r.A)`
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
    WHERE p.id = ${t}
  `)[0]??null}async function i(t){return(await (0,r.A)`
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
    WHERE sc.id = ${t}
      AND sc.is_fm_authored = TRUE
  `)[0]??null}async function o(t,e,s=50){return"static"===e?(0,r.A)`
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
      WHERE custom_portfolio_id = ${t}
      ORDER BY created_at DESC
      LIMIT ${s}
    `:(0,r.A)`
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
    WHERE strategy_id = ${t}
    ORDER BY created_at DESC
    LIMIT ${s}
  `}}};var e=require("../../webpack-runtime.js");e.C(t);var s=t=>e(e.s=t),r=e.X(0,[4447,3971,9626,4613],()=>s(92915));module.exports=r})();