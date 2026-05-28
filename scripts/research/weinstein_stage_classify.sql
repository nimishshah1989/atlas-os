-- scripts/research/weinstein_stage_classify.sql
-- Task 2 of Stream A — Weinstein stage classifier per candidate
-- (docs/superpowers/plans/2026-05-28-trader-view-A-weinstein-research.md)
--
-- For each (instrument_id, week, lookback) compute stage 1/2/3/4 using
-- price-vs-MA + MA slope over the previous 4 weeks.
--
-- Slope thresholds match canonical Weinstein:
--   slope_pct = (ma_now - ma_4w_ago) / ma_4w_ago
--   STAGE 1: price above MA, slope flat   (|slope| <= 0.01)
--   STAGE 2: price above MA, slope rising (slope > +0.01)
--   STAGE 3: price below MA, slope flat   (|slope| <= 0.01)
--   STAGE 4: price below MA, slope falling (slope < -0.01)
--
-- Dependencies:
--   - atlas.v_weinstein_grid_candidates (Task 1)
--     -- if the view is not persisted (gate blocker), inline its body
--     -- as a CTE at the top of the IC query in Task 3.

CREATE OR REPLACE VIEW atlas.v_weinstein_stage_classify AS
WITH base AS (
  SELECT
    instrument_id,
    as_of_week,
    lookback_weeks,
    close_w,
    ma_value,
    price_vs_ma_pct,
    LAG(ma_value, 4) OVER (
      PARTITION BY instrument_id, lookback_weeks
      ORDER BY as_of_week
    ) AS ma_4w_ago
  FROM atlas.v_weinstein_grid_candidates
),
classified AS (
  SELECT
    *,
    CASE
      WHEN ma_4w_ago IS NULL OR ma_4w_ago = 0 THEN NULL
      ELSE (ma_value - ma_4w_ago) / ma_4w_ago
    END AS ma_slope_pct
  FROM base
)
SELECT
  instrument_id,
  as_of_week,
  lookback_weeks,
  close_w,
  ma_value,
  ma_slope_pct,
  price_vs_ma_pct,
  CASE
    WHEN ma_slope_pct IS NULL OR ma_value IS NULL THEN NULL
    WHEN close_w >= ma_value AND ma_slope_pct >   0.01  THEN 2
    WHEN close_w >= ma_value AND ABS(ma_slope_pct) <= 0.01 THEN 1
    WHEN close_w <  ma_value AND ABS(ma_slope_pct) <= 0.01 THEN 3
    WHEN close_w <  ma_value AND ma_slope_pct <   -0.01 THEN 4
    -- Falls in a no-mans-land (e.g. price below MA with strong up slope OR
    -- price above MA with strong down slope) — treat as NULL.
    ELSE NULL
  END AS stage
FROM classified;
