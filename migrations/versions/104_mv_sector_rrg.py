"""v6 — mv_sector_rrg materialized view (Page 04 Sectors — Relative Rotation Graph).

# allow-large: SQL body is a 6-CTE chain with window functions + LATERAL for trail assembly

Marker migration. The MV is APPLIED via Supabase MCP execute_sql against
live atlas-os project nanvgbhootvvthjujkvs.
Mac psycopg2 hangs against Supabase (existing memory entry reference_ec2_access),
so Alembic CLI is not usable from local Mac; MCP execute_sql is the working write path.

MV: atlas.mv_sector_rrg
Row shape: ONE row per (as_of_date, sector_name).
Latest as_of_date serves Page 04 Sectors — RRG 4-quadrant visualization.
Historical rows support time-travel.
~31 sectors × ~1,550 trading days (2020-01-01+) ≈ 48,050 rows.

Sections served:
  - RRG chart: rs_ratio_current (X), rs_momentum_current (Y), quadrant_current
    Plot today's dot for each sector in the 4-quadrant plane.
  - 6-week trail (trajectory): trail_6w JSONB — array of up to 6 weekly snapshots
    {week_end_date, rs_ratio, rs_momentum, quadrant}, oldest-first, for the
    trailing path on the RRG chart.

Quadrant definitions:
  Leading   — rs_ratio >= 100 AND rs_momentum >= 0  (top-right, strong + improving)
  Improving — rs_ratio <  100 AND rs_momentum >= 0  (top-left, recovering)
  Lagging   — rs_ratio <  100 AND rs_momentum <  0  (bottom-left, weak + weakening)
  Weakening — rs_ratio >= 100 AND rs_momentum <  0  (bottom-right, fading)
  NULL when either rs_ratio or rs_momentum is NULL

Formulas:
  rs_ratio    = 100 + (bottomup_rs_3m_nifty500 * 100)
                  → 0% RS vs Nifty 500 → 100.0 (parity)
                  → +5% RS → 105.0, −5% RS → 95.0
  rs_momentum = rs_ratio_today − rs_ratio_20_trading_days_ago
                  → approximates 4-week rate-of-change of relative strength
                  → positive = RS accelerating, negative = RS decelerating
                  → NULL for first 20 rows per sector (LAG window not available)

Trail (6-week):
  "Weekly" = every 5th trading-day row per sector (descending date order), rows
  1, 6, 11, 16, 21, 26. Gives today + 5 prior weekly snapshots.
  Assembled via LATERAL: for each (as_of_date, sector_name), pick up to 6
  most-recent weekly-anchor rows with date <= as_of_date.

Source tables:
  atlas.atlas_sector_metrics_daily — bottomup_rs_3m_nifty500 (74,752 rows,
    2020+ filtered to ~48,050 rows; 31 sectors × ~1,550 trading days)

Column notes:
  bottomup_rs_3m_nifty500: decimal fraction (0.05 = +5%), NULLable before
    M3 backfill. NULL propagated to rs_ratio, rs_momentum, quadrant_current.
  rs_ratio: 4-decimal precision (ROUND to 4dp).
  rs_momentum: difference in rs_ratio points (ROUND to 4dp).
    Not a percentage — raw difference for chart scaling.
  quadrant_current: VARCHAR — 'Leading'/'Improving'/'Lagging'/'Weakening'/NULL
  trail_6w: JSONB array, up to 6 elements, oldest-first.
    Each element: {week_end_date (ISO date string), rs_ratio, rs_momentum,
    quadrant}. Fewer than 6 elements is valid (sparse early data or new sector).

Data gaps (NULL propagated — never zeroed):
  bottomup_rs_3m_nifty500: NULL before M3 backfill → rs_ratio NULL throughout
  rs_momentum: NULL for first 20 trading days per sector (LAG window)
  trail_6w entries: may have NULL rs_momentum/quadrant in early dates

Refresh: pg_cron 'mv_sector_rrg_nightly' at 20:50 IST (15:20 UTC) daily.
CONCURRENTLY after first full build. Unique index on (as_of_date, sector_name) required.

Design doc: docs/v6/mvs/2026-05-27-mv-sector-rrg-design.md

Revision ID: 104
Revises: 103
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "104"
down_revision = "103"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# MV body — full SQL
# ---------------------------------------------------------------------------
_CREATE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_sector_rrg AS
WITH

-- ============================================================
-- 1. Date + sector spine — from atlas_sector_metrics_daily
--    (74,752 rows; 31 sectors × 2,412 trading days; filtered to 2020+)
--    ~48,050 rows post-filter.
-- ============================================================
spine AS (
  SELECT DISTINCT date AS as_of_date, sector_name
  FROM atlas.atlas_sector_metrics_daily
  WHERE date >= '2020-01-01'
),

-- ============================================================
-- 2. Raw RS series — bottomup_rs_3m_nifty500 → rs_ratio
--    rs_ratio = 100 + (bottomup_rs_3m_nifty500 * 100)
--    Parity (0% RS vs Nifty 500) → 100.0
--    +5% RS → 105.0, −5% RS → 95.0
--    NULL bottomup_rs_3m_nifty500 → NULL rs_ratio (never zeroed).
-- ============================================================
raw_rs AS (
  SELECT
    date,
    sector_name,
    bottomup_rs_3m_nifty500,
    CASE
      WHEN bottomup_rs_3m_nifty500 IS NOT NULL
      THEN ROUND((100 + bottomup_rs_3m_nifty500 * 100)::numeric, 4)
      ELSE NULL
    END AS rs_ratio
  FROM atlas.atlas_sector_metrics_daily
  WHERE date >= '2020-01-01'
),

-- ============================================================
-- 3. RS with momentum — LAG(rs_ratio, 20) approximates 4-week change
--    rs_momentum = rs_ratio_today − rs_ratio_20_trading_days_ago
--    NULL for first 20 rows per sector (LAG window not available).
--    NULL when either value is NULL (data gap).
--    Quadrant assigned inline via CASE.
-- ============================================================
with_momentum AS (
  SELECT
    date,
    sector_name,
    rs_ratio,
    CASE
      WHEN rs_ratio IS NOT NULL
        AND LAG(rs_ratio, 20) OVER (
          PARTITION BY sector_name ORDER BY date ASC
        ) IS NOT NULL
      THEN ROUND(
        (rs_ratio - LAG(rs_ratio, 20) OVER (
          PARTITION BY sector_name ORDER BY date ASC
        ))::numeric,
        4
      )
      ELSE NULL
    END AS rs_momentum,
    CASE
      WHEN rs_ratio IS NULL OR LAG(rs_ratio, 20) OVER (
        PARTITION BY sector_name ORDER BY date ASC
      ) IS NULL
        THEN NULL
      WHEN rs_ratio >= 100 AND (rs_ratio - LAG(rs_ratio, 20) OVER (
        PARTITION BY sector_name ORDER BY date ASC
      )) >= 0
        THEN 'Leading'
      WHEN rs_ratio < 100 AND (rs_ratio - LAG(rs_ratio, 20) OVER (
        PARTITION BY sector_name ORDER BY date ASC
      )) >= 0
        THEN 'Improving'
      WHEN rs_ratio < 100 AND (rs_ratio - LAG(rs_ratio, 20) OVER (
        PARTITION BY sector_name ORDER BY date ASC
      )) < 0
        THEN 'Lagging'
      WHEN rs_ratio >= 100 AND (rs_ratio - LAG(rs_ratio, 20) OVER (
        PARTITION BY sector_name ORDER BY date ASC
      )) < 0
        THEN 'Weakening'
      ELSE NULL
    END AS quadrant
  FROM raw_rs
),

-- ============================================================
-- 4. Weekly anchor rows — every 5th row per sector (descending date)
--    ROW_NUMBER() descending → rows 1, 6, 11, 16, 21, 26 are
--    the most-recent date + 5 prior weekly snapshots.
--    row_num MOD 5 = 1 selects those anchors.
--    These are the candidate rows for the 6-week trail.
-- ============================================================
weekly_anchors AS (
  SELECT
    date,
    sector_name,
    rs_ratio,
    rs_momentum,
    quadrant,
    ROW_NUMBER() OVER (
      PARTITION BY sector_name ORDER BY date DESC
    ) AS rn_desc
  FROM with_momentum
),

-- ============================================================
-- 5. Filter to weekly anchor dates only (every 5th row descending)
--    rn_desc MOD 5 = 1 → rows 1, 6, 11, 16, 21, 26, ...
-- ============================================================
weekly_filtered AS (
  SELECT date, sector_name, rs_ratio, rs_momentum, quadrant
  FROM weekly_anchors
  WHERE rn_desc % 5 = 1
)

-- ============================================================
-- 6. FINAL SELECT — one row per (as_of_date, sector_name)
--    Current scalars from with_momentum.
--    trail_6w assembled via LATERAL: for each row's as_of_date,
--    pick up to 6 most-recent weekly_filtered entries with date <= as_of_date,
--    aggregated as a JSONB array (oldest-first).
-- ============================================================
SELECT
  s.as_of_date,
  s.sector_name,

  -- ---- Current RRG scalars ----
  wm.rs_ratio       AS rs_ratio_current,
  wm.rs_momentum    AS rs_momentum_current,
  wm.quadrant       AS quadrant_current,

  -- ---- 6-week trail — JSONB array, oldest-first, up to 6 elements ----
  trail.trail_6w,

  -- ---- Metadata ----
  NOW()             AS refreshed_at

FROM spine s

-- Join current-date scalars
LEFT JOIN with_momentum wm
  ON wm.date = s.as_of_date AND wm.sector_name = s.sector_name

-- LATERAL: assemble the 6-week trail for each (as_of_date, sector_name)
-- Picks up to 6 most-recent weekly anchors on or before as_of_date,
-- then sorts ascending to produce oldest-first trail.
LEFT JOIN LATERAL (
  SELECT
    COALESCE(
      (
        SELECT jsonb_agg(
          jsonb_build_object(
            'week_end_date', sub.date::text,
            'rs_ratio',      sub.rs_ratio,
            'rs_momentum',   sub.rs_momentum,
            'quadrant',      sub.quadrant
          )
          ORDER BY sub.date ASC
        )
        FROM (
          SELECT wf.date, wf.rs_ratio, wf.rs_momentum, wf.quadrant
          FROM weekly_filtered wf
          WHERE wf.sector_name = s.sector_name
            AND wf.date <= s.as_of_date
          ORDER BY wf.date DESC
          LIMIT 6
        ) sub
      ),
      '[]'::jsonb
    ) AS trail_6w
) trail ON true

WITH NO DATA;
"""

_CREATE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX uix_mv_sector_rrg_date_sector
  ON atlas.mv_sector_rrg (as_of_date, sector_name);
"""

_REFRESH_MV = """
REFRESH MATERIALIZED VIEW atlas.mv_sector_rrg;
"""

_CRON_SCHEDULE = """
SELECT cron.schedule(
  'mv_sector_rrg_nightly',
  '20 15 * * *',
  $$ REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_rrg; $$
);
"""

_CRON_UNSCHEDULE = "SELECT cron.unschedule('mv_sector_rrg_nightly');"

_DROP_UNIQUE_INDEX = "DROP INDEX IF EXISTS atlas.uix_mv_sector_rrg_date_sector;"

_DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_sector_rrg CASCADE;"


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
