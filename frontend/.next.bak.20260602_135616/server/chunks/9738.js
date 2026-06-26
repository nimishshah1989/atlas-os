"use strict";exports.id=9738,exports.ids=[9738],exports.modules={6707:(e,t,a)=>{a.d(t,{Ro:()=>r,oT:()=>s});let _=new Set(["—","-","N/A","n/a","NaN","nan","null","undefined"]);function r(e){if(null==e)return null;let t="string"==typeof e?e.trim():e;if(""===t||"string"==typeof t&&_.has(t))return null;let a=Number(t);if(!Number.isFinite(a))throw TypeError(`toNumber: "${e}" is not a valid number`);return a}function s(e,t){let a=r(e);return null===a?t:a}new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",minimumFractionDigits:2,maximumFractionDigits:2})},48856:(e,t,a)=>{a.d(t,{EL:()=>r,RJ:()=>i,WI:()=>n,jm:()=>s,k5:()=>o});var _=a(5069);async function r(){return(0,_.A)`
    WITH latest AS (
      SELECT ticker, MAX(date) AS d
      FROM atlas.atlas_etf_metrics_daily
      GROUP BY ticker
    ),
    latest_signal AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_signal_unified
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.linked_index,
      u.inception_date::text        AS inception_date,
      u.asset_class,
      u.fund_house,
      l.d::text                     AS data_as_of,
      m.ret_1w::text                AS ret_1w,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      m.ret_6m::text                AS ret_6m,
      m.ret_12m::text               AS ret_12m,
      m.rs_pctile_3m::text          AS rs_pctile_3m,
      m.rs_3m_benchmark::text       AS rs_3m_benchmark,
      m.ema_10_ratio::text          AS ema_10_ratio,
      m.extension_pct::text         AS extension_pct,
      m.realized_vol_63::text       AS vol_63,
      m.drawdown_ratio_252::text    AS drawdown,
      m.volume_expansion::text      AS volume_expansion,
      m.avg_volume_20::text         AS avg_volume_20,
      m.effort_ratio_63::text       AS effort_ratio_63,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      NULL::int                     AS days_in_state,
      -- rs_state derived from mean_rs_rank_12m (mirrors atlas_stock_signal_unified tier logic)
      CASE
        WHEN eu.mean_rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN eu.mean_rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN eu.mean_rs_rank_12m >= 0.30 THEN 'Average'
        WHEN eu.mean_rs_rank_12m >= 0.10 THEN 'Weak'
        WHEN eu.mean_rs_rank_12m IS NOT NULL THEN 'Laggard'
        ELSE NULL
      END                           AS rs_state,
      -- momentum_state derived from pct_stage_2 / pct_stage_4
      CASE
        WHEN eu.pct_stage_2 >= 0.50  THEN 'Accelerating'
        WHEN eu.pct_stage_4 >= 0.50  THEN 'Collapsing'
        WHEN eu.pct_stage_3 >= 0.30  THEN 'Deteriorating'
        WHEN eu.pct_stage_2 IS NOT NULL THEN 'Flat'
        ELSE NULL
      END                           AS momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low' WHEN 2 THEN 'Normal' WHEN 3 THEN 'Elevated' WHEN 4 THEN 'High'
      END                           AS risk_state,
      -- weinstein_gate_pass: pct_stage_2 dominant
      (eu.pct_stage_2 IS NOT NULL AND eu.pct_stage_2 >= 0.50) AS weinstein_gate_pass,
      -- Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
      TRUE                          AS history_gate_pass,
      TRUE                          AS liquidity_gate_pass,
      -- is_investable: ETF stage_4 < 50% of holdings
      (eu.pct_stage_4 IS NULL OR eu.pct_stage_4 < 0.50) AS is_investable,
      TRUE                          AS strength_gate,
      TRUE                          AS direction_gate,
      TRUE                          AS risk_gate,
      TRUE                          AS sector_gate,
      TRUE                          AS market_gate,
      NULL::text                    AS position_size_pct,
      NULL::boolean                 AS breakout_trigger,
      NULL::boolean                 AS transition_trigger,
      NULL::boolean                 AS exit_market_riskoff,
      NULL::boolean                 AS exit_sector_avoid,
      NULL::boolean                 AS exit_rs_deteriorate,
      NULL::boolean                 AS exit_momentum_collapse,
      NULL::boolean                 AS exit_stop_loss,
      -- Stage badge: engine_state from atlas_etf_signal_unified
      eu.engine_state,
      -- Phase 8: bubble chart axes
      eu.mean_rs_rank_12m::float8   AS mean_rs_rank_12m,
      eu.mean_within_state_rank::float8 AS mean_within_state_rank,
      eu.pct_stage_2::float8        AS pct_stage_2,
      eu.pct_stage_4::float8        AS pct_stage_4,
      -- C5: provenance. Migration-087 atlas_etf_signal_unified is a pure pass-through
      -- from atlas_etf_states_daily (legacy ticker-level RS/momentum writer).
      -- n_holdings IS NULL in this view (no bottom-up holdings aggregator path yet).
      -- All rows are 'legacy' until a future migration populates atlas_etf_state_v2.
      'legacy'::text                AS data_source
    FROM atlas.atlas_universe_etfs u
    LEFT JOIN latest l ON l.ticker = u.ticker
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_signal_unified eu
      ON eu.etf_ticker = u.ticker AND eu.date = (SELECT d FROM latest_signal)
    WHERE u.effective_to IS NULL
    ORDER BY
      (eu.pct_stage_4 IS NULL OR eu.pct_stage_4 < 0.50) DESC NULLS LAST,
      m.rs_pctile_3m DESC NULLS LAST
  `}async function s(e){return(await (0,_.A)`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
      WHERE ticker = ${e}
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.linked_index,
      u.inception_date::text        AS inception_date,
      u.asset_class,
      u.fund_house,
      l.d::text                     AS data_as_of,
      m.ret_1w::text                AS ret_1w,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      m.ret_6m::text                AS ret_6m,
      m.ret_12m::text               AS ret_12m,
      m.rs_pctile_3m::text          AS rs_pctile_3m,
      m.rs_3m_benchmark::text       AS rs_3m_benchmark,
      m.ema_10_ratio::text          AS ema_10_ratio,
      m.extension_pct::text         AS extension_pct,
      m.realized_vol_63::text       AS vol_63,
      m.drawdown_ratio_252::text    AS drawdown,
      m.volume_expansion::text      AS volume_expansion,
      m.avg_volume_20::text         AS avg_volume_20,
      m.effort_ratio_63::text       AS effort_ratio_63,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      NULL::int                     AS days_in_state,
      CASE
        WHEN eu.mean_rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN eu.mean_rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN eu.mean_rs_rank_12m >= 0.30 THEN 'Average'
        WHEN eu.mean_rs_rank_12m >= 0.10 THEN 'Weak'
        WHEN eu.mean_rs_rank_12m IS NOT NULL THEN 'Laggard'
        ELSE NULL
      END                           AS rs_state,
      CASE
        WHEN eu.pct_stage_2 >= 0.50  THEN 'Accelerating'
        WHEN eu.pct_stage_4 >= 0.50  THEN 'Collapsing'
        WHEN eu.pct_stage_3 >= 0.30  THEN 'Deteriorating'
        WHEN eu.pct_stage_2 IS NOT NULL THEN 'Flat'
        ELSE NULL
      END                           AS momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low' WHEN 2 THEN 'Normal' WHEN 3 THEN 'Elevated' WHEN 4 THEN 'High'
      END                           AS risk_state,
      (eu.pct_stage_2 IS NOT NULL AND eu.pct_stage_2 >= 0.50) AS weinstein_gate_pass,
      -- Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
      TRUE                          AS history_gate_pass,
      TRUE                          AS liquidity_gate_pass,
      (eu.pct_stage_4 IS NULL OR eu.pct_stage_4 < 0.50) AS is_investable,
      TRUE                          AS strength_gate,
      TRUE                          AS direction_gate,
      TRUE                          AS risk_gate,
      TRUE                          AS sector_gate,
      TRUE                          AS market_gate,
      NULL::text                    AS position_size_pct,
      NULL::boolean                 AS breakout_trigger,
      NULL::boolean                 AS transition_trigger,
      NULL::boolean                 AS exit_market_riskoff,
      NULL::boolean                 AS exit_sector_avoid,
      NULL::boolean                 AS exit_rs_deteriorate,
      NULL::boolean                 AS exit_momentum_collapse,
      NULL::boolean                 AS exit_stop_loss,
      -- Stage badge: engine_state from atlas_etf_signal_unified
      eu.engine_state,
      -- Phase 8: bubble chart axes
      eu.mean_rs_rank_12m::float8   AS mean_rs_rank_12m,
      eu.mean_within_state_rank::float8 AS mean_within_state_rank,
      eu.pct_stage_2::float8        AS pct_stage_2,
      eu.pct_stage_4::float8        AS pct_stage_4,
      -- C5: provenance. Migration-087 atlas_etf_signal_unified is legacy passthrough.
      'legacy'::text                AS data_source
    FROM atlas.atlas_universe_etfs u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_signal_unified eu
      ON eu.etf_ticker = u.ticker AND eu.date = l.d
    WHERE u.ticker = ${e}
      AND u.effective_to IS NULL
    LIMIT 1
  `)[0]??null}async function n(e,t=180){if(!Number.isInteger(t)||t<1||t>3650)throw Error(`days must be an integer between 1 and 3650, got: ${t}`);return(0,_.A)`
    SELECT
      date,
      rs_pctile_3m::text        AS rs_pctile_3m,
      rs_3m_benchmark::text     AS rs_3m_benchmark,
      ret_1w::text              AS ret_1w,
      ret_1m::text              AS ret_1m,
      ret_3m::text              AS ret_3m,
      ret_6m::text              AS ret_6m,
      ret_12m::text             AS ret_12m,
      ema_10_ratio::text        AS ema_10_ratio,
      ema_20_ratio::text        AS ema_20_ratio,
      extension_pct::text       AS extension_pct,
      realized_vol_63::text     AS vol_63,
      drawdown_ratio_252::text  AS drawdown,
      volume_expansion::text    AS volume_expansion,
      above_30w_ma
    FROM atlas.atlas_etf_metrics_daily
    WHERE ticker = ${e}
      AND date >= CURRENT_DATE - (${t} || ' days')::interval
    ORDER BY date ASC
  `}async function i(e,t=180){if(!Number.isInteger(t)||t<1||t>3650)throw Error(`days must be an integer between 1 and 3650, got: ${t}`);return(0,_.A)`
    WITH vol_window AS (
      SELECT date, realized_vol_63
      FROM atlas.atlas_etf_metrics_daily
      WHERE ticker = ${e}
        AND date >= CURRENT_DATE - (${t} || ' days')::interval
    )
    SELECT
      eu.date,
      CASE
        WHEN eu.mean_rs_rank_12m >= 0.90 THEN 'Leader'
        WHEN eu.mean_rs_rank_12m >= 0.70 THEN 'Strong'
        WHEN eu.mean_rs_rank_12m >= 0.30 THEN 'Average'
        WHEN eu.mean_rs_rank_12m >= 0.10 THEN 'Weak'
        WHEN eu.mean_rs_rank_12m IS NOT NULL THEN 'Laggard'
        ELSE NULL
      END                       AS rs_state,
      CASE
        WHEN eu.pct_stage_2 >= 0.50  THEN 'Accelerating'
        WHEN eu.pct_stage_4 >= 0.50  THEN 'Collapsing'
        WHEN eu.pct_stage_3 >= 0.30  THEN 'Deteriorating'
        WHEN eu.pct_stage_2 IS NOT NULL THEN 'Flat'
        ELSE NULL
      END                       AS momentum_state,
      CASE NTILE(4) OVER (ORDER BY vw.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low' WHEN 2 THEN 'Normal' WHEN 3 THEN 'Elevated' WHEN 4 THEN 'High'
      END                       AS risk_state
    FROM atlas.atlas_etf_signal_unified eu
    LEFT JOIN vol_window vw ON vw.date = eu.date
    WHERE eu.etf_ticker = ${e}
      AND eu.date >= CURRENT_DATE - (${t} || ' days')::interval
    ORDER BY eu.date ASC
  `}async function o(e,t=20){if(!Number.isInteger(t)||t<1||t>100)throw Error(`limit must be between 1 and 100, got: ${t}`);return(0,_.A)`
    WITH latest_holdings AS (
      SELECT MAX(as_of_date) AS as_of_date
      FROM public.de_etf_holdings
      WHERE ticker = ${e}
    ),
    latest_states_date AS (
      SELECT MAX(date) AS d
      FROM atlas.atlas_stock_signal_unified
      WHERE date <= COALESCE((SELECT as_of_date FROM latest_holdings), CURRENT_DATE)
    )
    SELECT
      u.symbol,
      u.company_name,
      h.weight::text            AS weight,
      u.sector,
      su.rs_state,
      su.momentum_state,
      NULL::text                AS risk_state,
      m.ret_1m::text            AS ret_1m,
      m.ret_3m::text            AS ret_3m,
      lh.as_of_date::text       AS holdings_date
    FROM public.de_etf_holdings h
    JOIN latest_holdings lh ON h.ticker = ${e}
      AND h.as_of_date = lh.as_of_date
    LEFT JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = h.instrument_id
      AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_stock_signal_unified su
      ON su.instrument_id = u.instrument_id
      AND su.date = (SELECT d FROM latest_states_date)
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id
      AND m.date = (SELECT d FROM latest_states_date)
    WHERE h.ticker = ${e}
    ORDER BY h.weight DESC
    LIMIT ${t}
  `}},65589:(e,t,a)=>{a.d(t,{Cx:()=>o,fh:()=>l,yd:()=>i});var _=a(60687),r=a(85814),s=a.n(r);function n(){return(0,_.jsx)("span",{className:"font-mono text-xs text-ink-tertiary",children:"—"})}function i({symbol:e,className:t=""}){return e?(0,_.jsx)(s(),{href:`/stocks/${encodeURIComponent(e)}`,className:`text-ink-primary hover:text-teal hover:underline transition-colors ${t}`,children:e}):n()}function o({sector:e,className:t=""}){return e?(0,_.jsx)(s(),{href:`/sectors/${encodeURIComponent(e)}`,className:`text-ink-secondary hover:text-teal hover:underline transition-colors ${t}`,children:e}):n()}function l({ticker:e,className:t=""}){return e?(0,_.jsx)(s(),{href:`/etfs/${encodeURIComponent(e)}`,className:`text-ink-primary hover:text-teal hover:underline transition-colors ${t}`,children:e}):n()}},89855:(e,t,a)=>{a.d(t,{Fq:()=>s,UD:()=>i,qh:()=>n});var _=a(5069),r=a(6707);async function s(){return(await (0,_.A)`
    SELECT
      ticker, etf_name, fund_house, asset_class, etf_category,
      composite_score::text, is_atlas_leader,
      premium_bps::text, te_60d::text, adv_20d_inr::text, adv_monthly_cr::text,
      ret_1d::text, ret_1w::text, ret_1m::text, ret_3m::text,
      ret_6m::text, ret_12m::text,
      rs_state, momentum_state,
      action, scatter_zone,
      signal_fire_date::text, signal_tenure::text,
      as_of_date::text, eli5
    FROM atlas.mv_etf_list_v6
    ORDER BY composite_score DESC NULLS LAST
  `).map(e=>({ticker:e.ticker,etf_name:e.etf_name,fund_house:e.fund_house,asset_class:e.asset_class,etf_category:e.etf_category,composite_score:(0,r.Ro)(e.composite_score),is_atlas_leader:e.is_atlas_leader??null,premium_bps:(0,r.Ro)(e.premium_bps),te_60d:(0,r.Ro)(e.te_60d),adv_20d_inr:(0,r.Ro)(e.adv_20d_inr),adv_monthly_cr:(0,r.Ro)(e.adv_monthly_cr),ret_1d:(0,r.Ro)(e.ret_1d),ret_1w:(0,r.Ro)(e.ret_1w),ret_1m:(0,r.Ro)(e.ret_1m),ret_3m:(0,r.Ro)(e.ret_3m),ret_6m:(0,r.Ro)(e.ret_6m),ret_12m:(0,r.Ro)(e.ret_12m),rs_state:e.rs_state,momentum_state:e.momentum_state,action:e.action,scatter_zone:e.scatter_zone,signal_fire_date:e.signal_fire_date,signal_tenure:e.signal_tenure,as_of_date:e.as_of_date,eli5:e.eli5}))}function n(e){let t=new Map;for(let a of e){let e=a.fund_house?.toUpperCase().trim()??"UNKNOWN";t.has(e)||t.set(e,{fund_house:e,etf_count:0,buy_count:0,avoid_count:0,watch_count:0,total_adv_cr:0,dominant_action:"neutral"});let _=t.get(e);_.etf_count+=1,"BUY"===a.action?_.buy_count+=1:"AVOID"===a.action?_.avoid_count+=1:"WATCH"===a.action&&(_.watch_count+=1),_.total_adv_cr+=a.adv_monthly_cr??0}return Array.from(t.values()).map(e=>({...e,dominant_action:e.buy_count>e.avoid_count&&e.buy_count>e.watch_count?"BUY":e.avoid_count>e.watch_count?"AVOID":e.watch_count>0?"WATCH":"neutral"})).sort((e,t)=>t.total_adv_cr-e.total_adv_cr)}async function i(e){var t,a;let s=(await (0,_.A)`
    SELECT
      ticker, etf_name, fund_house, asset_class, etf_category,
      as_of_date::text,
      composite_score::text, is_atlas_leader,
      premium_bps::text, te_60d::text, adv_20d_inr::text,
      ret_1m::text, ret_3m::text, ret_6m::text, ret_12m::text,
      rs_state, action, eli5,
      price_180d, peer_set
    FROM atlas.mv_etf_deepdive
    WHERE ticker = ${e.toUpperCase()}
    LIMIT 1
  `)[0];if(!s)return null;let n=(t=s.price_180d)&&Array.isArray(t)?t.map(e=>"object"!=typeof e||null===e?null:{date:String(e.date??""),open:o(e.open)??0,high:o(e.high)??0,low:o(e.low)??0,close:o(e.close)??0,volume:o(e.volume)??0}).filter(e=>null!==e&&""!==e.date):null,i=(a=s.peer_set)&&Array.isArray(a)?a.map(e=>"object"!=typeof e||null===e?null:{ticker:String(e.ticker??""),composite_score:o(e.composite_score),matrix_conviction_score:o(e.matrix_conviction_score),adv_20d_inr:o(e.adv_20d_inr),is_atlas_leader:"boolean"==typeof e.is_atlas_leader?e.is_atlas_leader:null,rank_in_category:o(e.rank_in_category),delta_composite:o(e.delta_composite)}).filter(e=>null!==e&&""!==e.ticker):null;return{ticker:s.ticker,etf_name:s.etf_name,fund_house:s.fund_house,asset_class:s.asset_class,etf_category:s.etf_category,as_of_date:s.as_of_date,composite_score:(0,r.Ro)(s.composite_score),is_atlas_leader:s.is_atlas_leader??null,premium_bps:(0,r.Ro)(s.premium_bps),te_60d:(0,r.Ro)(s.te_60d),adv_20d_inr:(0,r.Ro)(s.adv_20d_inr),ret_1m:(0,r.Ro)(s.ret_1m),ret_3m:(0,r.Ro)(s.ret_3m),ret_6m:(0,r.Ro)(s.ret_6m),ret_12m:(0,r.Ro)(s.ret_12m),rs_state:s.rs_state,action:s.action,eli5:s.eli5,price_180d:n,peer_set:i}}function o(e){return null==e?null:"number"==typeof e?Number.isFinite(e)?e:null:"string"==typeof e?(0,r.Ro)(e):null}}};