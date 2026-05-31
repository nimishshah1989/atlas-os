-- mv_india_pulse v2 body (2026-05-30 Regime+IndiaPulse fix chunk)
-- Changes vs migration 100 live def:
--   (A) breadth_table: DMA->EMA labels; add "% above 20 EMA" row (data exists);
--       keep 100EMA + 4wk-high as data_gap until M2 computes the columns.
--   (B) sector_heatmap: emit rs_1m, rs_3m, rs_6m, rs_12m alongside rs_1w.
--   (C) macro/vix/narrative: date-tolerant LATERAL "latest macro row <= as_of_date"
--       (macro lags regime by ~2 trading days; exact-date join NULLed the
--       newest row -> blank term structure / macro cards / narrative ribbon).
WITH
dates AS (
  SELECT date AS as_of_date FROM atlas.atlas_market_regime_daily
),
regime_v5 AS (
  SELECT date, pct_above_ema_200, pct_above_ema_50, pct_above_ema_20,
         india_vix, ad_ratio, mcclellan_oscillator,
         new_52w_highs, new_52w_lows, ad_line, advances_count, declines_count
  FROM atlas.atlas_market_regime_daily
),
regime_v6 AS (
  SELECT date, smallcap_rs_z, cross_sectional_dispersion, vix_percentile,
         breadth_pct_above_200dma
  FROM atlas.atlas_regime_daily
),
macro_vix9d AS (
  SELECT date, vix_9d FROM atlas.atlas_macro_daily
),
macro_sparklines AS (
  SELECT m.date,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.usdinr) ORDER BY sp.date)
       FROM atlas.atlas_macro_daily sp
      WHERE sp.date > (m.date - '31 days'::interval) AND sp.date <= m.date AND sp.usdinr IS NOT NULL) AS usdinr_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.india_10y_yield) ORDER BY sp.date)
       FROM atlas.atlas_macro_daily sp
      WHERE sp.date > (m.date - '31 days'::interval) AND sp.date <= m.date AND sp.india_10y_yield IS NOT NULL) AS india_10y_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.brent_inr) ORDER BY sp.date)
       FROM atlas.atlas_macro_daily sp
      WHERE sp.date > (m.date - '31 days'::interval) AND sp.date <= m.date AND sp.brent_inr IS NOT NULL) AS brent_inr_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v',
              CASE WHEN sp.india_10y_yield IS NOT NULL AND sp.cpi_yoy IS NOT NULL
                   THEN sp.india_10y_yield - sp.cpi_yoy ELSE NULL::numeric END) ORDER BY sp.date)
       FROM atlas.atlas_macro_daily sp
      WHERE sp.date > (m.date - '31 days'::interval) AND sp.date <= m.date) AS real_yield_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.fii_cash_equity_flow_cr) ORDER BY sp.date)
       FROM atlas.atlas_macro_daily sp
      WHERE sp.date > (m.date - '31 days'::interval) AND sp.date <= m.date) AS fii_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.dii_flow) ORDER BY sp.date)
       FROM atlas.atlas_macro_daily sp
      WHERE sp.date > (m.date - '31 days'::interval) AND sp.date <= m.date) AS dii_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.us_10y_yield) ORDER BY sp.date)
       FROM atlas.atlas_macro_daily sp
      WHERE sp.date > (m.date - '31 days'::interval) AND sp.date <= m.date AND sp.us_10y_yield IS NOT NULL) AS us_10y_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.dxy) ORDER BY sp.date)
       FROM atlas.atlas_macro_daily sp
      WHERE sp.date > (m.date - '31 days'::interval) AND sp.date <= m.date AND sp.dxy IS NOT NULL) AS dxy_spark
  FROM atlas.atlas_macro_daily m
),
idx AS (
  SELECT date, index_code, ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m, rs_3m_nifty500
  FROM atlas.atlas_index_metrics_daily
  WHERE index_code IN ('NIFTY 50','NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250','NIFTY 500','NIFTY BANK','NIFTY IT')
),
idx_close AS (
  SELECT date, index_code, close FROM de_index_prices
  WHERE index_code IN ('NIFTY 50','NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250','NIFTY 500','NIFTY BANK','NIFTY IT')
),
gold AS (
  SELECT date, close, ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m, NULL::numeric AS rs_3m_nifty500
  FROM atlas.atlas_benchmark_returns_cache WHERE benchmark_code = 'GOLD'
),
headline_json AS (
  SELECT d1.date AS as_of_date,
    jsonb_build_array(
      jsonb_build_object('index_code','NIFTY 50','label','Nifty 50','close',ic50.close,'ret_1d',i50.ret_1d,'ret_1w',i50.ret_1w,'ret_1m',i50.ret_1m,'ret_3m',i50.ret_3m,'ret_6m',i50.ret_6m,'rs_3m_vs_nifty500',i50.rs_3m_nifty500),
      jsonb_build_object('index_code','NIFTY 100','label','Nifty 100','close',ic100.close,'ret_1d',i100.ret_1d,'ret_1w',i100.ret_1w,'ret_1m',i100.ret_1m,'ret_3m',i100.ret_3m,'ret_6m',i100.ret_6m,'rs_3m_vs_nifty500',i100.rs_3m_nifty500),
      jsonb_build_object('index_code','NIFTY MIDCAP 150','label','Nifty Midcap 150','close',icmc.close,'ret_1d',imc.ret_1d,'ret_1w',imc.ret_1w,'ret_1m',imc.ret_1m,'ret_3m',imc.ret_3m,'ret_6m',imc.ret_6m,'rs_3m_vs_nifty500',imc.rs_3m_nifty500),
      jsonb_build_object('index_code','NIFTY SMLCAP 250','label','Nifty Smallcap 250','close',icsc.close,'ret_1d',isc.ret_1d,'ret_1w',isc.ret_1w,'ret_1m',isc.ret_1m,'ret_3m',isc.ret_3m,'ret_6m',isc.ret_6m,'rs_3m_vs_nifty500',isc.rs_3m_nifty500),
      jsonb_build_object('index_code','NIFTY 500','label','Nifty 500','close',ic500.close,'ret_1d',i500.ret_1d,'ret_1w',i500.ret_1w,'ret_1m',i500.ret_1m,'ret_3m',i500.ret_3m,'ret_6m',i500.ret_6m,'rs_3m_vs_nifty500',NULL::numeric),
      jsonb_build_object('index_code','NIFTY BANK','label','Nifty Bank','close',icbnk.close,'ret_1d',ibnk.ret_1d,'ret_1w',ibnk.ret_1w,'ret_1m',ibnk.ret_1m,'ret_3m',ibnk.ret_3m,'ret_6m',ibnk.ret_6m,'rs_3m_vs_nifty500',ibnk.rs_3m_nifty500),
      jsonb_build_object('index_code','NIFTY IT','label','Nifty IT','close',icit.close,'ret_1d',iit.ret_1d,'ret_1w',iit.ret_1w,'ret_1m',iit.ret_1m,'ret_3m',iit.ret_3m,'ret_6m',iit.ret_6m,'rs_3m_vs_nifty500',iit.rs_3m_nifty500),
      jsonb_build_object('index_code','GOLD','label','Gold (₹/10g)','close',g.close,'ret_1d',g.ret_1d,'ret_1w',g.ret_1w,'ret_1m',g.ret_1m,'ret_3m',g.ret_3m,'ret_6m',g.ret_6m,'rs_3m_vs_nifty500',NULL::numeric)
    ) AS headline_indices
  FROM (SELECT DISTINCT date FROM atlas.atlas_market_regime_daily) d1
    LEFT JOIN idx i50 ON i50.date=d1.date AND i50.index_code='NIFTY 50'
    LEFT JOIN idx_close ic50 ON ic50.date=d1.date AND ic50.index_code='NIFTY 50'
    LEFT JOIN idx i100 ON i100.date=d1.date AND i100.index_code='NIFTY 100'
    LEFT JOIN idx_close ic100 ON ic100.date=d1.date AND ic100.index_code='NIFTY 100'
    LEFT JOIN idx imc ON imc.date=d1.date AND imc.index_code='NIFTY MIDCAP 150'
    LEFT JOIN idx_close icmc ON icmc.date=d1.date AND icmc.index_code='NIFTY MIDCAP 150'
    LEFT JOIN idx isc ON isc.date=d1.date AND isc.index_code='NIFTY SMLCAP 250'
    LEFT JOIN idx_close icsc ON icsc.date=d1.date AND icsc.index_code='NIFTY SMLCAP 250'
    LEFT JOIN idx i500 ON i500.date=d1.date AND i500.index_code='NIFTY 500'
    LEFT JOIN idx_close ic500 ON ic500.date=d1.date AND ic500.index_code='NIFTY 500'
    LEFT JOIN idx ibnk ON ibnk.date=d1.date AND ibnk.index_code='NIFTY BANK'
    LEFT JOIN idx_close icbnk ON icbnk.date=d1.date AND icbnk.index_code='NIFTY BANK'
    LEFT JOIN idx iit ON iit.date=d1.date AND iit.index_code='NIFTY IT'
    LEFT JOIN idx_close icit ON icit.date=d1.date AND icit.index_code='NIFTY IT'
    LEFT JOIN gold g ON g.date=d1.date
),
vix_pct AS (
  SELECT date, india_vix,
    percent_rank() OVER (ORDER BY india_vix) AS vix_5y_pct_all_time,
    round(percent_rank() OVER (ORDER BY india_vix ROWS BETWEEN 1260 PRECEDING AND CURRENT ROW)::numeric, 4) AS vix_5y_pct
  FROM atlas.atlas_market_regime_daily WHERE india_vix IS NOT NULL
),
breadth_deltas AS (
  SELECT date, pct_above_ema_200, pct_above_ema_100, pct_above_ema_50, pct_above_ema_20,
    pct_4w_high,
    new_52w_highs, new_52w_lows, ad_ratio, mcclellan_oscillator, ad_line,
    (pct_above_ema_200 - lag(pct_above_ema_200,5) OVER w) * 100 AS pct200_d1w,
    (pct_above_ema_200 - lag(pct_above_ema_200,21) OVER w) * 100 AS pct200_d1m,
    (pct_above_ema_200 - lag(pct_above_ema_200,63) OVER w) * 100 AS pct200_d3m,
    (pct_above_ema_100 - lag(pct_above_ema_100,5) OVER w) * 100 AS pct100_d1w,
    (pct_above_ema_100 - lag(pct_above_ema_100,21) OVER w) * 100 AS pct100_d1m,
    (pct_above_ema_100 - lag(pct_above_ema_100,63) OVER w) * 100 AS pct100_d3m,
    (pct_above_ema_50 - lag(pct_above_ema_50,5) OVER w) * 100 AS pct50_d1w,
    (pct_above_ema_50 - lag(pct_above_ema_50,21) OVER w) * 100 AS pct50_d1m,
    (pct_above_ema_50 - lag(pct_above_ema_50,63) OVER w) * 100 AS pct50_d3m,
    (pct_above_ema_20 - lag(pct_above_ema_20,5) OVER w) * 100 AS pct20_d1w,
    (pct_above_ema_20 - lag(pct_above_ema_20,21) OVER w) * 100 AS pct20_d1m,
    (pct_above_ema_20 - lag(pct_above_ema_20,63) OVER w) * 100 AS pct20_d3m,
    (pct_4w_high - lag(pct_4w_high,5) OVER w) * 100 AS p4wh_d1w,
    (pct_4w_high - lag(pct_4w_high,21) OVER w) * 100 AS p4wh_d1m,
    (pct_4w_high - lag(pct_4w_high,63) OVER w) * 100 AS p4wh_d3m,
    new_52w_highs - lag(new_52w_highs,5) OVER w AS highs_d1w,
    new_52w_highs - lag(new_52w_highs,21) OVER w AS highs_d1m,
    new_52w_highs - lag(new_52w_highs,63) OVER w AS highs_d3m,
    new_52w_lows - lag(new_52w_lows,5) OVER w AS lows_d1w,
    new_52w_lows - lag(new_52w_lows,21) OVER w AS lows_d1m,
    new_52w_lows - lag(new_52w_lows,63) OVER w AS lows_d3m,
    ad_ratio - lag(ad_ratio,5) OVER w AS adr_d1w,
    ad_ratio - lag(ad_ratio,21) OVER w AS adr_d1m,
    ad_ratio - lag(ad_ratio,63) OVER w AS adr_d3m,
    mcclellan_oscillator - lag(mcclellan_oscillator,5) OVER w AS mcl_d1w,
    mcclellan_oscillator - lag(mcclellan_oscillator,21) OVER w AS mcl_d1m,
    mcclellan_oscillator - lag(mcclellan_oscillator,63) OVER w AS mcl_d3m,
    ad_line - lag(ad_line,5) OVER w AS adl_d1w,
    ad_line - lag(ad_line,21) OVER w AS adl_d1m,
    ad_line - lag(ad_line,63) OVER w AS adl_d3m
  FROM atlas.atlas_market_regime_daily
  WINDOW w AS (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),
breadth_json AS (
  SELECT b.date AS as_of_date,
    jsonb_build_array(
      jsonb_build_object('metric','pct_above_20ema','label','% above 20 EMA','today',round(b.pct_above_ema_20*100,1),'delta_1w',round(b.pct20_d1w,1),'delta_1m',round(b.pct20_d1m,1),'delta_3m',round(b.pct20_d3m,1),'data_gap',(b.pct_above_ema_20 IS NULL)),
      jsonb_build_object('metric','pct_above_50ema','label','% above 50 EMA','today',round(b.pct_above_ema_50*100,1),'delta_1w',round(b.pct50_d1w,1),'delta_1m',round(b.pct50_d1m,1),'delta_3m',round(b.pct50_d3m,1),'data_gap',(b.pct_above_ema_50 IS NULL)),
      jsonb_build_object('metric','pct_above_100ema','label','% above 100 EMA','today',round(b.pct_above_ema_100*100,1),'delta_1w',round(b.pct100_d1w,1),'delta_1m',round(b.pct100_d1m,1),'delta_3m',round(b.pct100_d3m,1),'data_gap',(b.pct_above_ema_100 IS NULL)),
      jsonb_build_object('metric','pct_above_200ema','label','% above 200 EMA','today',round(b.pct_above_ema_200*100,1),'delta_1w',round(b.pct200_d1w,1),'delta_1m',round(b.pct200_d1m,1),'delta_3m',round(b.pct200_d3m,1),'data_gap',(b.pct_above_ema_200 IS NULL)),
      jsonb_build_object('metric','pct_4w_high','label','% at 4-week high','today',round(b.pct_4w_high*100,1),'delta_1w',round(b.p4wh_d1w,1),'delta_1m',round(b.p4wh_d1m,1),'delta_3m',round(b.p4wh_d3m,1),'data_gap',(b.pct_4w_high IS NULL)),
      jsonb_build_object('metric','new_52w_highs','label','52-week highs','today',b.new_52w_highs,'delta_1w',b.highs_d1w,'delta_1m',b.highs_d1m,'delta_3m',b.highs_d3m,'data_gap',false),
      jsonb_build_object('metric','new_52w_lows','label','52-week lows','today',b.new_52w_lows,'delta_1w',b.lows_d1w,'delta_1m',b.lows_d1m,'delta_3m',b.lows_d3m,'data_gap',false),
      jsonb_build_object('metric','ad_ratio','label','Advance/decline ratio','today',round(b.ad_ratio::numeric,2),'delta_1w',round(b.adr_d1w,2),'delta_1m',round(b.adr_d1m,2),'delta_3m',round(b.adr_d3m,2),'data_gap',false),
      jsonb_build_object('metric','mcclellan','label','McClellan oscillator','today',round(b.mcclellan_oscillator::numeric,0),'delta_1w',round(b.mcl_d1w,0),'delta_1m',round(b.mcl_d1m,0),'delta_3m',round(b.mcl_d3m,0),'data_gap',false),
      jsonb_build_object('metric','ad_line','label','Cumulative A-D line','today',round(b.ad_line::numeric,0),'delta_1w',round(b.adl_d1w,0),'delta_1m',round(b.adl_d1m,0),'delta_3m',round(b.adl_d3m,0),'data_gap',false)
    ) AS breadth_table
  FROM breadth_deltas b
),
sector_heatmap_json AS (
  SELECT s.date AS as_of_date,
    jsonb_agg(jsonb_build_object(
      'sector_name', s.sector_name,
      'rs_1w', round(s.rs_1w::numeric,4),
      'rs_1m', round(s.rs_1m::numeric,4),
      'rs_3m', round(s.bottomup_rs_3m_nifty500::numeric,4),
      'rs_6m', round(s.rs_6m::numeric,4),
      'rs_12m', round(s.rs_12m::numeric,4),
      'ret_1m', round(s.bottomup_ret_1m::numeric,4),
      'ret_3m', round(s.bottomup_ret_3m::numeric,4)
    ) ORDER BY COALESCE(s.rs_1w,0) DESC) AS sector_heatmap
  FROM atlas.atlas_sector_metrics_daily s
  GROUP BY s.date
),
tier_idx AS (
  SELECT date,
    max(CASE WHEN index_code='NIFTY SMLCAP 250' THEN ret_1w END) AS sc_ret_1w,
    max(CASE WHEN index_code='NIFTY SMLCAP 250' THEN ret_1m END) AS sc_ret_1m,
    max(CASE WHEN index_code='NIFTY SMLCAP 250' THEN ret_3m END) AS sc_ret_3m,
    max(CASE WHEN index_code='NIFTY SMLCAP 250' THEN ret_6m END) AS sc_ret_6m,
    max(CASE WHEN index_code='NIFTY SMLCAP 250' THEN ret_12m END) AS sc_ret_12m,
    max(CASE WHEN index_code='NIFTY MIDCAP 150' THEN ret_1w END) AS mc_ret_1w,
    max(CASE WHEN index_code='NIFTY MIDCAP 150' THEN ret_1m END) AS mc_ret_1m,
    max(CASE WHEN index_code='NIFTY MIDCAP 150' THEN ret_3m END) AS mc_ret_3m,
    max(CASE WHEN index_code='NIFTY MIDCAP 150' THEN ret_6m END) AS mc_ret_6m,
    max(CASE WHEN index_code='NIFTY MIDCAP 150' THEN ret_12m END) AS mc_ret_12m,
    max(CASE WHEN index_code='NIFTY 100' THEN ret_1w END) AS lc_ret_1w,
    max(CASE WHEN index_code='NIFTY 100' THEN ret_1m END) AS lc_ret_1m,
    max(CASE WHEN index_code='NIFTY 100' THEN ret_3m END) AS lc_ret_3m,
    max(CASE WHEN index_code='NIFTY 100' THEN ret_6m END) AS lc_ret_6m,
    max(CASE WHEN index_code='NIFTY 100' THEN ret_12m END) AS lc_ret_12m
  FROM atlas.atlas_index_metrics_daily
  WHERE index_code IN ('NIFTY SMLCAP 250','NIFTY MIDCAP 150','NIFTY 100')
  GROUP BY date
),
tier_leadership_json AS (
  SELECT t.date AS as_of_date,
    jsonb_build_object('returns_table', jsonb_build_array(
      jsonb_build_object('window','1w','sc',round(t.sc_ret_1w,4),'mc',round(t.mc_ret_1w,4),'lc',round(t.lc_ret_1w,4),'sc_lc_spread',round(COALESCE(t.sc_ret_1w,0)-COALESCE(t.lc_ret_1w,0),4),'mc_lc_spread',round(COALESCE(t.mc_ret_1w,0)-COALESCE(t.lc_ret_1w,0),4)),
      jsonb_build_object('window','1m','sc',round(t.sc_ret_1m,4),'mc',round(t.mc_ret_1m,4),'lc',round(t.lc_ret_1m,4),'sc_lc_spread',round(COALESCE(t.sc_ret_1m,0)-COALESCE(t.lc_ret_1m,0),4),'mc_lc_spread',round(COALESCE(t.mc_ret_1m,0)-COALESCE(t.lc_ret_1m,0),4)),
      jsonb_build_object('window','3m','sc',round(t.sc_ret_3m,4),'mc',round(t.mc_ret_3m,4),'lc',round(t.lc_ret_3m,4),'sc_lc_spread',round(COALESCE(t.sc_ret_3m,0)-COALESCE(t.lc_ret_3m,0),4),'mc_lc_spread',round(COALESCE(t.mc_ret_3m,0)-COALESCE(t.lc_ret_3m,0),4)),
      jsonb_build_object('window','6m','sc',round(t.sc_ret_6m,4),'mc',round(t.mc_ret_6m,4),'lc',round(t.lc_ret_6m,4),'sc_lc_spread',round(COALESCE(t.sc_ret_6m,0)-COALESCE(t.lc_ret_6m,0),4),'mc_lc_spread',round(COALESCE(t.mc_ret_6m,0)-COALESCE(t.lc_ret_6m,0),4)),
      jsonb_build_object('window','12m','sc',round(t.sc_ret_12m,4),'mc',round(t.mc_ret_12m,4),'lc',round(t.lc_ret_12m,4),'sc_lc_spread',round(COALESCE(t.sc_ret_12m,0)-COALESCE(t.lc_ret_12m,0),4),'mc_lc_spread',round(COALESCE(t.mc_ret_12m,0)-COALESCE(t.lc_ret_12m,0),4))
    ), 'smallcap_rs_z', rv6.smallcap_rs_z) AS tier_leadership
  FROM tier_idx t
    LEFT JOIN atlas.atlas_regime_daily rv6 ON rv6.date = t.date
),
dispersion_series_json AS (
  SELECT r.date AS as_of_date,
    (SELECT jsonb_agg(jsonb_build_object('date', s.date, 'value', round(s.cross_sectional_dispersion::numeric,6)) ORDER BY s.date)
       FROM atlas.atlas_regime_daily s
      WHERE s.date > (r.date - '61 days'::interval) AND s.date <= r.date AND s.cross_sectional_dispersion IS NOT NULL) AS dispersion_60d_series
  FROM atlas.atlas_market_regime_daily r
),
macro_deltas AS (
  SELECT m.date, m.usdinr, m.india_10y_yield, m.brent_inr, m.cpi_yoy,
    m.fii_cash_equity_flow_cr, m.dii_flow, m.us_10y_yield, m.dxy, m.vix_9d,
    CASE WHEN m.india_10y_yield IS NOT NULL AND m.cpi_yoy IS NOT NULL THEN m.india_10y_yield - m.cpi_yoy ELSE NULL::numeric END AS real_yield,
    sum(m.fii_cash_equity_flow_cr) OVER (ORDER BY m.date ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) AS fii_flow_1m_cr,
    sum(m.dii_flow) OVER (ORDER BY m.date ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) AS dii_flow_1m_cr,
    lag(m.usdinr,21) OVER (ORDER BY m.date) AS usdinr_1m_ago,
    lag(m.india_10y_yield,21) OVER (ORDER BY m.date) AS india_10y_1m_ago,
    lag(m.brent_inr,21) OVER (ORDER BY m.date) AS brent_inr_1m_ago,
    lag(m.us_10y_yield,21) OVER (ORDER BY m.date) AS us_10y_1m_ago,
    lag(m.dxy,21) OVER (ORDER BY m.date) AS dxy_1m_ago,
    m.usdinr - lag(m.usdinr,1) OVER (ORDER BY m.date) AS usdinr_ret_1d,
    m.india_10y_yield - lag(m.india_10y_yield,1) OVER (ORDER BY m.date) AS india_10y_ret_1d,
    m.brent_inr / NULLIF(lag(m.brent_inr,1) OVER (ORDER BY m.date),0) - 1 AS brent_inr_ret_1d,
    m.us_10y_yield - lag(m.us_10y_yield,1) OVER (ORDER BY m.date) AS us_10y_ret_1d,
    m.dxy / NULLIF(lag(m.dxy,1) OVER (ORDER BY m.date),0) - 1 AS dxy_ret_1d
  FROM atlas.atlas_macro_daily m
),
macro_cards_agg AS (
  SELECT md1.date AS as_of_date,
    jsonb_build_array(
      jsonb_build_object('id','usdinr','label','USD / INR','value',round(md1.usdinr::numeric,4),'ret_1d',round(md1.usdinr_ret_1d,6),'ret_1m',CASE WHEN md1.usdinr_1m_ago IS NOT NULL THEN round(md1.usdinr/NULLIF(md1.usdinr_1m_ago,0)-1,6) END,'sparkline_30d',sp.usdinr_spark),
      jsonb_build_object('id','india_10y','label','India 10Y G-Sec yield','value',round(md1.india_10y_yield::numeric,4),'ret_1d',round(md1.india_10y_ret_1d,6),'ret_1m',CASE WHEN md1.india_10y_1m_ago IS NOT NULL THEN round(md1.india_10y_yield-md1.india_10y_1m_ago,4) END,'sparkline_30d',sp.india_10y_spark),
      jsonb_build_object('id','brent_inr','label','Brent crude ₹/bbl','value',round(md1.brent_inr::numeric,2),'ret_1d',round(md1.brent_inr_ret_1d,6),'ret_1m',CASE WHEN md1.brent_inr_1m_ago IS NOT NULL THEN round(md1.brent_inr/NULLIF(md1.brent_inr_1m_ago,0)-1,6) END,'sparkline_30d',sp.brent_inr_spark),
      jsonb_build_object('id','real_yield','label','Real yield (10Y − CPI)','value',round(md1.real_yield,4),'ret_1d',NULL::numeric,'ret_1m',NULL::numeric,'sparkline_30d',sp.real_yield_spark),
      jsonb_build_object('id','fii_flow_1m','label','FII net flow · 1M cumulative','value',round(md1.fii_flow_1m_cr,0),'ret_1d',round(md1.fii_cash_equity_flow_cr::numeric,0),'ret_1m',NULL::numeric,'sparkline_30d',sp.fii_spark),
      jsonb_build_object('id','dii_flow_1m','label','DII net flow · 1M cumulative','value',round(md1.dii_flow_1m_cr,0),'ret_1d',round(md1.dii_flow::numeric,0),'ret_1m',NULL::numeric,'sparkline_30d',sp.dii_spark),
      jsonb_build_object('id','us_10y','label','US 10Y yield','value',round(md1.us_10y_yield::numeric,4),'ret_1d',round(md1.us_10y_ret_1d,6),'ret_1m',CASE WHEN md1.us_10y_1m_ago IS NOT NULL THEN round(md1.us_10y_yield-md1.us_10y_1m_ago,4) END,'sparkline_30d',sp.us_10y_spark),
      jsonb_build_object('id','dxy','label','DXY · USD index','value',round(md1.dxy::numeric,2),'ret_1d',round(md1.dxy_ret_1d,6),'ret_1m',CASE WHEN md1.dxy_1m_ago IS NOT NULL THEN round(md1.dxy/NULLIF(md1.dxy_1m_ago,0)-1,6) END,'sparkline_30d',sp.dxy_spark)
    ) AS macro_cards
  FROM macro_deltas md1
    LEFT JOIN macro_sparklines sp ON sp.date = md1.date
)
SELECT d.as_of_date,
  COALESCE(rv6.breadth_pct_above_200dma, rv5.pct_above_ema_200) AS breadth_pct_above_200dma,
  rv5.india_vix,
  rv6.cross_sectional_dispersion AS cross_section_dispersion,
  rv6.smallcap_rs_z,
  rv6.vix_percentile AS vix_pct_v6,
  rv5.india_vix AS vix_spot,
  round(vp.vix_5y_pct, 4) AS vix_5y_pct,
  CASE WHEN rv5.india_vix IS NOT NULL AND mv9.vix_9d IS NOT NULL THEN round(rv5.india_vix - mv9.vix_9d, 4) ELSE NULL::numeric END AS vix_term_structure,
  hj.headline_indices,
  bj.breadth_table,
  shj.sector_heatmap,
  tlj.tier_leadership,
  dsj.dispersion_60d_series,
  mcj.macro_cards,
  jsonb_build_object('india_10y_yield',round(md.india_10y_yield::numeric,4),'real_yield',round(md.real_yield,4),'cpi_yoy',round(md.cpi_yoy::numeric,4),'fii_flow_1m_cr',round(md.fii_flow_1m_cr,0),'dii_flow_1m_cr',round(md.dii_flow_1m_cr,0),'equity_earnings_yield',NULL::numeric) AS narrative_ribbon,
  now() AS refreshed_at
FROM dates d
  LEFT JOIN regime_v5 rv5 ON rv5.date = d.as_of_date
  LEFT JOIN regime_v6 rv6 ON rv6.date = d.as_of_date
  -- (C) macro is date-tolerant: pick the latest macro row on or before as_of_date.
  LEFT JOIN LATERAL (SELECT mv.vix_9d FROM macro_vix9d mv WHERE mv.date <= d.as_of_date ORDER BY mv.date DESC LIMIT 1) mv9 ON true
  LEFT JOIN LATERAL (SELECT md2.* FROM macro_deltas md2 WHERE md2.date <= d.as_of_date ORDER BY md2.date DESC LIMIT 1) md ON true
  LEFT JOIN vix_pct vp ON vp.date = d.as_of_date
  LEFT JOIN headline_json hj ON hj.as_of_date = d.as_of_date
  LEFT JOIN breadth_json bj ON bj.as_of_date = d.as_of_date
  LEFT JOIN sector_heatmap_json shj ON shj.as_of_date = d.as_of_date
  LEFT JOIN tier_leadership_json tlj ON tlj.as_of_date = d.as_of_date
  LEFT JOIN dispersion_series_json dsj ON dsj.as_of_date = d.as_of_date
  LEFT JOIN LATERAL (SELECT mca.macro_cards FROM macro_cards_agg mca WHERE mca.as_of_date <= d.as_of_date ORDER BY mca.as_of_date DESC LIMIT 1) mcj ON true;
