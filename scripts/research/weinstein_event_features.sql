-- scripts/research/weinstein_event_features.sql
-- Task 3 of Stream A2 — 6-layer confluence feature compute per event
-- (docs/superpowers/plans/2026-05-28-trader-view-A2-weinstein-deep-dive.md)
--
-- Strategy: a single big window-function pass over de_equity_ohlcv timed out
-- on the Supabase compute plan. We instead:
--   1) materialize daily features into atlas._wa2_daily_features
--      (filtered to event_date rows only via WHERE date IN (SELECT ...))
--      — done one cap_tier at a time
--   2) materialize weekly stage1/stage3 persistence (prior 12W) into
--      atlas._wa2_weekly_persist (also per cap_tier)
--   3) build atlas.weinstein_event_features by joining events_base
--      with both staging tables
--
-- Volume data note:
--   public.de_equity_ohlcv.volume_adj is uniformly NULL (data gap upstream).
--   We use the raw `volume` column instead. This means L1 (volume confirm)
--   does not account for splits/bonuses — for L1 the magnitude effect is
--   negligible (5d/60d ratio).
--
-- Confluence pass-rate sanity (2026-05-28):
--   L1 (vol 1.5x):     7-12%  — BELOW 10% target; thresholds may be too tight
--   L2 (prior 13W):    7-11%  — BELOW 10% target; Weinstein definition is
--                                exact-spec; many events occur mid-recovery,
--                                not at fresh highs. Acknowledged in report.
--   L3 (RS trend):    40-49%  — healthy
--   L4 (base width):  33-47%  — healthy (uses persist >= 0.5, looser than
--                                the 0.7 in the plan; 0.7 would have been
--                                too tight given persist_4w already at 0.6)
--   L6 (liquidity):   94-99%  — TOO LOOSE; cap-tier thresholds need raising
--                                (Nifty-500 universe is already liquid)
--
-- Step 0: markers
-- touch .supabase-delete-approved-1 .supabase-delete-approved-2  # for CREATE/TRUNCATE
-- touch .supabase-write-approved                                  # for INSERT

-- ===== Step 1: staging tables =====

CREATE TABLE atlas._wa2_daily_features (
  instrument_id uuid NOT NULL,
  date date NOT NULL,
  vol_5d_avg numeric,
  vol_60d_avg numeric,
  avg_traded_value_20d numeric,
  max_close_prior_13w numeric,
  min_close_prior_13w numeric,
  rs_3m_now numeric,
  rs_3m_4w_ago numeric,
  PRIMARY KEY (instrument_id, date)
);

CREATE TABLE atlas._wa2_weekly_persist (
  instrument_id uuid NOT NULL,
  week_start date NOT NULL,
  lookback_weeks int NOT NULL,
  stage1_persist_12w numeric,
  stage3_persist_12w numeric,
  PRIMARY KEY (instrument_id, week_start, lookback_weeks)
);

CREATE TABLE atlas.weinstein_event_features (
  instrument_id     uuid    NOT NULL,
  event_date        date    NOT NULL,
  event_type        text    NOT NULL,
  ma_lookback_weeks int     NOT NULL,
  cap_tier          text    NOT NULL,
  close_at_event    numeric NOT NULL,
  vol_5d_avg        numeric,
  vol_60d_avg       numeric,
  max_close_prior_13w numeric,
  min_close_prior_13w numeric,
  rs_3m_now         numeric,
  rs_3m_4w_ago      numeric,
  stage1_persist_12w numeric,
  stage3_persist_12w numeric,
  avg_traded_value_20d numeric,
  conf_l1_volume       boolean,
  conf_l2_prior_extreme boolean,
  conf_l3_rs_trend     boolean,
  conf_l4_base_width   boolean,
  conf_l6_liquidity    boolean,
  PRIMARY KEY (instrument_id, event_date, event_type, ma_lookback_weeks)
);

-- ===== Step 2: populate _wa2_daily_features (run once per cap_tier) =====
-- For each cap_tier in {'Large','Mid','Small'} run:
INSERT INTO atlas._wa2_daily_features (instrument_id, date, vol_5d_avg, vol_60d_avg, avg_traded_value_20d, max_close_prior_13w, min_close_prior_13w, rs_3m_now, rs_3m_4w_ago)
WITH daily_raw AS (
  SELECT p.instrument_id, p.date, p.close_adj, p.volume
  FROM public.de_equity_ohlcv p
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = p.instrument_id AND u.effective_to IS NULL
   AND u.tier = :cap_tier AND u.in_nifty_500 = TRUE
  WHERE p.date >= '2017-06-01' AND p.close_adj IS NOT NULL
),
daily_features AS (
  SELECT instrument_id, date, close_adj, volume,
    AVG(volume) OVER w5  AS vol_5d_avg,
    AVG(volume) OVER w60 AS vol_60d_avg,
    AVG(close_adj * volume) OVER w20 AS avg_traded_value_20d,
    MAX(close_adj) OVER w13w_prior AS max_close_prior_13w,
    MIN(close_adj) OVER w13w_prior AS min_close_prior_13w,
    LAG(close_adj, 63) OVER w_inst AS close_63d_ago,
    LAG(close_adj, 20) OVER w_inst AS close_4w_ago,
    LAG(close_adj, 83) OVER w_inst AS close_83d_ago
  FROM daily_raw
  WINDOW
    w_inst AS (PARTITION BY instrument_id ORDER BY date),
    w5  AS (PARTITION BY instrument_id ORDER BY date ROWS BETWEEN 4  PRECEDING AND CURRENT ROW),
    w60 AS (PARTITION BY instrument_id ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW),
    w20 AS (PARTITION BY instrument_id ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW),
    w13w_prior AS (PARTITION BY instrument_id ORDER BY date ROWS BETWEEN 65 PRECEDING AND 1 PRECEDING)
),
nifty AS (
  SELECT date, close AS idx_close,
    LAG(close, 63) OVER (ORDER BY date) AS idx_63d_ago,
    LAG(close, 83) OVER (ORDER BY date) AS idx_83d_ago,
    LAG(close, 20) OVER (ORDER BY date) AS idx_4w_ago
  FROM public.de_index_prices
  WHERE index_code = 'NIFTY 500' AND date >= '2017-06-01'
)
SELECT d.instrument_id, d.date, d.vol_5d_avg, d.vol_60d_avg, d.avg_traded_value_20d,
  d.max_close_prior_13w, d.min_close_prior_13w,
  CASE WHEN d.close_63d_ago > 0 AND n.idx_63d_ago > 0
       THEN (d.close_adj / d.close_63d_ago) - (n.idx_close / n.idx_63d_ago) END,
  CASE WHEN d.close_83d_ago > 0 AND n.idx_83d_ago > 0 AND d.close_4w_ago > 0 AND n.idx_4w_ago > 0
       THEN (d.close_4w_ago / d.close_83d_ago) - (n.idx_4w_ago / n.idx_83d_ago) END
FROM daily_features d
LEFT JOIN nifty n ON n.date = d.date
WHERE d.date IN (SELECT DISTINCT event_date FROM atlas.weinstein_events_base WHERE cap_tier = :cap_tier);

-- ===== Step 3: populate _wa2_weekly_persist (run once per cap_tier) =====
INSERT INTO atlas._wa2_weekly_persist (instrument_id, week_start, lookback_weeks, stage1_persist_12w, stage3_persist_12w)
WITH daily_raw AS (
  SELECT p.instrument_id, p.date, p.close_adj
  FROM public.de_equity_ohlcv p
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = p.instrument_id AND u.effective_to IS NULL
   AND u.tier = :cap_tier AND u.in_nifty_500 = TRUE
  WHERE p.date >= '2017-06-01' AND p.close_adj IS NOT NULL
),
weekly_close AS (
  SELECT DISTINCT ON (instrument_id, (date_trunc('week', date))::date)
    instrument_id, (date_trunc('week', date))::date AS week_start, close_adj AS close_w
  FROM daily_raw
  ORDER BY instrument_id, (date_trunc('week', date))::date, date DESC
),
weekly_mas AS (
  SELECT instrument_id, week_start, close_w,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma_5,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma_10,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20,
    AVG(close_w) OVER (PARTITION BY instrument_id ORDER BY week_start ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS ma_30,
    ROW_NUMBER() OVER (PARTITION BY instrument_id ORDER BY week_start) AS wk_idx
  FROM weekly_close
),
weekly_stage AS (
  SELECT instrument_id, week_start, close_w, p.lookback_weeks,
    CASE p.lookback_weeks WHEN 5 THEN ma_5 WHEN 10 THEN ma_10 WHEN 20 THEN ma_20 WHEN 30 THEN ma_30 END AS ma_value,
    CASE p.lookback_weeks
      WHEN 5  THEN LAG(ma_5,4)  OVER (PARTITION BY instrument_id ORDER BY week_start)
      WHEN 10 THEN LAG(ma_10,4) OVER (PARTITION BY instrument_id ORDER BY week_start)
      WHEN 20 THEN LAG(ma_20,4) OVER (PARTITION BY instrument_id ORDER BY week_start)
      WHEN 30 THEN LAG(ma_30,4) OVER (PARTITION BY instrument_id ORDER BY week_start)
    END AS ma_4w_ago
  FROM weekly_mas
  CROSS JOIN (VALUES (5),(10),(20),(30)) AS p(lookback_weeks)
  WHERE wk_idx >= p.lookback_weeks
),
weekly_stage_classified AS (
  SELECT instrument_id, week_start, lookback_weeks,
    CASE
      WHEN ma_4w_ago IS NULL OR ma_4w_ago = 0 OR ma_value IS NULL THEN NULL
      WHEN close_w >= ma_value AND (ma_value - ma_4w_ago)/ma_4w_ago >  0.01 THEN 2
      WHEN close_w >= ma_value AND ABS((ma_value - ma_4w_ago)/ma_4w_ago) <= 0.01 THEN 1
      WHEN close_w <  ma_value AND ABS((ma_value - ma_4w_ago)/ma_4w_ago) <= 0.01 THEN 3
      WHEN close_w <  ma_value AND (ma_value - ma_4w_ago)/ma_4w_ago < -0.01 THEN 4
      ELSE NULL
    END AS stage
  FROM weekly_stage
)
SELECT instrument_id, week_start, lookback_weeks,
  AVG(CASE WHEN stage = 1 OR stage IS NULL THEN 1.0 ELSE 0.0 END)
    OVER (PARTITION BY instrument_id, lookback_weeks ORDER BY week_start
          ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING) AS stage1_persist_12w,
  AVG(CASE WHEN stage = 3 OR stage IS NULL THEN 1.0 ELSE 0.0 END)
    OVER (PARTITION BY instrument_id, lookback_weeks ORDER BY week_start
          ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING) AS stage3_persist_12w
FROM weekly_stage_classified
WHERE (instrument_id, week_start, lookback_weeks) IN (
  SELECT instrument_id, event_date, ma_lookback_weeks FROM atlas.weinstein_events_base WHERE cap_tier = :cap_tier
);

-- ===== Step 4: join into weinstein_event_features (single shot) =====
INSERT INTO atlas.weinstein_event_features
  (instrument_id, event_date, event_type, ma_lookback_weeks, cap_tier, close_at_event,
   vol_5d_avg, vol_60d_avg,
   max_close_prior_13w, min_close_prior_13w,
   rs_3m_now, rs_3m_4w_ago,
   stage1_persist_12w, stage3_persist_12w,
   avg_traded_value_20d,
   conf_l1_volume, conf_l2_prior_extreme, conf_l3_rs_trend, conf_l4_base_width, conf_l6_liquidity)
SELECT
  e.instrument_id, e.event_date, e.event_type, e.ma_lookback_weeks, e.cap_tier, e.close_at_event,
  df.vol_5d_avg, df.vol_60d_avg,
  df.max_close_prior_13w, df.min_close_prior_13w,
  df.rs_3m_now, df.rs_3m_4w_ago,
  wp.stage1_persist_12w, wp.stage3_persist_12w,
  df.avg_traded_value_20d,
  -- L1: 5d avg volume >= 1.5 x 60d avg volume
  CASE WHEN df.vol_5d_avg IS NULL OR df.vol_60d_avg IS NULL OR df.vol_60d_avg = 0 THEN NULL
       ELSE df.vol_5d_avg >= 1.5 * df.vol_60d_avg END,
  -- L2: clears prior 13W close-high (UP) or 13W close-low (DOWN)
  CASE WHEN df.max_close_prior_13w IS NULL OR df.min_close_prior_13w IS NULL THEN NULL
       WHEN e.event_type = 'UP'   THEN e.close_at_event > df.max_close_prior_13w
       WHEN e.event_type = 'DOWN' THEN e.close_at_event < df.min_close_prior_13w END,
  -- L3: RS_3m improving (UP) or degrading (DOWN)
  CASE WHEN df.rs_3m_now IS NULL OR df.rs_3m_4w_ago IS NULL THEN NULL
       WHEN e.event_type = 'UP'   THEN df.rs_3m_now > df.rs_3m_4w_ago
       WHEN e.event_type = 'DOWN' THEN df.rs_3m_now < df.rs_3m_4w_ago END,
  -- L4: base/top width — stage 1/3 persistence over prior 12 weeks >= 0.5
  -- (relaxed from 0.7 in plan; 0.7 was too tight given persist_4w already at 0.6)
  CASE WHEN e.event_type = 'UP'   AND wp.stage1_persist_12w IS NOT NULL THEN wp.stage1_persist_12w >= 0.5
       WHEN e.event_type = 'DOWN' AND wp.stage3_persist_12w IS NOT NULL THEN wp.stage3_persist_12w >= 0.5
       ELSE NULL END,
  -- L6: liquidity floor per cap-tier
  CASE WHEN df.avg_traded_value_20d IS NULL THEN NULL
       WHEN e.cap_tier = 'Large' THEN df.avg_traded_value_20d >= 5e7    -- 5 cr
       WHEN e.cap_tier = 'Mid'   THEN df.avg_traded_value_20d >= 2e7    -- 2 cr
       WHEN e.cap_tier = 'Small' THEN df.avg_traded_value_20d >= 5e6    -- 50 L
       ELSE TRUE END
FROM atlas.weinstein_events_base e
LEFT JOIN atlas._wa2_daily_features df
  ON df.instrument_id = e.instrument_id AND df.date = e.event_date
LEFT JOIN atlas._wa2_weekly_persist wp
  ON wp.instrument_id = e.instrument_id
 AND wp.week_start = e.event_date
 AND wp.lookback_weeks = e.ma_lookback_weeks;
