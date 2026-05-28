-- scripts/research/weinstein_event_ic.sql
-- Task 4 of Stream A2 — forward 6m IC per (cap_tier × lookback × event_type × confluence-subset)
-- (docs/superpowers/plans/2026-05-28-trader-view-A2-weinstein-deep-dive.md)
--
-- Confluence subsets tested (12 total):
--   S01 base alone
--   S02 +L1 (volume)        S03 +L2 (prior extreme)    S04 +L3 (RS trend)
--   S05 +L4 (base width)    S06 +L6 (liquidity)
--   S07 +L1+L2              S08 +L1+L3                 S09 +L2+L3
--   S10 +L1+L2+L3           S11 +L1+L2+L3+L4           S12 +L1+L2+L3+L4+L6
--
-- IC interpretation:
--   Spearman CORR between (subset indicator 0/1) and percent_rank(forward_excess_6m)
--   - For UP events: ic > 0 means "pass selects high-return events" (good signal)
--   - For DOWN events: ic < 0 means "pass selects LOW-return events" (good SELL signal)
--   - Signed useful IC := ic for UP, -ic for DOWN. Floor 0.05.
--
-- Output table: atlas.weinstein_a2_ic_results (288 rows = 12 subsets × 3 caps × 4 lookbacks × 2 types)
-- CSV: docs/v6/2026-05-28-weinstein-a2-ic-results.csv

-- Step 1: add forward_excess_6m column on the features table
-- (ALTER requires destructive markers)
ALTER TABLE atlas.weinstein_event_features ADD COLUMN forward_excess_6m numeric;

-- Step 2: populate forward_excess_6m
WITH nifty AS (
  SELECT date, close AS idx_close FROM public.de_index_prices
  WHERE index_code = 'NIFTY 500' AND date >= '2017-06-01'
),
fr AS (
  SELECT
    e.instrument_id, e.event_date, e.event_type, e.ma_lookback_weeks,
    (p_fwd.close_adj / NULLIF(p_now.close_adj, 0) - 1)
      - (n_fwd.idx_close / NULLIF(n_now.idx_close, 0) - 1) AS excess_6m
  FROM atlas.weinstein_event_features e
  LEFT JOIN public.de_equity_ohlcv p_now
    ON p_now.instrument_id = e.instrument_id AND p_now.date = e.event_date
  LEFT JOIN public.de_equity_ohlcv p_fwd
    ON p_fwd.instrument_id = e.instrument_id AND p_fwd.date = e.event_date + INTERVAL '130 days'
  LEFT JOIN nifty n_now ON n_now.date = e.event_date
  LEFT JOIN nifty n_fwd ON n_fwd.date = e.event_date + INTERVAL '130 days'
  WHERE e.event_date <= CURRENT_DATE - INTERVAL '130 days'
)
UPDATE atlas.weinstein_event_features f
SET forward_excess_6m = fr.excess_6m
FROM fr
WHERE f.instrument_id = fr.instrument_id
  AND f.event_date    = fr.event_date
  AND f.event_type    = fr.event_type
  AND f.ma_lookback_weeks = fr.ma_lookback_weeks
  AND fr.excess_6m IS NOT NULL;

-- Step 3: create results table
CREATE TABLE atlas.weinstein_a2_ic_results (
  cap_tier text NOT NULL,
  ma_lookback_weeks int NOT NULL,
  event_type text NOT NULL,
  subset_id text NOT NULL,
  n_all int,
  n_pass int,
  events_per_year numeric,
  hit_rate numeric,
  mean_excess_pass numeric,
  ic_spearman numeric,
  PRIMARY KEY (cap_tier, ma_lookback_weeks, event_type, subset_id)
);

-- Step 4: populate IC results
INSERT INTO atlas.weinstein_a2_ic_results
  (cap_tier, ma_lookback_weeks, event_type, subset_id, n_all, n_pass, events_per_year, hit_rate, mean_excess_pass, ic_spearman)
WITH ranked AS (
  SELECT
    cap_tier, ma_lookback_weeks, event_type,
    conf_l1_volume, conf_l2_prior_extreme, conf_l3_rs_trend, conf_l4_base_width, conf_l6_liquidity,
    forward_excess_6m,
    PERCENT_RANK() OVER (PARTITION BY cap_tier, ma_lookback_weeks, event_type ORDER BY forward_excess_6m) AS rk_fwd
  FROM atlas.weinstein_event_features
  WHERE forward_excess_6m IS NOT NULL
),
expanded AS (
  SELECT *,
    1 AS ind_s1,
    CASE WHEN conf_l1_volume IS TRUE THEN 1 ELSE 0 END AS ind_s2,
    CASE WHEN conf_l2_prior_extreme IS TRUE THEN 1 ELSE 0 END AS ind_s3,
    CASE WHEN conf_l3_rs_trend IS TRUE THEN 1 ELSE 0 END AS ind_s4,
    CASE WHEN conf_l4_base_width IS TRUE THEN 1 ELSE 0 END AS ind_s5,
    CASE WHEN conf_l6_liquidity IS TRUE THEN 1 ELSE 0 END AS ind_s6,
    CASE WHEN conf_l1_volume IS TRUE AND conf_l2_prior_extreme IS TRUE THEN 1 ELSE 0 END AS ind_s7,
    CASE WHEN conf_l1_volume IS TRUE AND conf_l3_rs_trend IS TRUE THEN 1 ELSE 0 END AS ind_s8,
    CASE WHEN conf_l2_prior_extreme IS TRUE AND conf_l3_rs_trend IS TRUE THEN 1 ELSE 0 END AS ind_s9,
    CASE WHEN conf_l1_volume IS TRUE AND conf_l2_prior_extreme IS TRUE AND conf_l3_rs_trend IS TRUE THEN 1 ELSE 0 END AS ind_s10,
    CASE WHEN conf_l1_volume IS TRUE AND conf_l2_prior_extreme IS TRUE AND conf_l3_rs_trend IS TRUE AND conf_l4_base_width IS TRUE THEN 1 ELSE 0 END AS ind_s11,
    CASE WHEN conf_l1_volume IS TRUE AND conf_l2_prior_extreme IS TRUE AND conf_l3_rs_trend IS TRUE AND conf_l4_base_width IS TRUE AND conf_l6_liquidity IS TRUE THEN 1 ELSE 0 END AS ind_s12
  FROM ranked
),
melted AS (
  SELECT cap_tier, ma_lookback_weeks, event_type, forward_excess_6m, rk_fwd,
         UNNEST(ARRAY['S01_base','S02_+L1','S03_+L2','S04_+L3','S05_+L4','S06_+L6','S07_+L1+L2','S08_+L1+L3','S09_+L2+L3','S10_+L1+L2+L3','S11_+L1+L2+L3+L4','S12_+L1+L2+L3+L4+L6']) AS subset_id,
         UNNEST(ARRAY[ind_s1,ind_s2,ind_s3,ind_s4,ind_s5,ind_s6,ind_s7,ind_s8,ind_s9,ind_s10,ind_s11,ind_s12]) AS ind
  FROM expanded
)
SELECT
  cap_tier, ma_lookback_weeks, event_type, subset_id,
  COUNT(*) AS n_all,
  SUM(ind) AS n_pass,
  ROUND(SUM(ind)/8.0, 1) AS events_per_year,
  AVG(CASE WHEN ind=1 AND ((event_type='UP' AND forward_excess_6m>0) OR (event_type='DOWN' AND forward_excess_6m<0)) THEN 1.0 ELSE 0.0 END) /
    NULLIF(AVG(ind::numeric), 0) AS hit_rate,
  AVG(CASE WHEN ind=1 THEN forward_excess_6m END) AS mean_excess_pass,
  CORR(ind::numeric, rk_fwd) AS ic_spearman
FROM melted
GROUP BY 1,2,3,4;

-- Step 5: ranked winners query (no INSERT, ad-hoc inspection)
-- Floor: signed_useful_ic >= 0.05 AND events_per_year >= 50 AND hit_rate >= 0.60
-- WITH ranked AS (
--   SELECT *,
--     CASE WHEN event_type='UP' THEN ic_spearman ELSE -ic_spearman END AS signed_useful_ic
--   FROM atlas.weinstein_a2_ic_results
--   WHERE ic_spearman IS NOT NULL
-- )
-- SELECT cap_tier, ma_lookback_weeks, event_type, subset_id, n_pass, events_per_year,
--        ROUND(hit_rate::numeric, 3) AS hit_rate, ROUND(ic_spearman::numeric, 4) AS ic_raw,
--        ROUND(signed_useful_ic::numeric, 4) AS ic_signed
-- FROM ranked
-- WHERE signed_useful_ic >= 0.05 AND events_per_year >= 30 AND hit_rate >= 0.55
-- ORDER BY cap_tier, event_type, signed_useful_ic DESC;
