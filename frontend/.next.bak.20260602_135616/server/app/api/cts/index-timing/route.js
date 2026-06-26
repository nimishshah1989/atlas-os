(()=>{var e={};e.id=1246,e.ids=[1246],e.modules={3295:e=>{"use strict";e.exports=require("next/dist/server/app-render/after-task-async-storage.external.js")},5069:(e,t,r)=>{"use strict";r.d(t,{A:()=>n});var s=r(43971);if(!process.env.ATLAS_DB_URL)throw Error("ATLAS_DB_URL is not defined. Set it in .env.local.");let i=process.env.ATLAS_DB_URL.includes("pooler.supabase.com");if(process.env.ATLAS_DB_URL.includes(":6543/"))throw Error("ATLAS_DB_URL must use session-mode pooler (port 5432), not transaction-mode (port 6543). M13 audit trail relies on sql.begin() + SET LOCAL which requires a pinned connection.");let n=(0,s.A)(process.env.ATLAS_DB_URL,{max:14,idle_timeout:10,max_lifetime:300,connect_timeout:10,prepare:!i,ssl:!!process.env.ATLAS_DB_URL.includes("sslmode=require")&&{rejectUnauthorized:!1}})},6216:(e,t,r)=>{"use strict";r.r(t),r.d(t,{patchFetch:()=>A,routeModule:()=>c,serverHooks:()=>E,workAsyncStorage:()=>p,workUnitAsyncStorage:()=>_});var s={};r.r(s),r.d(s,{GET:()=>l,dynamic:()=>d});var i=r(96559),n=r(48088),a=r(37719),u=r(32190),o=r(5069);let d="force-dynamic";async function l(){let e=await (0,o.A)`
    WITH latest AS (
      SELECT instrument_id, stage, is_npc, cts_action_confidence
      FROM atlas.atlas_cts_signals_daily
      WHERE date = (SELECT MAX(date) FROM atlas.atlas_cts_signals_daily)
    ),
    graded AS (
      SELECT
        u.in_nifty_50,
        u.in_nifty_100,
        u.in_nifty_500,
        CASE
          WHEN l.cts_action_confidence = true                        THEN 'plus_a'
          WHEN l.stage = 2                                           THEN 'plus_b'
          WHEN l.stage = 4 OR (l.stage = 3 AND l.is_npc = true)    THEN 'minus_a'
          WHEN l.stage = 3                                           THEN 'minus_b'
          ELSE 'neutral'
        END AS grade
      FROM atlas.atlas_universe_stocks u
      LEFT JOIN latest l ON l.instrument_id = u.instrument_id
    )
    SELECT
      idx.name                                                   AS index_name,
      COUNT(*) FILTER (WHERE grade = 'plus_a')::int             AS plus_a,
      COUNT(*) FILTER (WHERE grade = 'plus_b')::int             AS plus_b,
      COUNT(*) FILTER (WHERE grade = 'neutral')::int            AS neutral,
      COUNT(*) FILTER (WHERE grade = 'minus_b')::int            AS minus_b,
      COUNT(*) FILTER (WHERE grade = 'minus_a')::int            AS minus_a,
      COUNT(*)::int                                              AS total
    FROM graded
    CROSS JOIN (VALUES
      ('Nifty 50',      'n50'),
      ('Nifty 100',     'n100'),
      ('Nifty 500',     'n500'),
      ('All Tradeable', 'all')
    ) AS idx(name, key)
    WHERE (idx.key = 'n50'  AND in_nifty_50  = true)
       OR (idx.key = 'n100' AND in_nifty_100 = true)
       OR (idx.key = 'n500' AND in_nifty_500 = true)
       OR  idx.key = 'all'
    GROUP BY idx.name, idx.key
    ORDER BY ARRAY_POSITION(ARRAY['n50','n100','n500','all'], idx.key)
  `;return u.NextResponse.json({rows:e,as_of:new Date().toISOString()})}let c=new i.AppRouteRouteModule({definition:{kind:n.RouteKind.APP_ROUTE,page:"/api/cts/index-timing/route",pathname:"/api/cts/index-timing",filename:"route",bundlePath:"app/api/cts/index-timing/route"},resolvedPagePath:"/home/ubuntu/atlas-os/frontend/src/app/api/cts/index-timing/route.ts",nextConfigOutput:"",userland:s}),{workAsyncStorage:p,workUnitAsyncStorage:_,serverHooks:E}=c;function A(){return(0,a.patchFetch)({workAsyncStorage:p,workUnitAsyncStorage:_})}},10846:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-page.runtime.prod.js")},21820:e=>{"use strict";e.exports=require("os")},27910:e=>{"use strict";e.exports=require("stream")},29021:e=>{"use strict";e.exports=require("fs")},29294:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-async-storage.external.js")},34631:e=>{"use strict";e.exports=require("tls")},44870:e=>{"use strict";e.exports=require("next/dist/compiled/next-server/app-route.runtime.prod.js")},55511:e=>{"use strict";e.exports=require("crypto")},63033:e=>{"use strict";e.exports=require("next/dist/server/app-render/work-unit-async-storage.external.js")},74998:e=>{"use strict";e.exports=require("perf_hooks")},78335:()=>{},91645:e=>{"use strict";e.exports=require("net")},96487:()=>{}};var t=require("../../../../webpack-runtime.js");t.C(e);var r=e=>t(t.s=e),s=t.X(0,[4447,3971,580],()=>r(6216));module.exports=s})();