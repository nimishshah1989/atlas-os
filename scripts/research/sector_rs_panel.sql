-- Stream A3 Task 1 — sector RS rank daily panel
-- Source: atlas.atlas_sector_metrics_daily.bottomup_rs_3m_nifty500
-- Window: 2018-01-01+ (matches Stream A2 event window)
-- Coverage check (2026-05-28): 2,401 distinct days, 30 sectors, ~69k rows
-- Used by Stream A3 Task 2 (L5 boolean per event)

CREATE OR REPLACE VIEW atlas.v_sector_rs_rank_daily AS
SELECT
  date,
  sector_name,
  bottomup_rs_3m_nifty500 AS rs_3m,
  RANK() OVER (PARTITION BY date ORDER BY bottomup_rs_3m_nifty500 DESC NULLS LAST) AS rs_rank,
  COUNT(*) OVER (PARTITION BY date) AS n_sectors_today,
  PERCENT_RANK() OVER (PARTITION BY date ORDER BY bottomup_rs_3m_nifty500 NULLS FIRST) AS rs_pctile
FROM atlas.atlas_sector_metrics_daily
WHERE bottomup_rs_3m_nifty500 IS NOT NULL
  AND date >= '2018-01-01';
