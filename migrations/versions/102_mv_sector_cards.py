"""v6 — mv_sector_cards materialized view (Page 04 Sectors).

# allow-large: SQL body is a 15-column CTE chain covering 6 source tables

Marker migration. The MV is APPLIED via Supabase MCP execute_sql against
live atlas-os project nanvgbhootvvthjujkvs.
Mac psycopg2 hangs against Supabase (existing memory entry reference_ec2_access),
so Alembic CLI is not usable from local Mac; MCP execute_sql is the working write path.

MV: atlas.mv_sector_cards
Row shape: ONE row per (as_of_date, sector_name).
Latest as_of_date serves Page 04 Sectors; historical rows support time-travel.
~31 sectors × ~1,550 trading days (2020-01-01+) ≈ 48,050 rows.

Sections served:
  - Heatmap table (15 columns per sector):
      sector_name, constituent_count
      ret_1w, ret_1m, ret_3m, ret_6m, ret_12m
      rs_1m, rs_3m, rs_6m
      vol_60d_ann, pct_above_ema20, pct_above_ema200, pct_at_52wh
      hhi_concentration
      buy_signal_count, confidence_distribution (JSONB {"H":n,"M":n,"L":n})
      verdict, verdict_abbr
  - Hero readout (Leading / Lagging / Rotation):
      All data computable from scalar columns above.

Source tables:
  atlas.atlas_sector_metrics_daily     — 74,752 rows, bottomup_ret_* + rs_* + breadth cols
  atlas.atlas_sector_states_daily      — 74,752 rows, sector_state (Overweight/Neutral/Underweight)
  atlas.atlas_signal_calls             — 363 rows,  action + confidence_unconditional + exit_date
  atlas.atlas_universe_stocks          — 750 rows,  instrument_id → sector mapping
  atlas.atlas_stock_metrics_daily      — large,     realized_vol_63 per stock per date
  atlas.atlas_index_metrics_daily      — for nifty500_ret_1w and ret_12m to back-derive sector abs returns

Column notes:
  ret_1w  = rs_1w  + nifty500_ret_1w   (rs_1w added migration 097; rs = sector_ret - nifty500_ret)
  ret_12m = rs_12m + nifty500_ret_12m  (rs_12m added migration 097)
  ret_1m / ret_3m / ret_6m: direct from bottomup_ret_1m/3m/6m
  rs_1m / rs_6m: direct from atlas_sector_metrics_daily.rs_1m / rs_6m (migration 097)
  rs_3m:  from atlas_sector_metrics_daily.bottomup_rs_3m_nifty500 (original column)
  vol_60d_ann: AVG(atlas_stock_metrics_daily.realized_vol_63) per sector per date
  buy_signal_count: COUNT of POSITIVE action + exit_date IS NULL signals per sector ON that date
  confidence H/M/L: confidence_unconditional >= 0.70 / 0.50-0.70 / < 0.50

Data gaps (NULL propagated — never zeroed):
  rs_1w / rs_6m / rs_12m: NULL before migration 097 backfill date
  pct_above_ema20 / pct_above_ema200 / pct_at_52wh: NULL before backfill
  hhi_concentration: NULL before backfill
  vol_60d_ann: NULL if no stock_metrics_daily rows for that sector+date

Signal join note:
  atlas_signal_calls has no sector_name column. Join path:
  signal_calls.instrument_id → atlas_universe_stocks.instrument_id
    WHERE effective_to IS NULL → atlas_universe_stocks.sector
  Buy signals are matched to the date they were triggered (sc.date = as_of_date).
  Only POSITIVE action + exit_date IS NULL on that date (open signals triggered that day).
  This under-counts active signals on non-trigger dates; for a daily MV this is the
  cleanest pattern without a full range-join on 363 × 48,050 rows.

Refresh: pg_cron 'mv_sector_cards_nightly' at 20:40 IST (14:40 UTC) daily.
CONCURRENTLY after first full build. Unique index on (as_of_date, sector_name) required.

Design doc: docs/v6/mvs/2026-05-27-mv-sector-cards-design.md

Revision ID: 102
Revises: 101
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# MV body — full SQL
# ---------------------------------------------------------------------------
_CREATE_MV = """
CREATE MATERIALIZED VIEW atlas.mv_sector_cards AS
WITH

-- ============================================================
-- 1. Date + sector spine — from atlas_sector_metrics_daily
--    (74,752 rows; 31 sectors × 2,412 trading days; filtered to 2020+)
-- ============================================================
spine AS (
  SELECT DISTINCT date AS as_of_date, sector_name
  FROM atlas.atlas_sector_metrics_daily
  WHERE date >= '2020-01-01'
),

-- ============================================================
-- 2. Sector metrics — direct scalar columns
--    bottomup_ret_1m/3m/6m + rs_1w/1m/6m/12m + breadth + hhi
-- ============================================================
metrics AS (
  SELECT
    smd.date                           AS as_of_date,
    smd.sector_name,
    -- Absolute returns (available columns)
    smd.bottomup_ret_1m                AS ret_1m,
    smd.bottomup_ret_3m                AS ret_3m,
    smd.bottomup_ret_6m                AS ret_6m,
    smd.bottomup_ret_12m,              -- A4: true 12m (direct), not back-derived
    -- RS columns (added migration 097)
    smd.rs_1w,
    smd.rs_1m,
    smd.bottomup_rs_3m_nifty500        AS rs_3m,
    smd.rs_6m,
    smd.rs_12m,
    -- Breadth (EMA21 = canonical, A1)
    smd.pct_above_ema21,
    smd.pct_above_ema200,
    smd.pct_52wh                       AS pct_at_52wh,
    smd.hhi                            AS hhi_concentration
  FROM atlas.atlas_sector_metrics_daily smd
  WHERE smd.date >= '2020-01-01'
),

-- ============================================================
-- 3. Nifty 500 returns — needed to back-derive sector absolute
--    1W and 12M returns from RS values:
--      sector_ret_1w  = rs_1w  + nifty500_ret_1w
--      sector_ret_12m = rs_12m + nifty500_ret_12m
-- ============================================================
n500_rets AS (
  SELECT
    date,
    ret_1w    AS n500_ret_1w,
    ret_12m   AS n500_ret_12m
  FROM atlas.atlas_index_metrics_daily
  WHERE index_code = 'NIFTY 500'
    AND date >= '2020-01-01'
),

-- ============================================================
-- 4. Sector states — verdict
-- ============================================================
states AS (
  SELECT
    date                              AS as_of_date,
    sector_name,
    sector_state
  FROM atlas.atlas_sector_states_daily
  WHERE date >= '2020-01-01'
),

-- ============================================================
-- 5. Constituent count — live snapshot per sector
--    (effective_to IS NULL = current universe member)
--    NOTE: count is static (current snapshot), not historical.
--    This is correct for the current sector cards view.
-- ============================================================
constituent_counts AS (
  SELECT
    sector                            AS sector_name,
    COUNT(DISTINCT instrument_id)     AS constituent_count
  FROM atlas.atlas_universe_stocks
  WHERE effective_to IS NULL
  GROUP BY sector
),

-- ============================================================
-- 6. Vol 60d annualised — average of stock realized_vol_63
--    per sector per date (from atlas_stock_metrics_daily).
--    realized_vol_63 = annualised 63-day realised vol (std*sqrt(252)).
--    AVG ignores NULLs — result is NULL if all stocks lack vol data.
-- ============================================================
stock_vol AS (
  SELECT
    u.sector                          AS sector_name,
    smd.date                          AS as_of_date,
    AVG(smd.realized_vol_63)          AS vol_60d_ann
  FROM atlas.atlas_stock_metrics_daily smd
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = smd.instrument_id
   AND u.effective_to IS NULL
  WHERE smd.date >= '2020-01-01'
    AND smd.realized_vol_63 IS NOT NULL
  GROUP BY u.sector, smd.date
),

-- ============================================================
-- 7. BUY signal counts per sector per trigger date.
--    Join path: signal_calls → universe_stocks (sector mapping).
--    We match on sc.date = as_of_date (signals triggered that day).
--    Only POSITIVE action (BUY) + exit_date IS NULL (open signals).
--    Confidence bands:
--      H = confidence_unconditional >= 0.70
--      M = confidence_unconditional >= 0.50 AND < 0.70
--      L = confidence_unconditional < 0.50
-- ============================================================
signal_agg AS (
  SELECT
    u.sector                          AS sector_name,
    sc.date                           AS as_of_date,
    COUNT(sc.signal_call_id)          AS buy_signal_count,
    COUNT(CASE WHEN sc.confidence_unconditional >= 0.70 THEN 1 END) AS conf_h,
    COUNT(CASE WHEN sc.confidence_unconditional >= 0.50
               AND  sc.confidence_unconditional <  0.70 THEN 1 END) AS conf_m,
    COUNT(CASE WHEN sc.confidence_unconditional <  0.50 THEN 1 END) AS conf_l
  FROM atlas.atlas_signal_calls sc
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = sc.instrument_id
   AND u.effective_to IS NULL
  WHERE sc.action = 'POSITIVE'
    AND sc.exit_date IS NULL
    AND sc.date >= '2020-01-01'
  GROUP BY u.sector, sc.date
)

-- ============================================================
-- 8. FINAL SELECT — one row per (as_of_date, sector_name)
-- ============================================================
SELECT
  s.as_of_date,
  s.sector_name,

  -- ---- Constituent count (current snapshot) ----
  COALESCE(cc.constituent_count, 0)                          AS constituent_count,

  -- ---- Absolute returns ----
  -- ret_1w: back-derived from rs_1w + nifty500_ret_1w
  CASE
    WHEN m.rs_1w IS NOT NULL AND nr.n500_ret_1w IS NOT NULL
    THEN ROUND((m.rs_1w + nr.n500_ret_1w)::numeric, 4)
    ELSE NULL
  END                                                         AS ret_1w,
  ROUND(m.ret_1m::numeric,  4)                               AS ret_1m,
  ROUND(m.ret_3m::numeric,  4)                               AS ret_3m,
  ROUND(m.ret_6m::numeric,  4)                               AS ret_6m,
  -- ret_12m: true bottom-up 12m (A4); fall back to rs_12m + nifty500_ret_12m only
  -- when the stored 12m is absent (pre-backfill rows).
  COALESCE(
    ROUND(m.bottomup_ret_12m::numeric, 4),
    CASE
      WHEN m.rs_12m IS NOT NULL AND nr.n500_ret_12m IS NOT NULL
      THEN ROUND((m.rs_12m + nr.n500_ret_12m)::numeric, 4)
      ELSE NULL
    END
  )                                                           AS ret_12m,

  -- ---- RS vs Nifty 500 ----
  ROUND(m.rs_1m::numeric,   4)                               AS rs_1m,
  ROUND(m.rs_3m::numeric,   4)                               AS rs_3m,
  ROUND(m.rs_6m::numeric,   4)                               AS rs_6m,

  -- ---- Risk / breadth ----
  ROUND(sv.vol_60d_ann::numeric, 4)                          AS vol_60d_ann,
  ROUND(m.pct_above_ema21::numeric,  4)                      AS pct_above_ema21,
  ROUND(m.pct_above_ema200::numeric, 4)                      AS pct_above_ema200,
  ROUND(m.pct_at_52wh::numeric,      4)                      AS pct_at_52wh,
  ROUND(m.hhi_concentration::numeric, 4)                     AS hhi_concentration,

  -- ---- Signal counts ----
  COALESCE(sg.buy_signal_count, 0)                           AS buy_signal_count,
  jsonb_build_object(
    'H', COALESCE(sg.conf_h, 0),
    'M', COALESCE(sg.conf_m, 0),
    'L', COALESCE(sg.conf_l, 0)
  )                                                           AS confidence_distribution,

  -- ---- Verdict ----
  st.sector_state                                             AS verdict,
  CASE st.sector_state
    WHEN 'Overweight'             THEN 'OW'
    WHEN 'Neutral'                THEN 'NW'
    WHEN 'Underweight'            THEN 'UW'
    WHEN 'Avoid'                  THEN 'UW'
    WHEN 'DISLOCATION_SUSPENDED'  THEN 'NW'
    ELSE NULL
  END                                                         AS verdict_abbr,

  -- ---- Metadata ----
  NOW()                                                       AS refreshed_at

FROM spine s
-- Sector metrics (returns, RS, breadth, concentration)
LEFT JOIN metrics m
  ON m.as_of_date = s.as_of_date AND m.sector_name = s.sector_name
-- Nifty 500 returns for back-deriving sector 1W / 12M abs returns
LEFT JOIN n500_rets nr
  ON nr.date = s.as_of_date
-- Sector states (verdict)
LEFT JOIN states st
  ON st.as_of_date = s.as_of_date AND st.sector_name = s.sector_name
-- Constituent count (static current snapshot)
LEFT JOIN constituent_counts cc
  ON cc.sector_name = s.sector_name
-- Vol 60d annualised
LEFT JOIN stock_vol sv
  ON sv.as_of_date = s.as_of_date AND sv.sector_name = s.sector_name
-- Signal aggregation
LEFT JOIN signal_agg sg
  ON sg.as_of_date = s.as_of_date AND sg.sector_name = s.sector_name

WITH NO DATA;
"""

_CREATE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX uix_mv_sector_cards_date_sector
  ON atlas.mv_sector_cards (as_of_date, sector_name);
"""

_REFRESH_MV = """
REFRESH MATERIALIZED VIEW atlas.mv_sector_cards;
"""

_CRON_SCHEDULE = """
SELECT cron.schedule(
  'mv_sector_cards_nightly',
  '40 14 * * *',
  $$ REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_cards; $$
);
"""

_CRON_UNSCHEDULE = "SELECT cron.unschedule('mv_sector_cards_nightly');"

_DROP_UNIQUE_INDEX = "DROP INDEX IF EXISTS atlas.uix_mv_sector_cards_date_sector;"

_DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_sector_cards CASCADE;"


def upgrade() -> None:
    """Create MV, unique index, do initial full refresh, schedule nightly cron."""
    op.execute(_CREATE_MV)
    op.execute(_CREATE_UNIQUE_INDEX)
    op.execute(_REFRESH_MV)
    op.execute(_CRON_SCHEDULE)


def downgrade() -> None:
    """Drop cron job + MV in dependency-safe order."""
    op.execute(_CRON_UNSCHEDULE)
    op.execute(_DROP_UNIQUE_INDEX)
    op.execute(_DROP_MV)
