-- scripts/research/weinstein_lookback_grid.sql
-- Task 1 of Stream A — Weinstein per cap-tier research
-- (docs/superpowers/plans/2026-05-28-trader-view-A-weinstein-research.md)
--
-- For each (instrument_id, as_of_week, lookback_weeks ∈ {5,10,20,30})
-- compute:
--   - weekly close (last close in calendar week)
--   - moving average over the last N weeks
--   - price-vs-MA percentage (close_w / ma_value - 1)
--
-- Schema reality check (vs plan draft):
--   * Stock prices live in public.de_equity_ohlcv (NOT atlas.atlas_prices_daily);
--     close_adj column exists and is the corp-action-adjusted close.
--   * cap_tier on atlas.atlas_universe_stocks lives in the column `tier`
--     (Large / Mid / Small / Micro). The daily snapshot on
--     atlas_scorecard_daily.cap_tier only has 3 dates of history so it is
--     not usable for an 8-year IC research run; use the static `tier`.
--
-- We avoid the "ROWS BETWEEN <var> PRECEDING" issue (Postgres requires a
-- literal frame bound) by computing one MA per lookback in its own
-- expression, then UNION-ing them into the long shape the IC compute wants.

CREATE OR REPLACE VIEW atlas.v_weinstein_grid_candidates AS
WITH daily_with_week AS (
  SELECT
    instrument_id,
    date,
    close_adj,
    (date_trunc('week', date))::date AS week_start
  FROM public.de_equity_ohlcv
  WHERE date >= '2018-01-01'
    AND close_adj IS NOT NULL
),
weekly_close AS (
  -- One row per (instrument, week_start) holding the last close of the week.
  SELECT DISTINCT ON (instrument_id, week_start)
    instrument_id,
    week_start,
    close_adj AS close_w
  FROM daily_with_week
  ORDER BY instrument_id, week_start, date DESC
),
weekly_with_mas AS (
  SELECT
    instrument_id,
    week_start,
    close_w,
    -- N-week MA (current row + N-1 prior weeks). ROW_NUMBER ensures we
    -- only emit MA values once the window is fully populated.
    AVG(close_w) OVER (
      PARTITION BY instrument_id
      ORDER BY week_start
      ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
    ) AS ma_5,
    AVG(close_w) OVER (
      PARTITION BY instrument_id
      ORDER BY week_start
      ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
    ) AS ma_10,
    AVG(close_w) OVER (
      PARTITION BY instrument_id
      ORDER BY week_start
      ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) AS ma_20,
    AVG(close_w) OVER (
      PARTITION BY instrument_id
      ORDER BY week_start
      ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS ma_30,
    ROW_NUMBER() OVER (PARTITION BY instrument_id ORDER BY week_start) AS wk_idx
  FROM weekly_close
)
SELECT
  instrument_id,
  week_start AS as_of_week,
  lookback_weeks,
  close_w,
  CASE lookback_weeks
    WHEN 5  THEN ma_5
    WHEN 10 THEN ma_10
    WHEN 20 THEN ma_20
    WHEN 30 THEN ma_30
  END AS ma_value,
  CASE lookback_weeks
    WHEN 5  THEN CASE WHEN ma_5  > 0 THEN close_w / ma_5  - 1 END
    WHEN 10 THEN CASE WHEN ma_10 > 0 THEN close_w / ma_10 - 1 END
    WHEN 20 THEN CASE WHEN ma_20 > 0 THEN close_w / ma_20 - 1 END
    WHEN 30 THEN CASE WHEN ma_30 > 0 THEN close_w / ma_30 - 1 END
  END AS price_vs_ma_pct
FROM weekly_with_mas
CROSS JOIN (VALUES (5), (10), (20), (30)) AS p(lookback_weeks)
WHERE wk_idx >= lookback_weeks;  -- discard rows before MA is fully formed
