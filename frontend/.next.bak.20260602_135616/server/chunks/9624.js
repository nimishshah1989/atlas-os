"use strict";exports.id=9624,exports.ids=[9624],exports.modules={10969:(t,_,e)=>{e.d(_,{y:()=>s});var a=e(5069);let n=null,l=0;async function s(){if(null!==n&&Date.now()-l<3e5)return n;let t=await (0,a.A)`
    SELECT
      component_name,
      badge,
      threshold_range,
      implied_action,
      horizon_days,
      mean_ic::float8     AS mean_ic,
      ic_ir::float8       AS ic_ir,
      q5_q1_spread::float8 AS q5_q1_spread,
      status
    FROM atlas.atlas_component_validation
    WHERE as_of_date = (
      SELECT MAX(as_of_date) FROM atlas.atlas_component_validation
    )
  `;return n=t,l=Date.now(),t}},27992:(t,_,e)=>{e.d(_,{Yp:()=>r,qf:()=>m});var a=e(5069);async function n(){return(await (0,a.A)`
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
  `)[0]??null}async function l(t){return(await (0,a.A)`
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
    WHERE portfolio_id = ${t}
    LIMIT 1
  `)[0]??null}function s(t,_){return null!=_?{value:_,source:"overridden"}:{value:t,source:"inherited"}}function i(t,_){let e=_??{};return{cash_floor_pct:s(t.cash_floor_pct,e.cash_floor_pct??null),respect_regime_cap:s(t.respect_regime_cap,e.respect_regime_cap??null),max_per_stock_pct:s(t.max_per_stock_pct,e.max_per_stock_pct??null),max_per_sector_pct:s(t.max_per_sector_pct,e.max_per_sector_pct??null),max_small_cap_pct:s(t.max_small_cap_pct,e.max_small_cap_pct??null),min_holdings:s(t.min_holdings,e.min_holdings??null),max_positions:s(t.max_positions,e.max_positions??null),buy_states:s(t.buy_states,e.buy_states??null),min_within_state_rank:s(t.min_within_state_rank,e.min_within_state_rank??null),min_rs_rank:s(t.min_rs_rank,e.min_rs_rank??null),hard_stop_pct:s(t.hard_stop_pct,e.hard_stop_pct??null),state_exit_trim:s(t.state_exit_trim,e.state_exit_trim??null),state_exit_full:s(t.state_exit_full,e.state_exit_full??null),trailing_stop_pct:s(t.trailing_stop_pct,e.trailing_stop_pct??null),instrument_universe:s(t.instrument_universe,e.instrument_universe??null),benchmark:s(t.benchmark,e.benchmark??null),rebalance_cadence:s(t.rebalance_cadence,e.rebalance_cadence??null)}}async function m(t){let[_,e]=await Promise.all([n(),l(t)]);return null===_?null:i(_,e)}async function r(){let t=await n();return null===t?null:i(t,null)}},33017:(t,_,e)=>{e.d(_,{JY:()=>m,Uk:()=>l,l_:()=>n,rx:()=>s});var a=e(5069);async function n(t){let _=t?.sectorFilter??null,e=t?.indexFilter??null;return(0,a.A)`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    ),
    latest_signal AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_signal_unified
    ),
    benchmark AS (
      SELECT
        cur.nifty500_close                          AS n500_now,
        m3.nifty500_close                           AS n500_3m,
        m6.nifty500_close                           AS n500_6m
      FROM atlas.atlas_market_regime_daily cur
      CROSS JOIN LATERAL (
        SELECT nifty500_close FROM atlas.atlas_market_regime_daily
        WHERE date <= cur.date - INTERVAL '63 days'
        ORDER BY date DESC LIMIT 1
      ) m3
      CROSS JOIN LATERAL (
        SELECT nifty500_close FROM atlas.atlas_market_regime_daily
        WHERE date <= cur.date - INTERVAL '126 days'
        ORDER BY date DESC LIMIT 1
      ) m6
      WHERE cur.date = (SELECT d FROM latest)
    )
    SELECT
      u.instrument_id::text           AS instrument_id,
      u.symbol,
      u.company_name,
      u.sector,
      u.in_nifty_50,
      u.in_nifty_100,
      u.in_nifty_500,
      m.ret_1m::text                  AS ret_1m,
      m.ret_3m::text                  AS ret_3m,
      m.ret_6m::text                  AS ret_6m,
      m.rs_pctile_3m::text            AS rs_pctile_3m,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      su.weinstein_gate_pass,
      m.ret_1w::text                       AS ret_1w,
      m.extension_pct::text                AS extension_pct,
      m.realized_vol_63::text              AS vol_63,
      m.realized_vol_63::text              AS realized_vol_63,
      m.avg_volume_20::text                AS avg_volume_20,
      m.ret_12m::text                      AS ret_12m,
      m.ret_1d::text                       AS ret_1d,
      m.rs_pctile_1w::text                 AS rs_pctile_1w,
      m.rs_pctile_1m::text                 AS rs_pctile_1m,
      m.vol_ratio_63::text                 AS vol_ratio_63,
      m.max_drawdown_252::text             AS max_drawdown_252,
      m.volume_expansion::text             AS volume_expansion,
      m.effort_ratio_63::text              AS effort_ratio_63,
      m.ema_20_ratio::text                 AS ema_20_ratio,
      m.ma_30w_slope_4w::text              AS ma_30w_slope_4w,
      m.atr_21::text                       AS atr_21,
      (m.extension_pct IS NOT NULL AND m.extension_pct > 0) AS above_200d_ma,
      (
        m.ema_200_stock IS NOT NULL
        AND m.extension_pct IS NOT NULL
        AND m.ema_50_stock IS NOT NULL
        AND m.ema_200_stock * (1 + m.extension_pct) > m.ema_50_stock
      )                                    AS above_50d_ma,
      m.drawdown_ratio_252::text           AS drawdown,
      su.dwell_days                        AS days_in_state,
      -- Gate columns: hardcoded TRUE (real gate logic moved to atlas_stock_signal_unified).
      TRUE                                 AS history_gate_pass,
      TRUE                                 AS liquidity_gate_pass,
      TRUE                                 AS strength_gate,
      TRUE                                 AS direction_gate,
      TRUE                                 AS risk_gate,
      TRUE                                 AS volume_gate,
      TRUE                                 AS sector_gate,
      TRUE                                 AS market_gate,
      su.rs_state,
      su.momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low'
        WHEN 2 THEN 'Normal'
        WHEN 3 THEN 'Elevated'
        WHEN 4 THEN 'High'
      END                                  AS risk_state,
      NULL::text                           AS volume_state,
      su.is_investable,
      su.engine_state,
      su.within_state_rank::float8         AS within_state_rank,
      su.rs_rank_12m::float8               AS rs_rank_12m,
      su.dwell_days,
      su.urgency_score,
      CASE
        WHEN m.ret_3m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_3m IS NOT NULL AND b.n500_3m > 0
        THEN (m.ret_3m - (b.n500_now - b.n500_3m) / b.n500_3m)::text
        ELSE NULL
      END AS alpha_3m,
      CASE
        WHEN m.ret_6m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_6m IS NOT NULL AND b.n500_6m > 0
        THEN (m.ret_6m - (b.n500_now - b.n500_6m) / b.n500_6m)::text
        ELSE NULL
      END AS alpha_6m
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    CROSS JOIN benchmark b
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_signal_unified su
      ON su.instrument_id = u.instrument_id AND su.date = (SELECT d FROM latest_signal)
    WHERE u.effective_to IS NULL
      AND (${_}::text IS NULL OR u.sector = ${_}::text)
      AND (
        ${e}::text IS NULL
        OR (${e} = 'Nifty 50'  AND u.in_nifty_50  = TRUE)
        OR (${e} = 'Nifty 100' AND u.in_nifty_100 = TRUE)
        OR (${e} = 'Nifty 500' AND u.in_nifty_500 = TRUE)
      )
    ORDER BY
      su.is_investable DESC NULLS LAST,
      m.rs_pctile_3m DESC NULLS LAST
  `}async function l(t){return(await (0,a.A)`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    ),
    benchmark AS (
      SELECT
        cur.nifty500_close                          AS n500_now,
        m3.nifty500_close                           AS n500_3m,
        m6.nifty500_close                           AS n500_6m
      FROM atlas.atlas_market_regime_daily cur
      CROSS JOIN LATERAL (
        SELECT nifty500_close FROM atlas.atlas_market_regime_daily
        WHERE date <= cur.date - INTERVAL '63 days'
        ORDER BY date DESC LIMIT 1
      ) m3
      CROSS JOIN LATERAL (
        SELECT nifty500_close FROM atlas.atlas_market_regime_daily
        WHERE date <= cur.date - INTERVAL '126 days'
        ORDER BY date DESC LIMIT 1
      ) m6
      WHERE cur.date = (SELECT d FROM latest)
    )
    SELECT
      u.instrument_id::text           AS instrument_id,
      u.symbol,
      u.company_name,
      u.sector,
      u.in_nifty_50,
      u.in_nifty_100,
      u.in_nifty_500,
      m.ret_1m::text                  AS ret_1m,
      m.ret_3m::text                  AS ret_3m,
      m.ret_6m::text                  AS ret_6m,
      m.rs_pctile_3m::text            AS rs_pctile_3m,
      m.above_30w_ma,
      m.ema_10_at_20d_high,
      su.weinstein_gate_pass,
      m.ret_1w::text                       AS ret_1w,
      m.extension_pct::text                AS extension_pct,
      m.realized_vol_63::text              AS vol_63,
      m.realized_vol_63::text              AS realized_vol_63,
      m.avg_volume_20::text                AS avg_volume_20,
      m.ret_12m::text                      AS ret_12m,
      m.ret_1d::text                       AS ret_1d,
      m.rs_pctile_1w::text                 AS rs_pctile_1w,
      m.rs_pctile_1m::text                 AS rs_pctile_1m,
      m.vol_ratio_63::text                 AS vol_ratio_63,
      m.max_drawdown_252::text             AS max_drawdown_252,
      m.volume_expansion::text             AS volume_expansion,
      m.effort_ratio_63::text              AS effort_ratio_63,
      m.ema_20_ratio::text                 AS ema_20_ratio,
      m.ma_30w_slope_4w::text              AS ma_30w_slope_4w,
      m.atr_21::text                       AS atr_21,
      (m.extension_pct IS NOT NULL AND m.extension_pct > 0) AS above_200d_ma,
      (
        m.ema_200_stock IS NOT NULL
        AND m.extension_pct IS NOT NULL
        AND m.ema_50_stock IS NOT NULL
        AND m.ema_200_stock * (1 + m.extension_pct) > m.ema_50_stock
      )                                    AS above_50d_ma,
      m.drawdown_ratio_252::text           AS drawdown,
      su.dwell_days                        AS days_in_state,
      -- Gate columns: hardcoded TRUE (real gate logic moved to atlas_stock_signal_unified).
      TRUE                                 AS history_gate_pass,
      TRUE                                 AS liquidity_gate_pass,
      TRUE                                 AS strength_gate,
      TRUE                                 AS direction_gate,
      TRUE                                 AS risk_gate,
      TRUE                                 AS volume_gate,
      TRUE                                 AS sector_gate,
      TRUE                                 AS market_gate,
      su.rs_state,
      su.momentum_state,
      CASE NTILE(4) OVER (ORDER BY m.realized_vol_63 NULLS LAST)
        WHEN 1 THEN 'Low'
        WHEN 2 THEN 'Normal'
        WHEN 3 THEN 'Elevated'
        WHEN 4 THEN 'High'
      END                                  AS risk_state,
      NULL::text                           AS volume_state,
      su.is_investable,
      su.engine_state,
      su.within_state_rank::float8         AS within_state_rank,
      su.rs_rank_12m::float8               AS rs_rank_12m,
      su.dwell_days,
      su.urgency_score,
      CASE
        WHEN m.ret_3m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_3m IS NOT NULL AND b.n500_3m > 0
        THEN (m.ret_3m - (b.n500_now - b.n500_3m) / b.n500_3m)::text
        ELSE NULL
      END AS alpha_3m,
      CASE
        WHEN m.ret_6m IS NOT NULL AND b.n500_now IS NOT NULL AND b.n500_6m IS NOT NULL AND b.n500_6m > 0
        THEN (m.ret_6m - (b.n500_now - b.n500_6m) / b.n500_6m)::text
        ELSE NULL
      END AS alpha_6m
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    CROSS JOIN benchmark b
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_signal_unified su
      ON su.instrument_id = u.instrument_id AND su.date = l.d
    WHERE u.symbol = ${t}
      AND u.effective_to IS NULL
    LIMIT 1
  `)[0]??null}async function s(t,_=180){if(!Number.isInteger(_)||_<1||_>3650)throw Error(`days must be an integer between 1 and 3650, got: ${_}`);return(0,a.A)`
    SELECT
      m.date,
      m.rs_pctile_3m::text        AS rs_pctile_3m,
      m.ret_1w::text              AS ret_1w,
      m.ret_1m::text              AS ret_1m,
      m.ret_3m::text              AS ret_3m,
      m.ret_6m::text              AS ret_6m,
      m.ret_12m::text             AS ret_12m,
      m.ema_10_ratio::text        AS ema_10_ratio,
      m.drawdown_ratio_252::text  AS drawdown_ratio_252,
      m.avg_volume_20::text       AS avg_volume_20,
      m.extension_pct::text       AS extension_pct,
      m.atr_21::text              AS atr_21,
      m.ema_20_ratio::text        AS ema_20_ratio,
      m.vol_ratio_63::text        AS vol_ratio_63,
      m.max_drawdown_252::text    AS max_drawdown_252,
      -- Alpha vs Nifty 500 (excess return, same window as ret_X).
      -- 1w/1m/3m: precomputed rs_*_nifty500 (= ret − Nifty500 ret).
      m.rs_1w_nifty500::text      AS alpha_1w,
      m.rs_1m_nifty500::text      AS alpha_1m,
      m.rs_3m_nifty500::text      AS alpha_3m,
      -- 6m/12m: derive from the Nifty 500 index's own ret_6m/12m on the same date.
      CASE WHEN m.ret_6m IS NOT NULL AND idx.ret_6m IS NOT NULL
        THEN (m.ret_6m - idx.ret_6m)::text END   AS alpha_6m,
      CASE WHEN m.ret_12m IS NOT NULL AND idx.ret_12m IS NOT NULL
        THEN (m.ret_12m - idx.ret_12m)::text END AS alpha_12m
    FROM atlas.atlas_stock_metrics_daily m
    LEFT JOIN atlas.atlas_index_metrics_daily idx
      ON idx.index_code = 'NIFTY 500' AND idx.date = m.date
    WHERE m.instrument_id = ${t}
      AND m.date >= CURRENT_DATE - INTERVAL '1 day' * ${_}
    ORDER BY m.date ASC
  `}async function i(t){return(await (0,a.A)`
    WITH ohlcv AS (
      SELECT date, COALESCE(close_adj, close)::float8 AS close,
             high::float8 AS high, low::float8 AS low,
             LAG(COALESCE(close_adj, close)) OVER (ORDER BY date) AS prev_close
      FROM public.de_equity_ohlcv
      WHERE instrument_id = ${t}::uuid
      ORDER BY date DESC
      LIMIT 280
    ),
    tr AS (
      SELECT date,
             GREATEST(high - low, ABS(high - prev_close), ABS(low - prev_close)) AS true_range
      FROM ohlcv
      WHERE prev_close IS NOT NULL
    ),
    atr14 AS (
      SELECT date,
             AVG(true_range) OVER (
               ORDER BY date
               ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
             ) AS atr_14
      FROM tr
    )
    SELECT
      (SELECT atr_14 FROM atr14 ORDER BY date DESC LIMIT 1)::float8 AS atr_14_current,
      (SELECT AVG(atr_14) FROM atr14)::float8 AS atr_14_252d_avg,
      ((SELECT atr_14 FROM atr14 ORDER BY date DESC LIMIT 1)::float8
       / NULLIF((SELECT AVG(atr_14) FROM atr14)::float8, 0))::float8 AS ratio
    WHERE EXISTS (SELECT 1 FROM atr14)
  `)[0]??null}async function m(t){let _=await i(t),e=_?.ratio??null,n=await (0,a.A)`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    ),
    ranked AS (
      SELECT
        instrument_id,
        NTILE(4) OVER (ORDER BY realized_vol_63 ASC NULLS LAST) AS tier
      FROM atlas.atlas_stock_metrics_daily
      WHERE date = (SELECT d FROM latest)
        AND realized_vol_63 IS NOT NULL
    )
    SELECT tier
    FROM ranked
    WHERE instrument_id = ${t}::uuid
    LIMIT 1
  `,l=n[0]?.tier??null;return{obv_slope:null,atr_ratio:e,realized_vol_tier:null!=l?({1:"Low",2:"Normal",3:"Elevated",4:"High"})[l]??null:null}}},70933:(t,_,e)=>{e.d(_,{Z:()=>n,_:()=>l});var a=e(5069);async function n(){return(await (0,a.A)`
    WITH latest_full AS (
      SELECT *
      FROM atlas.atlas_market_regime_daily
      WHERE pct_above_ema_50 IS NOT NULL
      ORDER BY date DESC
      LIMIT 1
    ),
    latest_any AS (
      SELECT *
      FROM atlas.atlas_market_regime_daily
      ORDER BY date DESC
      LIMIT 1
    )
    SELECT
      la.date,
      la.nifty500_close, la.nifty500_ema_50, la.nifty500_ema_200,
      la.nifty500_above_ema_50, la.nifty500_above_ema_200,
      la.nifty500_ema_50_slope, la.nifty500_ema_200_slope,
      COALESCE(la.pct_above_ema_20,  lf.pct_above_ema_20)  AS pct_above_ema_20,
      COALESCE(la.pct_above_ema_50,  lf.pct_above_ema_50)  AS pct_above_ema_50,
      COALESCE(la.pct_above_ema_200, lf.pct_above_ema_200) AS pct_above_ema_200,
      COALESCE(la.advances_count,    lf.advances_count)    AS advances_count,
      COALESCE(la.declines_count,    lf.declines_count)    AS declines_count,
      COALESCE(la.unchanged_count,   lf.unchanged_count)   AS unchanged_count,
      COALESCE(la.ad_ratio,          lf.ad_ratio)          AS ad_ratio,
      COALESCE(la.ad_line,           lf.ad_line)           AS ad_line,
      COALESCE(la.ad_line_slope_21,  lf.ad_line_slope_21)  AS ad_line_slope_21,
      COALESCE(la.mcclellan_oscillator, lf.mcclellan_oscillator) AS mcclellan_oscillator,
      COALESCE(la.mcclellan_summation,  lf.mcclellan_summation)  AS mcclellan_summation,
      COALESCE(la.new_52w_highs,     lf.new_52w_highs)     AS new_52w_highs,
      COALESCE(la.new_52w_lows,      lf.new_52w_lows)      AS new_52w_lows,
      COALESCE(la.net_new_highs,     lf.net_new_highs)     AS net_new_highs,
      COALESCE(la.new_high_low_ratio, lf.new_high_low_ratio) AS new_high_low_ratio,
      COALESCE(la.pct_in_strong_states, lf.pct_in_strong_states) AS pct_in_strong_states,
      COALESCE(la.pct_weinstein_pass,   lf.pct_weinstein_pass)   AS pct_weinstein_pass,
      la.india_vix, la.realized_vol_5d_nifty500, la.vol_252_median_nifty500,
      la.regime_state, la.deployment_multiplier, la.dislocation_active, la.dislocation_started
    FROM latest_any la
    LEFT JOIN latest_full lf ON true
  `)[0]??null}async function l(t){return(0,a.A)`
    SELECT
      date,
      regime_state,
      deployment_multiplier,
      nifty500_close,
      pct_above_ema_20,
      pct_above_ema_50,
      pct_above_ema_200,
      ad_ratio,
      ad_line,
      mcclellan_oscillator,
      mcclellan_summation,
      new_52w_highs,
      new_52w_lows,
      net_new_highs,
      new_high_low_ratio,
      pct_in_strong_states,
      pct_weinstein_pass,
      india_vix,
      nifty500_ema_50_slope,
      nifty500_ema_200_slope
    FROM atlas.atlas_market_regime_daily
    WHERE date >= NOW() - (${t} || ' days')::INTERVAL
    ORDER BY date ASC
  `}}};