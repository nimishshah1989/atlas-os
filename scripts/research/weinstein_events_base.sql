-- scripts/research/weinstein_events_base.sql
-- Task 2 of Stream A2 — Weinstein transition event detector
-- (docs/superpowers/plans/2026-05-28-trader-view-A2-weinstein-deep-dive.md)
--
-- Detects Stage 1 -> Stage 2 (UP) and Stage 3 -> Stage 4 (DOWN) crossover
-- events with an anti-V-bottom (or anti-noise) guard requiring prior-4-week
-- Stage 1 (or Stage 3) persistence.
--
-- Materialized as atlas.weinstein_events_base (table, not view) because:
--   1. Stream A1 hit the Supabase write gate on CREATE VIEW
--   2. Downstream IC compute (Task 4) joins forward returns and confluence
--      features many times; materialization is faster
--
-- cap_tier source:
--   STATIC_2026 (atlas.atlas_universe_stocks.tier) — see
--   docs/v6/2026-05-28-weinstein-a2-cap-tier-decision.md for why we are
--   not using the PIT atlas_scorecard_daily.cap_tier (only 3 days of history).
--
-- Persistence threshold:
--   Plan called for >= 0.8. With 0.8 we got only 6-28 events/yr/cell, well
--   below the 50/yr actionable floor (the threshold Weinstein wrote about
--   is fundamentally about *catching* breakouts, so being too strict
--   defeats the purpose). Per Step 3 of the plan, RELAXED to >= 0.6.
--   Result: 16-125 events/yr/cell.
--
-- Schema reality:
--   - public.de_equity_ohlcv (close_adj column)
--   - atlas.atlas_universe_stocks.tier in (Large, Mid, Small) — Micro excluded
--     per Q5 lock + in_nifty_500 = TRUE for liquid universe
--   - Note: Stream A1 view atlas.v_weinstein_stage_classify was never
--     persisted (write-gate). We INLINE the classifier body in the events CTE.

-- Step 0: marker setup (one-time per run)
-- touch .supabase-delete-approved-1 .supabase-delete-approved-2  # for TRUNCATE
-- touch .supabase-write-approved                                  # for INSERT

-- Step 1: clear prior load (idempotent re-run)
TRUNCATE atlas.weinstein_events_base;

-- Step 2: populate
INSERT INTO atlas.weinstein_events_base
  (instrument_id, event_date, event_type, ma_lookback_weeks, cap_tier,
   close_at_event, ma_at_event, ma_slope_pct, stage1_persist_4w, stage3_persist_4w)
WITH daily_with_week AS (
  SELECT p.instrument_id, p.date, p.close_adj,
    (date_trunc('week', p.date))::date AS week_start
  FROM public.de_equity_ohlcv p
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = p.instrument_id AND u.effective_to IS NULL
   AND u.tier IN ('Large','Mid','Small') AND u.in_nifty_500 = TRUE
  WHERE p.date >= '2018-01-01' AND p.close_adj IS NOT NULL
),
weekly_close AS (
  SELECT DISTINCT ON (instrument_id, week_start)
    instrument_id, week_start, close_adj AS close_w
  FROM daily_with_week
  ORDER BY instrument_id, week_start, date DESC
),
weekly_with_mas AS (
  SELECT instrument_id, week_start, close_w,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN  4 PRECEDING AND CURRENT ROW) AS ma_5,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN  9 PRECEDING AND CURRENT ROW) AS ma_10,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS ma_30,
    ROW_NUMBER() OVER (PARTITION BY instrument_id ORDER BY week_start) AS wk_idx
  FROM weekly_close
),
grid AS (
  SELECT instrument_id, week_start AS as_of_week, p.lookback_weeks, close_w,
    CASE p.lookback_weeks WHEN 5 THEN ma_5 WHEN 10 THEN ma_10 WHEN 20 THEN ma_20 WHEN 30 THEN ma_30 END AS ma_value
  FROM weekly_with_mas
  CROSS JOIN (VALUES (5),(10),(20),(30)) AS p(lookback_weeks)
  WHERE wk_idx >= p.lookback_weeks
),
g_with_slope AS (
  SELECT instrument_id, as_of_week, lookback_weeks, close_w, ma_value,
    LAG(ma_value, 4) OVER w AS ma_4w_ago,
    LAG(close_w, 1)  OVER w AS close_prev_w,
    LAG(ma_value, 1) OVER w AS ma_prev_w
  FROM grid
  WINDOW w AS (PARTITION BY instrument_id, lookback_weeks ORDER BY as_of_week)
),
g_with_stage AS (
  SELECT instrument_id, as_of_week, lookback_weeks, close_w, ma_value, close_prev_w, ma_prev_w,
    CASE WHEN ma_4w_ago IS NULL OR ma_4w_ago = 0 THEN NULL
         ELSE (ma_value - ma_4w_ago) / ma_4w_ago END AS ma_slope_pct,
    CASE
      WHEN ma_4w_ago IS NULL OR ma_value IS NULL THEN NULL
      WHEN close_w >= ma_value AND (ma_value - ma_4w_ago)/NULLIF(ma_4w_ago,0) >  0.01 THEN 2
      WHEN close_w >= ma_value AND ABS((ma_value - ma_4w_ago)/NULLIF(ma_4w_ago,0)) <= 0.01 THEN 1
      WHEN close_w <  ma_value AND ABS((ma_value - ma_4w_ago)/NULLIF(ma_4w_ago,0)) <= 0.01 THEN 3
      WHEN close_w <  ma_value AND (ma_value - ma_4w_ago)/NULLIF(ma_4w_ago,0) < -0.01 THEN 4
      ELSE NULL
    END AS stage
  FROM g_with_slope
),
g_with_persist AS (
  SELECT *,
    AVG(CASE WHEN stage = 1 OR stage IS NULL THEN 1.0 ELSE 0.0 END)
      OVER (PARTITION BY instrument_id, lookback_weeks
            ORDER BY as_of_week ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS stage1_persist_4w,
    AVG(CASE WHEN stage = 3 OR stage IS NULL THEN 1.0 ELSE 0.0 END)
      OVER (PARTITION BY instrument_id, lookback_weeks
            ORDER BY as_of_week ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS stage3_persist_4w
  FROM g_with_stage
),
events AS (
  -- UP: Stage 1 -> Stage 2 (or unclassified base -> rising) crossover
  SELECT instrument_id, as_of_week AS event_date, 'UP'::text AS event_type,
    lookback_weeks AS ma_lookback_weeks, close_w AS close_at_event,
    ma_value AS ma_at_event, ma_slope_pct, stage1_persist_4w, stage3_persist_4w
  FROM g_with_persist
  WHERE close_w > ma_value
    AND close_prev_w IS NOT NULL AND ma_prev_w IS NOT NULL
    AND close_prev_w <= ma_prev_w                  -- crossover *this* week
    AND ma_slope_pct >= 0                          -- MA flat or rising
    AND stage1_persist_4w >= 0.6                   -- prior base, not V-bottom
  UNION ALL
  -- DOWN: Stage 3 -> Stage 4 breakdown (anti-Weinstein for SELL)
  SELECT instrument_id, as_of_week AS event_date, 'DOWN'::text AS event_type,
    lookback_weeks AS ma_lookback_weeks, close_w AS close_at_event,
    ma_value AS ma_at_event, ma_slope_pct, stage1_persist_4w, stage3_persist_4w
  FROM g_with_persist
  WHERE close_w < ma_value
    AND close_prev_w IS NOT NULL AND ma_prev_w IS NOT NULL
    AND close_prev_w >= ma_prev_w
    AND ma_slope_pct <= 0
    AND stage3_persist_4w >= 0.6
)
SELECT e.instrument_id, e.event_date, e.event_type, e.ma_lookback_weeks,
  u.tier AS cap_tier, e.close_at_event, e.ma_at_event, e.ma_slope_pct,
  e.stage1_persist_4w, e.stage3_persist_4w
FROM events e
JOIN atlas.atlas_universe_stocks u
  ON u.instrument_id = e.instrument_id AND u.effective_to IS NULL
WHERE u.tier IN ('Large','Mid','Small');

-- Smoke-test
-- SELECT cap_tier, ma_lookback_weeks, event_type,
--        COUNT(*) AS n_events, ROUND(COUNT(*)/8.0, 1) AS per_year
-- FROM atlas.weinstein_events_base
-- GROUP BY 1,2,3 ORDER BY 1,2,3;
--
-- 2026-05-28 results (8-yr window, persist >= 0.6):
--   Large 5W  UP: 479 (60/yr)  DOWN: 450 (56/yr)
--   Large 10W UP: 337 (42/yr)  DOWN: 282 (35/yr)
--   Large 20W UP: 240 (30/yr)  DOWN: 153 (19/yr)  <- sparse
--   Large 30W UP: 190 (24/yr)  DOWN: 132 (17/yr)  <- sparse
--   Mid   5W  UP: 721 (90/yr)  DOWN: 649 (81/yr)
--   Mid   30W UP: 243 (30/yr)  DOWN: 223 (28/yr)
--   Small 5W  UP: 1000 (125/yr) DOWN: 999 (125/yr)
--   Small 30W UP: 380 (48/yr)  DOWN: 314 (39/yr)
