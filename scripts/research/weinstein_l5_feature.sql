-- Stream A3 Task 2 — L5 sector confluence boolean per Weinstein event
--
-- L5 = "Weinstein rule 6: buy leaders in leading groups"
-- Dual condition (asymmetric across UP/DOWN):
--   UP event:   sector_rs_pctile_now > pctile_4w_ago   AND pctile_now >= 0.50
--               (sector is improving AND sitting in top half)
--   DOWN event: sector_rs_pctile_now < pctile_4w_ago   AND pctile_now <= 0.50
--               (sector is deteriorating AND sitting in bottom half)
--
-- Single-condition (trend OR level alone) was tested as L3 in Stream A2 and didn't move IC.
--
-- Pass-rate sanity (2026-05-28):
--   cap_tier | event | n_with_l5 | pass_rate
--   Large    | DOWN  | 931       | 0.313
--   Large    | UP    | 1055      | 0.240
--   Mid      | DOWN  | 1405      | 0.310
--   Mid      | UP    | 1492      | 0.293
--   Small    | DOWN  | 2249      | 0.290
--   Small    | UP    | 2089      | 0.305
-- All inside the 25-50% target band per the plan.

ALTER TABLE atlas.weinstein_event_features
  ADD COLUMN IF NOT EXISTS conf_l5_sector_rs boolean;

WITH joined AS (
  SELECT
    e.event_date,
    e.instrument_id,
    e.ma_lookback_weeks,
    e.event_type,
    rs_now.rs_pctile  AS sector_pctile_now,
    rs_old.rs_pctile  AS sector_pctile_4w_ago
  FROM atlas.weinstein_event_features e
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = e.instrument_id AND u.effective_to IS NULL
  LEFT JOIN atlas.v_sector_rs_rank_daily rs_now
    ON rs_now.date = e.event_date AND rs_now.sector_name = u.sector
  LEFT JOIN atlas.v_sector_rs_rank_daily rs_old
    ON rs_old.date = e.event_date - INTERVAL '28 days' AND rs_old.sector_name = u.sector
)
UPDATE atlas.weinstein_event_features e
SET conf_l5_sector_rs = CASE
  WHEN e.event_type = 'UP'
    AND j.sector_pctile_now IS NOT NULL
    AND j.sector_pctile_4w_ago IS NOT NULL
    THEN (j.sector_pctile_now > j.sector_pctile_4w_ago AND j.sector_pctile_now >= 0.50)
  WHEN e.event_type = 'DOWN'
    AND j.sector_pctile_now IS NOT NULL
    AND j.sector_pctile_4w_ago IS NOT NULL
    THEN (j.sector_pctile_now < j.sector_pctile_4w_ago AND j.sector_pctile_now <= 0.50)
  ELSE NULL
END
FROM joined j
WHERE e.event_date = j.event_date
  AND e.instrument_id = j.instrument_id
  AND e.ma_lookback_weeks = j.ma_lookback_weeks
  AND e.event_type = j.event_type;
