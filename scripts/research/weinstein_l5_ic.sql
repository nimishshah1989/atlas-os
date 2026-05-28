-- Stream A3 Task 3 — IC + walk-forward with L5 layered on A2 winners
--
-- 6 subsets × 3 cap_tiers × 4 lookbacks × 2 event_types = 144 rows
-- Subsets tested:
--   A2_base       Base alone (A2 baseline restricted to L5-eligible subset)
--   A3_L5         Base + L5
--   A3_L5_L6      Base + L5 + L6 (liquidity)
--   A3_L5_L4      Base + L5 + L4 (base width)
--   A3_L5_L2      Base + L5 + L2 (prior 13W extreme)
--   A3_L5_L2_L4   Base + L5 + L2 + L4
--
-- IC: Spearman per (cap_tier × ma_lookback × event_type) partition
-- Forward return: 130-day calendar excess vs NIFTY 500 (same as A2)
-- Output table: atlas.weinstein_a3_ic_results
-- CSV: docs/v6/2026-05-28-weinstein-a3-ic-results.csv
-- Walk-forward: per-calendar-year IC for each candidate that cleared IC>=0.05 in-sample

-- Step 1: Create the results table
CREATE TABLE IF NOT EXISTS atlas.weinstein_a3_ic_results (
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

-- Step 2: Compute IC for all 144 (cap × lookback × type × subset) cells
INSERT INTO atlas.weinstein_a3_ic_results
  (cap_tier, ma_lookback_weeks, event_type, subset_id, n_all, n_pass, events_per_year, hit_rate, mean_excess_pass, ic_spearman)
WITH ranked AS (
  SELECT
    cap_tier, ma_lookback_weeks, event_type,
    conf_l2_prior_extreme, conf_l4_base_width, conf_l5_sector_rs, conf_l6_liquidity,
    forward_excess_6m,
    PERCENT_RANK() OVER (PARTITION BY cap_tier, ma_lookback_weeks, event_type ORDER BY forward_excess_6m) AS rk_fwd
  FROM atlas.weinstein_event_features
  WHERE forward_excess_6m IS NOT NULL
    AND conf_l5_sector_rs IS NOT NULL
    AND cap_tier <> 'Micro'
),
expanded AS (
  SELECT *,
    1 AS ind_a2_base,
    CASE WHEN conf_l5_sector_rs IS TRUE THEN 1 ELSE 0 END AS ind_a3_l5,
    CASE WHEN conf_l5_sector_rs IS TRUE AND conf_l6_liquidity IS TRUE THEN 1 ELSE 0 END AS ind_a3_l5_l6,
    CASE WHEN conf_l5_sector_rs IS TRUE AND conf_l4_base_width IS TRUE THEN 1 ELSE 0 END AS ind_a3_l5_l4,
    CASE WHEN conf_l5_sector_rs IS TRUE AND conf_l2_prior_extreme IS TRUE THEN 1 ELSE 0 END AS ind_a3_l5_l2,
    CASE WHEN conf_l5_sector_rs IS TRUE AND conf_l2_prior_extreme IS TRUE AND conf_l4_base_width IS TRUE THEN 1 ELSE 0 END AS ind_a3_l5_l2_l4
  FROM ranked
),
melted AS (
  SELECT cap_tier, ma_lookback_weeks, event_type, forward_excess_6m, rk_fwd,
         UNNEST(ARRAY['A2_base','A3_L5','A3_L5_L6','A3_L5_L4','A3_L5_L2','A3_L5_L2_L4']) AS subset_id,
         UNNEST(ARRAY[ind_a2_base, ind_a3_l5, ind_a3_l5_l6, ind_a3_l5_l4, ind_a3_l5_l2, ind_a3_l5_l2_l4]) AS ind
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
GROUP BY 1,2,3,4
ON CONFLICT (cap_tier, ma_lookback_weeks, event_type, subset_id) DO UPDATE
SET n_all = EXCLUDED.n_all,
    n_pass = EXCLUDED.n_pass,
    events_per_year = EXCLUDED.events_per_year,
    hit_rate = EXCLUDED.hit_rate,
    mean_excess_pass = EXCLUDED.mean_excess_pass,
    mean_excess_pass = EXCLUDED.mean_excess_pass,
    ic_spearman = EXCLUDED.ic_spearman;

-- Step 3: Walk-forward per-year IC for top L5 candidates
--   (rules with n_pass >= 50 and signed-IC >= 0.05 only — none cleared, so this is for completeness)
-- Sample query for one rule:
-- WITH ranked AS (
--   SELECT
--     cap_tier, ma_lookback_weeks, event_type, conf_l5_sector_rs,
--     forward_excess_6m, EXTRACT(YEAR FROM event_date)::int AS yr,
--     PERCENT_RANK() OVER (PARTITION BY cap_tier, ma_lookback_weeks, event_type, EXTRACT(YEAR FROM event_date) ORDER BY forward_excess_6m) AS rk_fwd_yr
--   FROM atlas.weinstein_event_features
--   WHERE forward_excess_6m IS NOT NULL AND conf_l5_sector_rs IS NOT NULL AND cap_tier <> 'Micro'
-- )
-- SELECT yr, COUNT(*) FILTER (WHERE conf_l5_sector_rs) AS n_pass,
--        ROUND(CORR((conf_l5_sector_rs)::int::numeric, rk_fwd_yr)::numeric, 4) AS ic_yr
-- FROM ranked
-- WHERE cap_tier='Mid' AND ma_lookback_weeks=5 AND event_type='UP'
-- GROUP BY yr ORDER BY yr;

-- Step 4: Production-gate scan (signed IC >= 0.05 AND events/yr >= 50 AND positive walk-forward min IC)
--   No rule cleared. Closest candidates:
--   - Mid 5W UP A3_L5:   ic=0.0739, n=145, events/yr=18.1, hit=59.3%, walk-forward 6 of 8 yrs positive (min -0.086)
--   - Large 5W UP A3_L5_L6: ic=0.117, n=67, events/yr=8.4, hit=67.2%, walk-forward inconsistent
--   - Large 5W UP A3_L5: ic=0.112, n=70, events/yr=8.8, hit=65.7%, walk-forward inconsistent
-- See docs/v6/2026-05-28-weinstein-a3-report.md for full analysis.
