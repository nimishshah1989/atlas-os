-- scripts/research/weinstein_a2_walk_forward.sql
-- Task 5 of Stream A2 — OOS walk-forward of in-sample winners
-- (docs/superpowers/plans/2026-05-28-trader-view-A2-weinstein-deep-dive.md)
--
-- Approach: For each in-sample winner (cap_tier × event_type × lookback × subset),
-- recompute IC + hit-rate + mean_excess year-by-year (2018..2026). True 3y-train/
-- 1y-test rolling windows would require recalibrating subset thresholds per train
-- window — since our subsets use fixed thresholds (L1@1.5x, L2 prior 13W,
-- L4 persist>=0.5, L6 cap-tier liquidity floors), per-year IC IS the OOS
-- measurement of a locked rule.
--
-- Caveat: S06 (+L6 liquidity) passes ~95% of events in the universe (Nifty 500
-- is already liquid). For many per-year cells the indicator has zero variance
-- and CORR returns NULL. Only S05 (+L4 base width) gives a meaningful within-year
-- filter that we can robustly compute IC on. For S06 winners we still report
-- mean_excess and hit_rate per year — those don't depend on within-year variance.
--
-- Output: atlas.weinstein_a2_walk_forward; CSV docs/v6/2026-05-28-weinstein-a2-walk-forward.csv

CREATE TABLE atlas.weinstein_a2_walk_forward (
  cap_tier text NOT NULL,
  event_type text NOT NULL,
  ma_lookback_weeks int NOT NULL,
  subset_id text NOT NULL,
  test_year int NOT NULL,
  n_pass int,
  hit_rate numeric,
  mean_excess_pass numeric,
  ic_spearman numeric,
  PRIMARY KEY (cap_tier, event_type, ma_lookback_weeks, subset_id, test_year)
);

INSERT INTO atlas.weinstein_a2_walk_forward
  (cap_tier, event_type, ma_lookback_weeks, subset_id, test_year, n_pass, hit_rate, mean_excess_pass, ic_spearman)
WITH winners AS (
  SELECT * FROM (VALUES
    ('Large','DOWN',10,'S06_+L6'),
    ('Large','DOWN',5,'S06_+L6'),
    ('Mid','DOWN',10,'S06_+L6'),
    ('Mid','UP',20,'S06_+L6'),
    ('Small','DOWN',10,'S06_+L6'),
    ('Small','DOWN',10,'S05_+L4'),
    ('Small','UP',30,'S06_+L6')
  ) AS w(cap_tier, event_type, ma_lookback_weeks, subset_id)
),
ranked AS (
  SELECT
    e.cap_tier, e.ma_lookback_weeks, e.event_type, e.event_date,
    e.conf_l4_base_width, e.conf_l6_liquidity,
    e.forward_excess_6m,
    EXTRACT(YEAR FROM e.event_date)::int AS test_year,
    PERCENT_RANK() OVER (PARTITION BY e.cap_tier, e.ma_lookback_weeks, e.event_type, EXTRACT(YEAR FROM e.event_date)
                         ORDER BY e.forward_excess_6m) AS rk_fwd
  FROM atlas.weinstein_event_features e
  WHERE e.forward_excess_6m IS NOT NULL
),
joined AS (
  SELECT r.*, w.subset_id
  FROM ranked r
  JOIN winners w
    ON w.cap_tier = r.cap_tier AND w.event_type = r.event_type
   AND w.ma_lookback_weeks = r.ma_lookback_weeks
),
with_ind AS (
  SELECT *,
    CASE
      WHEN subset_id = 'S05_+L4' AND conf_l4_base_width IS TRUE THEN 1
      WHEN subset_id = 'S06_+L6' AND conf_l6_liquidity IS TRUE THEN 1
      ELSE 0
    END AS ind
  FROM joined
)
SELECT
  cap_tier, event_type, ma_lookback_weeks, subset_id, test_year,
  SUM(ind) AS n_pass,
  AVG(CASE WHEN ind=1 AND ((event_type='UP' AND forward_excess_6m>0) OR (event_type='DOWN' AND forward_excess_6m<0)) THEN 1.0 ELSE 0.0 END) /
    NULLIF(AVG(ind::numeric), 0) AS hit_rate,
  AVG(CASE WHEN ind=1 THEN forward_excess_6m END) AS mean_excess_pass,
  CORR(ind::numeric, rk_fwd) AS ic_spearman
FROM with_ind
GROUP BY 1,2,3,4,5;

-- OOS summary per (rule), only years with valid IC and n_pass >= 10
-- WITH valid AS (
--   SELECT cap_tier, event_type, ma_lookback_weeks, subset_id, test_year, n_pass, hit_rate,
--     CASE WHEN event_type='UP' THEN ic_spearman ELSE -ic_spearman END AS ic_signed
--   FROM atlas.weinstein_a2_walk_forward
--   WHERE ic_spearman IS NOT NULL AND n_pass >= 10
-- )
-- SELECT cap_tier, event_type, ma_lookback_weeks, subset_id,
--   COUNT(*) AS n_years, SUM(n_pass) AS total_n,
--   AVG(hit_rate) AS mean_hit_rate, AVG(ic_signed) AS mean_ic_signed,
--   MIN(ic_signed) AS min_ic_signed, MAX(ic_signed) AS max_ic_signed,
--   STDDEV(ic_signed) AS sd_ic_signed
-- FROM valid GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;
