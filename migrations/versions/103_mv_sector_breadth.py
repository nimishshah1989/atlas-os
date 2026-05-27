"""v6 — mv_sector_breadth materialized view (Page 04 Sectors breadth waterfall).

# allow-large: SQL body is a 7-CTE chain aggregating per-stock returns across 4 windows

Marker migration. The MV is APPLIED via Supabase MCP execute_sql against
live atlas-os project nanvgbhootvvthjujkvs.
Mac psycopg2 hangs against Supabase (existing memory entry reference_ec2_access),
so Alembic CLI is not usable from local Mac; MCP execute_sql is the working write path.

MV: atlas.mv_sector_breadth
Row shape: ONE row per (as_of_date, sector_name).
Latest as_of_date serves Page 04 Sectors breadth waterfall + per-sector breadth cards.
~31 sectors × ~1,550 trading days (2020-01-01+) ≈ 48,050 rows.

Sections served:
  - Breadth waterfall: breadth_by_window JSONB array [{window, pct_positive, pct_top_decile_movers}]
    For 1W / 1M / 3M / 6M lookbacks — % of constituents with positive return and % in top decile.
  - Strength distribution: breadth_by_strength JSONB {very_strong, strong, neutral, weak, very_weak}
    Bucketed by ret_3m quintile within sector on that date.
  - Top/bottom movers: top_movers / bottom_movers JSONB arrays of {symbol, ret_pct} (top 5)
  - EMA breadth scalars: pct_above_ema20, pct_above_ema50, pct_above_ema200, pct_at_52wh
  - constituent_count (current snapshot from atlas_universe_stocks)

Source tables:
  atlas.atlas_sector_metrics_daily     — 74,752 rows, pct_above_ema20/200, participation_50, pct_52wh
  atlas.atlas_universe_stocks          — 750 rows, instrument_id → sector mapping (effective_to IS NULL)
  atlas.atlas_stock_metrics_daily      — large (~1.16M rows in 2020+ range), ret_1w/1m/3m/6m per stock

Column notes:
  pct_above_ema20: direct from atlas_sector_metrics_daily.pct_above_ema20 (fraction 0.0–1.0)
  pct_above_ema50: from atlas_sector_metrics_daily.participation_50 (fraction 0.0–1.0)
  pct_above_ema200: direct from atlas_sector_metrics_daily.pct_above_ema200 (fraction 0.0–1.0)
  pct_at_52wh: from atlas_sector_metrics_daily.pct_52wh (fraction 0.0–1.0)
  breadth_by_window: computed from atlas_stock_metrics_daily ret_1w/1m/3m/6m per stock
    pct_positive = COUNT(ret > 0) / COUNT(ret IS NOT NULL) — NULL if no data
    pct_top_decile_movers = COUNT(rank <= 10th pctile count) / COUNT(ret IS NOT NULL)
  breadth_by_strength: NTILE(5) on ret_3m per (sector, date), NULL ret_3m excluded
  top_movers / bottom_movers: TOP/BOTTOM 5 by ret_1m; fewer than 5 OK for small sectors

Data gaps (NULL propagated — never zeroed):
  pct_above_ema20 / pct_above_ema200 / pct_at_52wh: NULL before migration 097 backfill
  participation_50 (→ pct_above_ema50): NULL before M3 backfill
  breadth_by_window pct_positive: NULL when all stocks have NULL ret_* for that window+date
  breadth_by_strength: NULL or empty when sector has no stocks with non-NULL ret_3m

Refresh: pg_cron 'mv_sector_breadth_nightly' at 20:45 IST (14:45 UTC) daily.
CONCURRENTLY after first full build. Unique index on (as_of_date, sector_name) required.

Design doc: docs/v6/mvs/2026-05-27-mv-sector-breadth-design.md

Revision ID: 103
Revises: 102
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "103"
down_revision = "102"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# MV body — full SQL
# ---------------------------------------------------------------------------
_CREATE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_sector_breadth AS
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
-- 2. Sector-level breadth scalars
--    pct_above_ema20, participation_50 (→ pct_above_ema50),
--    pct_above_ema200, pct_52wh
--    All values are fractions (0.0–1.0), NULLable before backfill.
-- ============================================================
sector_scalars AS (
  SELECT
    date                   AS as_of_date,
    sector_name,
    pct_above_ema20,
    participation_50       AS pct_above_ema50,
    pct_above_ema200,
    pct_52wh               AS pct_at_52wh
  FROM atlas.atlas_sector_metrics_daily
  WHERE date >= '2020-01-01'
),

-- ============================================================
-- 3. Constituent count — live snapshot (current universe)
--    effective_to IS NULL = current member
-- ============================================================
constituent_counts AS (
  SELECT
    sector                 AS sector_name,
    COUNT(DISTINCT instrument_id) AS constituent_count
  FROM atlas.atlas_universe_stocks
  WHERE effective_to IS NULL
  GROUP BY sector
),

-- ============================================================
-- 4. Per-stock returns — join stock_metrics_daily to universe
--    for sector mapping. Limit to 2020+ and current universe
--    members. Columns: sector_name, date, symbol, ret_1w/1m/3m/6m
-- ============================================================
stock_returns AS (
  SELECT
    u.sector                AS sector_name,
    smd.date,
    u.symbol,
    smd.ret_1w,
    smd.ret_1m,
    smd.ret_3m,
    smd.ret_6m
  FROM atlas.atlas_stock_metrics_daily smd
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = smd.instrument_id
   AND u.effective_to IS NULL
  WHERE smd.date >= '2020-01-01'
),

-- ============================================================
-- 5. Breadth-by-window aggregation
--    For each (sector, date) × each lookback window:
--    pct_positive = stocks with ret > 0 / stocks with non-NULL ret
--    pct_top_decile_movers = stocks in top decile / stocks with non-NULL ret
--
--    Top decile: rank by return DESC, threshold is CEIL(N * 0.10).
--    Uses COUNT CASE; NULL ret_* excluded from both numerator and denominator.
--
--    NTILE approach is correct but requires a subquery per window.
--    Here we use row_number + total count approach to avoid nested windows.
-- ============================================================
breadth_window_agg AS (
  SELECT
    sector_name,
    date,

    -- 1W window
    COUNT(ret_1w) FILTER (WHERE ret_1w IS NOT NULL)                            AS n_1w,
    COUNT(ret_1w) FILTER (WHERE ret_1w > 0)                                    AS pos_1w,
    -- 3M window
    COUNT(ret_3m) FILTER (WHERE ret_3m IS NOT NULL)                            AS n_3m,
    COUNT(ret_3m) FILTER (WHERE ret_3m > 0)                                    AS pos_3m,
    -- 1M window
    COUNT(ret_1m) FILTER (WHERE ret_1m IS NOT NULL)                            AS n_1m,
    COUNT(ret_1m) FILTER (WHERE ret_1m > 0)                                    AS pos_1m,
    -- 6M window
    COUNT(ret_6m) FILTER (WHERE ret_6m IS NOT NULL)                            AS n_6m,
    COUNT(ret_6m) FILTER (WHERE ret_6m > 0)                                    AS pos_6m
  FROM stock_returns
  GROUP BY sector_name, date
),

-- ============================================================
-- 5b. Top-decile movers per window
--     Ranks each stock within (sector, date) by descending return,
--     then counts how many fall in the top 10% (NTILE(10) = 1).
--     This is done per-window separately, then joined.
-- ============================================================
ranked_1w AS (
  SELECT sector_name, date,
         COUNT(*) FILTER (WHERE rnk = 1) AS top_decile_1w,
         COUNT(ret_1w)                    AS n_ranked_1w
  FROM (
    SELECT sector_name, date, ret_1w,
           NTILE(10) OVER (PARTITION BY sector_name, date ORDER BY ret_1w DESC NULLS LAST) AS rnk
    FROM stock_returns
    WHERE ret_1w IS NOT NULL
  ) t
  GROUP BY sector_name, date
),
ranked_1m AS (
  SELECT sector_name, date,
         COUNT(*) FILTER (WHERE rnk = 1) AS top_decile_1m,
         COUNT(ret_1m)                    AS n_ranked_1m
  FROM (
    SELECT sector_name, date, ret_1m,
           NTILE(10) OVER (PARTITION BY sector_name, date ORDER BY ret_1m DESC NULLS LAST) AS rnk
    FROM stock_returns
    WHERE ret_1m IS NOT NULL
  ) t
  GROUP BY sector_name, date
),
ranked_3m AS (
  SELECT sector_name, date,
         COUNT(*) FILTER (WHERE rnk = 1) AS top_decile_3m,
         COUNT(ret_3m)                    AS n_ranked_3m
  FROM (
    SELECT sector_name, date, ret_3m,
           NTILE(10) OVER (PARTITION BY sector_name, date ORDER BY ret_3m DESC NULLS LAST) AS rnk
    FROM stock_returns
    WHERE ret_3m IS NOT NULL
  ) t
  GROUP BY sector_name, date
),
ranked_6m AS (
  SELECT sector_name, date,
         COUNT(*) FILTER (WHERE rnk = 1) AS top_decile_6m,
         COUNT(ret_6m)                    AS n_ranked_6m
  FROM (
    SELECT sector_name, date, ret_6m,
           NTILE(10) OVER (PARTITION BY sector_name, date ORDER BY ret_6m DESC NULLS LAST) AS rnk
    FROM stock_returns
    WHERE ret_6m IS NOT NULL
  ) t
  GROUP BY sector_name, date
),

-- ============================================================
-- 6. Strength distribution — NTILE(5) on ret_3m per (sector, date)
--    Quintile 5 = very_strong (top 20%), 1 = very_weak (bottom 20%)
--    NULL ret_3m excluded from NTILE computation.
-- ============================================================
strength_dist AS (
  SELECT
    sector_name,
    date,
    COUNT(*) FILTER (WHERE quintile = 5) AS very_strong,
    COUNT(*) FILTER (WHERE quintile = 4) AS strong,
    COUNT(*) FILTER (WHERE quintile = 3) AS neutral,
    COUNT(*) FILTER (WHERE quintile = 2) AS weak,
    COUNT(*) FILTER (WHERE quintile = 1) AS very_weak
  FROM (
    SELECT
      sector_name,
      date,
      NTILE(5) OVER (PARTITION BY sector_name, date ORDER BY ret_3m ASC) AS quintile
    FROM stock_returns
    WHERE ret_3m IS NOT NULL
  ) quintiled
  GROUP BY sector_name, date
),

-- ============================================================
-- 7. Top/bottom movers — top 5 and bottom 5 stocks by ret_1m
--    per (sector, date). Uses jsonb_agg with ORDER BY.
--    Stocks with NULL ret_1m are excluded (FILTER WHERE ret_1m IS NOT NULL).
--    symbol comes from atlas_universe_stocks via stock_returns.
-- ============================================================
movers AS (
  SELECT
    sector_name,
    date,
    (
      SELECT COALESCE(
        jsonb_agg(
          jsonb_build_object(
            'symbol', sub.symbol,
            'ret_pct', ROUND((sub.ret_1m * 100)::numeric, 2)
          )
          ORDER BY sub.ret_1m DESC
        ) FILTER (WHERE sub.ret_1m IS NOT NULL),
        '[]'::jsonb
      )
      FROM (
        SELECT symbol, ret_1m
        FROM stock_returns sr2
        WHERE sr2.sector_name = sr.sector_name
          AND sr2.date = sr.date
          AND sr2.ret_1m IS NOT NULL
        ORDER BY ret_1m DESC
        LIMIT 5
      ) sub
    ) AS top_movers,
    (
      SELECT COALESCE(
        jsonb_agg(
          jsonb_build_object(
            'symbol', sub.symbol,
            'ret_pct', ROUND((sub.ret_1m * 100)::numeric, 2)
          )
          ORDER BY sub.ret_1m ASC
        ) FILTER (WHERE sub.ret_1m IS NOT NULL),
        '[]'::jsonb
      )
      FROM (
        SELECT symbol, ret_1m
        FROM stock_returns sr2
        WHERE sr2.sector_name = sr.sector_name
          AND sr2.date = sr.date
          AND sr2.ret_1m IS NOT NULL
        ORDER BY ret_1m ASC
        LIMIT 5
      ) sub
    ) AS bottom_movers
  FROM (SELECT DISTINCT sector_name, date FROM stock_returns) sr
)

-- ============================================================
-- 8. FINAL SELECT — one row per (as_of_date, sector_name)
-- ============================================================
SELECT
  s.as_of_date,
  s.sector_name,

  -- ---- Constituent count (current snapshot) ----
  COALESCE(cc.constituent_count, 0)                                   AS constituent_count,

  -- ---- EMA breadth scalars (fractions 0.0–1.0, NULL before backfill) ----
  ROUND(ss.pct_above_ema20::numeric,  4)                              AS pct_above_ema20,
  ROUND(ss.pct_above_ema50::numeric,  4)                              AS pct_above_ema50,
  ROUND(ss.pct_above_ema200::numeric, 4)                              AS pct_above_ema200,
  ROUND(ss.pct_at_52wh::numeric,      4)                              AS pct_at_52wh,

  -- ---- breadth_by_window — JSONB array of 4 window objects ----
  jsonb_build_array(
    jsonb_build_object(
      'window',              '1W',
      'pct_positive',        CASE WHEN bwa.n_1w > 0
                               THEN ROUND((bwa.pos_1w::numeric / bwa.n_1w), 4)
                               ELSE NULL END,
      'pct_top_decile_movers', CASE WHEN r1w.n_ranked_1w > 0
                               THEN ROUND((r1w.top_decile_1w::numeric / r1w.n_ranked_1w), 4)
                               ELSE NULL END
    ),
    jsonb_build_object(
      'window',              '1M',
      'pct_positive',        CASE WHEN bwa.n_1m > 0
                               THEN ROUND((bwa.pos_1m::numeric / bwa.n_1m), 4)
                               ELSE NULL END,
      'pct_top_decile_movers', CASE WHEN r1m.n_ranked_1m > 0
                               THEN ROUND((r1m.top_decile_1m::numeric / r1m.n_ranked_1m), 4)
                               ELSE NULL END
    ),
    jsonb_build_object(
      'window',              '3M',
      'pct_positive',        CASE WHEN bwa.n_3m > 0
                               THEN ROUND((bwa.pos_3m::numeric / bwa.n_3m), 4)
                               ELSE NULL END,
      'pct_top_decile_movers', CASE WHEN r3m.n_ranked_3m > 0
                               THEN ROUND((r3m.top_decile_3m::numeric / r3m.n_ranked_3m), 4)
                               ELSE NULL END
    ),
    jsonb_build_object(
      'window',              '6M',
      'pct_positive',        CASE WHEN bwa.n_6m > 0
                               THEN ROUND((bwa.pos_6m::numeric / bwa.n_6m), 4)
                               ELSE NULL END,
      'pct_top_decile_movers', CASE WHEN r6m.n_ranked_6m > 0
                               THEN ROUND((r6m.top_decile_6m::numeric / r6m.n_ranked_6m), 4)
                               ELSE NULL END
    )
  )                                                                     AS breadth_by_window,

  -- ---- breadth_by_strength — JSONB quintile distribution ----
  CASE WHEN sd.sector_name IS NOT NULL THEN
    jsonb_build_object(
      'very_strong', COALESCE(sd.very_strong, 0),
      'strong',      COALESCE(sd.strong,      0),
      'neutral',     COALESCE(sd.neutral,     0),
      'weak',        COALESCE(sd.weak,        0),
      'very_weak',   COALESCE(sd.very_weak,   0)
    )
  ELSE NULL
  END                                                                   AS breadth_by_strength,

  -- ---- Top / bottom movers (top 5 each by ret_1m) ----
  COALESCE(mv.top_movers,    '[]'::jsonb)                              AS top_movers,
  COALESCE(mv.bottom_movers, '[]'::jsonb)                              AS bottom_movers,

  -- ---- Metadata ----
  NOW()                                                                 AS refreshed_at

FROM spine s
-- EMA breadth scalars
LEFT JOIN sector_scalars ss
  ON ss.as_of_date = s.as_of_date AND ss.sector_name = s.sector_name
-- Constituent count (static current snapshot)
LEFT JOIN constituent_counts cc
  ON cc.sector_name = s.sector_name
-- Breadth-by-window aggregation (raw positive counts)
LEFT JOIN breadth_window_agg bwa
  ON bwa.sector_name = s.sector_name AND bwa.date = s.as_of_date
-- Top-decile ranks per window
LEFT JOIN ranked_1w r1w
  ON r1w.sector_name = s.sector_name AND r1w.date = s.as_of_date
LEFT JOIN ranked_1m r1m
  ON r1m.sector_name = s.sector_name AND r1m.date = s.as_of_date
LEFT JOIN ranked_3m r3m
  ON r3m.sector_name = s.sector_name AND r3m.date = s.as_of_date
LEFT JOIN ranked_6m r6m
  ON r6m.sector_name = s.sector_name AND r6m.date = s.as_of_date
-- Strength distribution
LEFT JOIN strength_dist sd
  ON sd.sector_name = s.sector_name AND sd.date = s.as_of_date
-- Top/bottom movers
LEFT JOIN movers mv
  ON mv.sector_name = s.sector_name AND mv.date = s.as_of_date

WITH NO DATA;
"""

_CREATE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX uix_mv_sector_breadth_date_sector
  ON atlas.mv_sector_breadth (as_of_date, sector_name);
"""

_REFRESH_MV = """
REFRESH MATERIALIZED VIEW atlas.mv_sector_breadth;
"""

_CRON_SCHEDULE = """
SELECT cron.schedule(
  'mv_sector_breadth_nightly',
  '45 14 * * *',
  $$ REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_breadth; $$
);
"""

_CRON_UNSCHEDULE = "SELECT cron.unschedule('mv_sector_breadth_nightly');"

_DROP_UNIQUE_INDEX = "DROP INDEX IF EXISTS atlas.uix_mv_sector_breadth_date_sector;"

_DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_sector_breadth CASCADE;"


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
