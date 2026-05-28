-- scripts/research/weinstein_forward_ic.sql
-- Task 3 of Stream A — forward 6m IC per (cap_tier × lookback × stage)
-- (docs/superpowers/plans/2026-05-28-trader-view-A-weinstein-research.md)
--
-- For each (cap_tier × lookback × stage) at each as_of_week, compute the
-- forward 6m excess return (vs NIFTY 500) per stock, then aggregate to
-- get IC + average excess + n_obs per cell.
--
-- IC is Pearson correlation between stage (1-4) and forward 6m excess.
-- We expect IC < 0 — Stage 2 should map to HIGH excess, Stage 4 to LOW.
-- Magnitude > 0.05 is the methodology lock's 6m floor.
--
-- Schema reality:
--   - public.de_equity_ohlcv (stock prices, close_adj)
--   - public.de_index_prices (index NIFTY 500, close only — no close_adj)
--   - atlas.atlas_universe_stocks.tier as cap_tier proxy (Large/Mid/Small)
--   - Plan uses 130-calendar-day forward window; we keep that for parity
--     (works against the underlying trading-day-only price table — only
--     hits when both ends fall on actual trading days)
--
-- This file is the persistence definition. We inline the grid + classifier
-- bodies (Tasks 1-2) at the top because their CREATE VIEW could not run
-- against Supabase (write gate classifies CREATE OR REPLACE as ALTER).

CREATE TABLE IF NOT EXISTS atlas.weinstein_research_ic (
  cap_tier        text    NOT NULL,
  lookback_weeks  int     NOT NULL,
  stage           int     NOT NULL,
  n_obs           bigint  NOT NULL,
  ic_pearson      numeric,
  avg_excess      numeric,
  sd_excess       numeric,
  computed_at     timestamptz DEFAULT NOW(),
  PRIMARY KEY (cap_tier, lookback_weeks, stage)
);

-- ===== Computation (run via INSERT INTO ... or as SELECT to CSV) =====
WITH daily_with_week AS (
  SELECT
    p.instrument_id,
    p.date,
    p.close_adj,
    (date_trunc('week', p.date))::date AS week_start
  FROM public.de_equity_ohlcv p
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = p.instrument_id
   AND u.effective_to IS NULL
   AND u.tier IN ('Large', 'Mid', 'Small')   -- Q5 lock: exclude Micro
   AND u.in_nifty_500 = TRUE                  -- liquid universe only
  WHERE p.date >= '2018-01-01'
    AND p.close_adj IS NOT NULL
),
weekly_close AS (
  SELECT DISTINCT ON (instrument_id, week_start)
    instrument_id, week_start, close_adj AS close_w
  FROM daily_with_week
  ORDER BY instrument_id, week_start, date DESC
),
weekly_with_mas AS (
  SELECT
    instrument_id, week_start, close_w,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN  4 PRECEDING AND CURRENT ROW) AS ma_5,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN  9 PRECEDING AND CURRENT ROW) AS ma_10,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS ma_30,
    ROW_NUMBER() OVER (PARTITION BY instrument_id ORDER BY week_start) AS wk_idx
  FROM weekly_close
),
grid AS (
  SELECT
    instrument_id,
    week_start AS as_of_week,
    p.lookback_weeks,
    close_w,
    CASE p.lookback_weeks
      WHEN  5 THEN ma_5
      WHEN 10 THEN ma_10
      WHEN 20 THEN ma_20
      WHEN 30 THEN ma_30
    END AS ma_value
  FROM weekly_with_mas
  CROSS JOIN (VALUES (5),(10),(20),(30)) AS p(lookback_weeks)
  WHERE wk_idx >= p.lookback_weeks
),
stage_classified AS (
  SELECT
    instrument_id, as_of_week, lookback_weeks, close_w, ma_value,
    CASE
      WHEN LAG(ma_value, 4) OVER w IS NULL
        OR LAG(ma_value, 4) OVER w = 0 THEN NULL
      ELSE (ma_value - LAG(ma_value, 4) OVER w) / LAG(ma_value, 4) OVER w
    END AS ma_slope_pct
  FROM grid
  WINDOW w AS (PARTITION BY instrument_id, lookback_weeks ORDER BY as_of_week)
),
stages AS (
  SELECT *,
    CASE
      WHEN ma_slope_pct IS NULL OR ma_value IS NULL THEN NULL
      WHEN close_w >= ma_value AND ma_slope_pct >    0.01  THEN 2
      WHEN close_w >= ma_value AND ABS(ma_slope_pct) <= 0.01 THEN 1
      WHEN close_w <  ma_value AND ABS(ma_slope_pct) <= 0.01 THEN 3
      WHEN close_w <  ma_value AND ma_slope_pct <   -0.01 THEN 4
      ELSE NULL
    END AS stage
  FROM stage_classified
),
stage_with_caps AS (
  SELECT
    s.instrument_id, s.as_of_week, s.lookback_weeks, s.stage,
    u.tier AS cap_tier
  FROM stages s
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = s.instrument_id AND u.effective_to IS NULL
  WHERE u.tier IN ('Large', 'Mid', 'Small') AND s.stage IS NOT NULL
),
nifty500 AS (
  SELECT date, close AS idx_close
  FROM public.de_index_prices
  WHERE index_code = 'NIFTY 500'
),
forward_returns AS (
  SELECT
    swc.cap_tier,
    swc.lookback_weeks,
    swc.stage,
    swc.as_of_week,
    swc.instrument_id,
    -- Stock forward 6m return (130 cal days ≈ 26 trading weeks)
    p_fwd.close_adj / NULLIF(p_now.close_adj, 0) - 1
      AS stock_6m,
    n_fwd.idx_close / NULLIF(n_now.idx_close, 0) - 1
      AS nifty_6m,
    (p_fwd.close_adj / NULLIF(p_now.close_adj, 0) - 1)
      - (n_fwd.idx_close / NULLIF(n_now.idx_close, 0) - 1)
      AS excess_6m
  FROM stage_with_caps swc
  LEFT JOIN public.de_equity_ohlcv p_now
    ON p_now.instrument_id = swc.instrument_id
   AND p_now.date = swc.as_of_week
  LEFT JOIN public.de_equity_ohlcv p_fwd
    ON p_fwd.instrument_id = swc.instrument_id
   AND p_fwd.date = swc.as_of_week + INTERVAL '130 days'
  LEFT JOIN nifty500 n_now
    ON n_now.date = swc.as_of_week
  LEFT JOIN nifty500 n_fwd
    ON n_fwd.date = swc.as_of_week + INTERVAL '130 days'
  WHERE swc.as_of_week <= CURRENT_DATE - INTERVAL '130 days'
)
INSERT INTO atlas.weinstein_research_ic
  (cap_tier, lookback_weeks, stage, n_obs, ic_pearson, avg_excess, sd_excess)
SELECT
  cap_tier,
  lookback_weeks,
  stage,
  COUNT(*) AS n_obs,
  -- Pearson IC: lower magnitude => weaker monotone link between stage and excess
  CORR(excess_6m::double precision, stage::double precision) AS ic_pearson,
  AVG(excess_6m) AS avg_excess,
  STDDEV(excess_6m) AS sd_excess
FROM forward_returns
WHERE excess_6m IS NOT NULL
GROUP BY cap_tier, lookback_weeks, stage
ORDER BY cap_tier, lookback_weeks, stage
ON CONFLICT (cap_tier, lookback_weeks, stage) DO UPDATE
  SET n_obs       = EXCLUDED.n_obs,
      ic_pearson  = EXCLUDED.ic_pearson,
      avg_excess  = EXCLUDED.avg_excess,
      sd_excess   = EXCLUDED.sd_excess,
      computed_at = NOW();
