"""v6 — mv_sector_deepdive materialized view (Page 04a Sector deep-dive).

# allow-large: SQL body is a 9-CTE chain aggregating per-sector + per-stock data for latest snapshot

Marker migration. The MV is APPLIED via Supabase MCP execute_sql against
live atlas-os project nanvgbhootvvthjujkvs.
Mac psycopg2 hangs against Supabase (existing memory entry reference_ec2_access),
so Alembic CLI is not usable from local Mac; MCP execute_sql is the working write path.

MV: atlas.mv_sector_deepdive
Row shape: ONE row per sector_name (LATEST snapshot only — ~30 rows total).
Page 04a renders for a single sector at a time; historical drill is not in scope.

Sections served (JSONB):
  Hero strip:
    sector_name, verdict (sector_state), constituent_count, rs_3m_nifty500, returns (JSONB)
  rs_windows (JSONB object):
    rs_1w, rs_1m, rs_3m, rs_6m, rs_12m vs Nifty 500
  returns (JSONB object):
    ret_1w, ret_1m, ret_3m, ret_6m, ret_12m (absolute sector returns)
  constituents_top30 (JSONB array):
    top 30 stocks by composite_score per sector:
    {symbol, company_name, tier, ret_1w, ret_1m, ret_3m, ret_6m, rs_3m_nifty500,
     vol_60d, rs_state, composite_score, confidence_band, action}
  open_signals (JSONB array):
    open BUY/SELL signal calls in this sector (exit_date IS NULL):
    {symbol, company_name, action, tenure, cap_tier_at_trigger,
     confidence_unconditional, signal_date}
  strength_dist (JSONB object):
    {very_strong, strong, neutral, weak, very_weak} — NTILE(5) on ret_3m
  top_picks_top10 (JSONB array):
    top 10 by composite_score with positive composite_score:
    {symbol, company_name, composite_score, confidence_band, action}

Design:
  LATEST-ONLY snapshot (not full historical time series). This avoids
  expensive window functions over 48,050 rows and delivers ~30 output rows
  with refresh time <10s.
  All per-stock aggregation operates on a single latest date (~750 stocks),
  making NTILE/ROW_NUMBER window functions trivially fast.
  No correlated subqueries scanning large tables per row.

Source tables:
  atlas.atlas_sector_metrics_daily     — 74,752 rows, sector-level returns + RS
  atlas.atlas_sector_states_daily      — 74,752 rows, sector_state (Overweight/Neutral/Underweight)
  atlas.atlas_universe_stocks          — 750 rows, instrument_id → sector mapping (effective_to IS NULL)
  atlas.atlas_stock_metrics_daily      — ~1.16M rows, per-stock returns + RS + vol
  atlas.atlas_stock_states_daily       — ~1.16M rows, rs_state (Weinstein analog)
  atlas.atlas_stock_conviction_daily   — ~300K rows, conviction_score + confidence_label
  atlas.atlas_signal_calls             — ~363+ rows, open BUY/SELL signals
  atlas.atlas_index_metrics_daily      — Nifty 500 returns for 1W/12M back-derivation

Column notes:
  composite_score: ROUND(((conviction_score - 0.5) * 20), 4) — range [-10, +10]
  confidence_band: industry_grade→H, baseline→M, descriptive_only→L, else NULL
  rs_state (from atlas_stock_states_daily): Leader/Strong/Consolidating/Emerging/Average/Weak/Laggard
    Used as Weinstein-stage analog for constituent display
  sector_state (from atlas_sector_states_daily): Overweight/Neutral/Underweight
  Returns are fractions (0.05 = 5%); multiplied by 100 for display in JSONB
  vol_60d: realized_vol_63 (annualised 63-day realised vol, std*sqrt(252))
  NULL propagated throughout — never zeroed

Data gaps (NULL propagated — never zeroed):
  returns/rs_windows: NULL when source columns are NULL (pre-backfill rows)
  constituents_top30: fewer than 30 elements for small sectors (valid)
  open_signals: empty array if no open signals for sector
  strength_dist: all-zero counts if all ret_3m NULL for sector
  top_picks_top10: empty array if no stocks with positive composite_score

Performance:
  REFRESH target <10s. Achieved by:
  - Filtering all CTEs to MAX(date) anchor — no full-table window passes
  - NTILE/ROW_NUMBER over ~750 stocks at single date (trivially fast)
  - open_signals table is ~363 rows total — no optimization needed
  - Final assembly: LEFT JOIN on ~30-row sector spine

Refresh: pg_cron 'mv_sector_deepdive_nightly' at 20:55 IST (15:25 UTC) daily.
CONCURRENTLY after first full build. Unique index on (sector_name) required.

Design doc: docs/v6/mvs/2026-05-27-mv-sector-deepdive-design.md

Revision ID: 105
Revises: 104
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "105"
down_revision = "104"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# MV body — full SQL
# ---------------------------------------------------------------------------
_CREATE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_sector_deepdive AS
WITH

-- ============================================================
-- 1. Latest dates — anchor for ALL per-date queries.
--    Pre-computed once; used in every subsequent CTE to avoid
--    full-table scans per sector.
-- ============================================================
latest_sector_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_sector_metrics_daily
),
latest_stock_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
),
latest_conviction_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_conviction_daily
),
latest_stock_state_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_states_daily
),
latest_sector_state_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_sector_states_daily
),

-- ============================================================
-- 2. Sector spine — all distinct sector_name values from
--    current universe members. ~30 sectors.
-- ============================================================
sector_spine AS (
  SELECT DISTINCT sector AS sector_name
  FROM atlas.atlas_universe_stocks
  WHERE effective_to IS NULL
),

-- ============================================================
-- 3. Sector-level metrics on latest date — returns + RS.
--    Returns are fractions (0.05 = 5%). Stored in JSONB as
--    percentage values (multiplied by 100, rounded to 2dp).
--    rs_* columns are already pp differences vs Nifty 500
--    (per migration 097/102 docstrings: rs = sector_ret - nifty500_ret).
--    NULL propagated for all columns.
-- ============================================================
sector_metrics AS (
  SELECT
    smd.sector_name,
    -- Absolute returns (bottomup aggregation)
    smd.bottomup_ret_1m                      AS ret_1m_raw,
    smd.bottomup_ret_3m                      AS ret_3m_raw,
    smd.bottomup_ret_6m                      AS ret_6m_raw,
    -- RS windows vs Nifty 500
    smd.rs_1w                                AS rs_1w_raw,
    smd.rs_1m                                AS rs_1m_raw,
    smd.bottomup_rs_3m_nifty500              AS rs_3m_raw,
    smd.rs_6m                                AS rs_6m_raw,
    smd.rs_12m                               AS rs_12m_raw,
    -- Breadth scalars (for hero)
    smd.pct_above_ema20,
    smd.pct_above_ema200,
    smd.pct_52wh                             AS pct_at_52wh
  FROM atlas.atlas_sector_metrics_daily smd
  CROSS JOIN latest_sector_date lsd
  WHERE smd.date = lsd.d
),

-- ============================================================
-- 4. Nifty 500 returns on same date — to back-derive 1W / 12M
--    absolute sector returns:
--      sector_ret_1w  = rs_1w  + nifty500_ret_1w
--      sector_ret_12m = rs_12m + nifty500_ret_12m
--    (rs = sector_ret - nifty500_ret by definition)
--    NULL if Nifty 500 row is missing for that date.
-- ============================================================
n500_rets AS (
  SELECT
    ret_1w    AS n500_ret_1w,
    ret_12m   AS n500_ret_12m
  FROM atlas.atlas_index_metrics_daily
  CROSS JOIN latest_sector_date lsd
  WHERE index_code = 'NIFTY 500'
    AND date = lsd.d
  LIMIT 1
),

-- ============================================================
-- 5. Sector states on latest date — verdict (Overweight/Neutral/Underweight)
-- ============================================================
sector_states AS (
  SELECT
    ssd.sector_name,
    ssd.sector_state
  FROM atlas.atlas_sector_states_daily ssd
  CROSS JOIN latest_sector_state_date lssd
  WHERE ssd.date = lssd.d
),

-- ============================================================
-- 6. Constituent counts — current universe snapshot.
--    Static snapshot; effective_to IS NULL = current member.
-- ============================================================
constituent_counts AS (
  SELECT
    sector            AS sector_name,
    COUNT(DISTINCT instrument_id) AS constituent_count
  FROM atlas.atlas_universe_stocks
  WHERE effective_to IS NULL
  GROUP BY sector
),

-- ============================================================
-- 7. Per-stock data at latest dates — single pass over stock
--    metrics + states + conviction for all sectors.
--    ~750 rows at one date. All joins are on instrument_id.
--    universe join provides sector mapping + symbol + name.
-- ============================================================
stock_data AS (
  SELECT
    u.sector                          AS sector_name,
    u.symbol,
    u.company_name,
    u.tier,
    u.instrument_id,
    -- Returns (fractions, NULLable)
    smd.ret_1w,
    smd.ret_1m,
    smd.ret_3m,
    smd.ret_6m,
    -- RS vs Nifty 500 (fraction, NULLable)
    smd.rs_3m_nifty500,
    -- Annualised realised vol (NULLable)
    smd.realized_vol_63               AS vol_60d,
    -- Weinstein analog — rs_state from stock_states_daily
    ss.rs_state,
    -- Conviction → composite_score + confidence_band
    CASE
      WHEN cd.conviction_score IS NOT NULL
      THEN ROUND(((cd.conviction_score - 0.5) * 20)::numeric, 4)
      ELSE NULL
    END                               AS composite_score,
    CASE cd.confidence_label
      WHEN 'industry_grade'   THEN 'H'
      WHEN 'baseline'         THEN 'M'
      WHEN 'descriptive_only' THEN 'L'
      ELSE NULL
    END                               AS confidence_band,
    -- Action: derive from composite_score sign
    -- Positive composite_score → POSITIVE conviction, Negative → NEGATIVE
    -- NULL composite_score → NULL action
    CASE
      WHEN cd.conviction_score IS NULL THEN NULL
      WHEN cd.conviction_score >= 0.55 THEN 'POSITIVE'
      WHEN cd.conviction_score <= 0.45 THEN 'NEGATIVE'
      ELSE 'NEUTRAL'
    END                               AS action
  FROM atlas.atlas_universe_stocks u
  -- Stock metrics at latest date
  LEFT JOIN atlas.atlas_stock_metrics_daily smd
    ON smd.instrument_id = u.instrument_id
    AND smd.date = (SELECT d FROM latest_stock_date)
  -- Stock states at latest date
  LEFT JOIN atlas.atlas_stock_states_daily ss
    ON ss.instrument_id = u.instrument_id
    AND ss.date = (SELECT d FROM latest_stock_state_date)
  -- Conviction at latest date
  LEFT JOIN atlas.atlas_stock_conviction_daily cd
    ON cd.instrument_id = u.instrument_id
    AND cd.date = (SELECT d FROM latest_conviction_date)
  WHERE u.effective_to IS NULL
),

-- ============================================================
-- 8. Rank constituents within sector by composite_score DESC.
--    ROW_NUMBER over ~750 rows (one date, all sectors) — trivial.
--    NULL composite_score ranked last (NULLS LAST).
--    top_picks: also flag as is_top_pick if composite_score > 0.
-- ============================================================
stock_ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY sector_name
      ORDER BY composite_score DESC NULLS LAST
    ) AS rn_composite
  FROM stock_data
),

-- ============================================================
-- 9. Strength distribution — NTILE(5) on ret_3m within sector.
--    Quintile 5 = very_strong (top 20%), 1 = very_weak.
--    NULL ret_3m excluded (NTILE ignores NULLs via WHERE filter).
--    Aggregated by sector — ~30 output rows.
-- ============================================================
strength_dist_agg AS (
  SELECT
    sector_name,
    COUNT(*) FILTER (WHERE quintile = 5) AS very_strong,
    COUNT(*) FILTER (WHERE quintile = 4) AS strong,
    COUNT(*) FILTER (WHERE quintile = 3) AS neutral,
    COUNT(*) FILTER (WHERE quintile = 2) AS weak,
    COUNT(*) FILTER (WHERE quintile = 1) AS very_weak
  FROM (
    SELECT
      sector_name,
      NTILE(5) OVER (PARTITION BY sector_name ORDER BY ret_3m ASC) AS quintile
    FROM stock_data
    WHERE ret_3m IS NOT NULL
  ) quintiled
  GROUP BY sector_name
),

-- ============================================================
-- 10. Open signals per sector — all open BUY/SELL calls.
--     atlas_signal_calls is small (~363 rows); no optimization needed.
--     Join path: signal_calls.instrument_id → universe_stocks (sector).
-- ============================================================
open_signals_raw AS (
  SELECT
    u.sector                              AS sector_name,
    u.symbol,
    u.company_name,
    sc.action::text,
    sc.tenure::text,
    sc.cap_tier_at_trigger::text,
    ROUND(sc.confidence_unconditional::numeric, 4) AS confidence_unconditional,
    sc.date                               AS signal_date
  FROM atlas.atlas_signal_calls sc
  JOIN atlas.atlas_universe_stocks u
    ON u.instrument_id = sc.instrument_id
   AND u.effective_to IS NULL
  WHERE sc.exit_date IS NULL
    AND sc.action IN ('POSITIVE', 'NEGATIVE')
),

-- ============================================================
-- 11. Assemble JSONB sections per sector.
--     constituents_top30: WHERE rn_composite <= 30 from stock_ranked
--     top_picks_top10:    WHERE rn_composite <= 10 AND composite_score > 0
--     open_signals:       all rows for sector from open_signals_raw
--     strength_dist:      from strength_dist_agg
-- ============================================================
sector_constituents AS (
  SELECT
    sector_name,
    COALESCE(
      jsonb_agg(
        jsonb_build_object(
          'symbol',              symbol,
          'company_name',        company_name,
          'tier',                tier,
          'ret_1w',              CASE WHEN ret_1w IS NOT NULL THEN ROUND((ret_1w * 100)::numeric, 2) ELSE NULL END,
          'ret_1m',              CASE WHEN ret_1m IS NOT NULL THEN ROUND((ret_1m * 100)::numeric, 2) ELSE NULL END,
          'ret_3m',              CASE WHEN ret_3m IS NOT NULL THEN ROUND((ret_3m * 100)::numeric, 2) ELSE NULL END,
          'ret_6m',              CASE WHEN ret_6m IS NOT NULL THEN ROUND((ret_6m * 100)::numeric, 2) ELSE NULL END,
          'rs_3m_nifty500_pp',   CASE WHEN rs_3m_nifty500 IS NOT NULL THEN ROUND((rs_3m_nifty500 * 100)::numeric, 2) ELSE NULL END,
          'vol_60d',             CASE WHEN vol_60d IS NOT NULL THEN ROUND((vol_60d * 100)::numeric, 2) ELSE NULL END,
          'rs_state',            rs_state,
          'composite_score',     composite_score,
          'confidence_band',     confidence_band,
          'action',              action
        )
        ORDER BY rn_composite ASC
      ) FILTER (WHERE rn_composite <= 30),
      '[]'::jsonb
    ) AS constituents_top30
  FROM stock_ranked
  GROUP BY sector_name
),

sector_top_picks AS (
  SELECT
    sector_name,
    COALESCE(
      jsonb_agg(
        jsonb_build_object(
          'symbol',          symbol,
          'company_name',    company_name,
          'composite_score', composite_score,
          'confidence_band', confidence_band,
          'action',          action
        )
        ORDER BY rn_composite ASC
      ) FILTER (WHERE rn_composite <= 10 AND composite_score > 0),
      '[]'::jsonb
    ) AS top_picks_top10
  FROM stock_ranked
  GROUP BY sector_name
),

sector_open_signals AS (
  SELECT
    sector_name,
    COALESCE(
      jsonb_agg(
        jsonb_build_object(
          'symbol',                  symbol,
          'company_name',            company_name,
          'action',                  action,
          'tenure',                  tenure,
          'cap_tier_at_trigger',     cap_tier_at_trigger,
          'confidence_unconditional', confidence_unconditional,
          'signal_date',             signal_date::text
        )
        ORDER BY signal_date DESC
      ),
      '[]'::jsonb
    ) AS open_signals
  FROM open_signals_raw
  GROUP BY sector_name
)

-- ============================================================
-- FINAL SELECT — one row per sector_name (~30 rows)
-- ============================================================
SELECT
  ss.sector_name,

  -- ---- Hero scalars ----
  COALESCE(sst.sector_state, 'Unknown')                AS verdict,
  COALESCE(cc.constituent_count, 0)::integer           AS constituent_count,
  -- Latest as_of_date (informational)
  (SELECT d FROM latest_sector_date)                   AS data_as_of,

  -- ---- Returns JSONB object ----
  jsonb_build_object(
    'ret_1w',  CASE
                 WHEN sm.rs_1w_raw IS NOT NULL AND nr.n500_ret_1w IS NOT NULL
                 THEN ROUND(((sm.rs_1w_raw + nr.n500_ret_1w) * 100)::numeric, 2)
                 ELSE NULL END,
    'ret_1m',  CASE WHEN sm.ret_1m_raw IS NOT NULL THEN ROUND((sm.ret_1m_raw * 100)::numeric, 2) ELSE NULL END,
    'ret_3m',  CASE WHEN sm.ret_3m_raw IS NOT NULL THEN ROUND((sm.ret_3m_raw * 100)::numeric, 2) ELSE NULL END,
    'ret_6m',  CASE WHEN sm.ret_6m_raw IS NOT NULL THEN ROUND((sm.ret_6m_raw * 100)::numeric, 2) ELSE NULL END,
    'ret_12m', CASE
                 WHEN sm.rs_12m_raw IS NOT NULL AND nr.n500_ret_12m IS NOT NULL
                 THEN ROUND(((sm.rs_12m_raw + nr.n500_ret_12m) * 100)::numeric, 2)
                 ELSE NULL END
  )                                                    AS returns,

  -- ---- RS windows JSONB object (pp values vs Nifty 500) ----
  jsonb_build_object(
    'rs_1w',   CASE WHEN sm.rs_1w_raw  IS NOT NULL THEN ROUND((sm.rs_1w_raw  * 100)::numeric, 2) ELSE NULL END,
    'rs_1m',   CASE WHEN sm.rs_1m_raw  IS NOT NULL THEN ROUND((sm.rs_1m_raw  * 100)::numeric, 2) ELSE NULL END,
    'rs_3m',   CASE WHEN sm.rs_3m_raw  IS NOT NULL THEN ROUND((sm.rs_3m_raw  * 100)::numeric, 2) ELSE NULL END,
    'rs_6m',   CASE WHEN sm.rs_6m_raw  IS NOT NULL THEN ROUND((sm.rs_6m_raw  * 100)::numeric, 2) ELSE NULL END,
    'rs_12m',  CASE WHEN sm.rs_12m_raw IS NOT NULL THEN ROUND((sm.rs_12m_raw * 100)::numeric, 2) ELSE NULL END
  )                                                    AS rs_windows,

  -- ---- Breadth scalars (from sector_metrics) ----
  sm.pct_above_ema20,
  sm.pct_above_ema200,
  sm.pct_at_52wh,

  -- ---- Constituents JSONB ----
  COALESCE(sc_agg.constituents_top30, '[]'::jsonb)    AS constituents_top30,

  -- ---- Open signals JSONB ----
  COALESCE(os_agg.open_signals, '[]'::jsonb)          AS open_signals,

  -- ---- Strength distribution JSONB ----
  jsonb_build_object(
    'very_strong', COALESCE(sd.very_strong, 0),
    'strong',      COALESCE(sd.strong,      0),
    'neutral',     COALESCE(sd.neutral,     0),
    'weak',        COALESCE(sd.weak,        0),
    'very_weak',   COALESCE(sd.very_weak,   0)
  )                                                    AS strength_dist,

  -- ---- Top picks JSONB ----
  COALESCE(tp_agg.top_picks_top10, '[]'::jsonb)       AS top_picks_top10,

  -- ---- Metadata ----
  NOW()                                                AS refreshed_at

FROM sector_spine ss

-- Sector metrics
LEFT JOIN sector_metrics sm
  ON sm.sector_name = ss.sector_name

-- Nifty 500 returns (single row cross-join for 1W/12M back-derivation)
LEFT JOIN n500_rets nr ON true

-- Sector verdict
LEFT JOIN sector_states sst
  ON sst.sector_name = ss.sector_name

-- Constituent counts
LEFT JOIN constituent_counts cc
  ON cc.sector_name = ss.sector_name

-- Constituents JSONB
LEFT JOIN sector_constituents sc_agg
  ON sc_agg.sector_name = ss.sector_name

-- Open signals JSONB
LEFT JOIN sector_open_signals os_agg
  ON os_agg.sector_name = ss.sector_name

-- Strength distribution
LEFT JOIN strength_dist_agg sd
  ON sd.sector_name = ss.sector_name

-- Top picks JSONB
LEFT JOIN sector_top_picks tp_agg
  ON tp_agg.sector_name = ss.sector_name

WITH NO DATA;
"""

_CREATE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX uix_mv_sector_deepdive_sector_name
  ON atlas.mv_sector_deepdive (sector_name);
"""

_REFRESH_MV = """
REFRESH MATERIALIZED VIEW atlas.mv_sector_deepdive;
"""

_CRON_SCHEDULE = """
SELECT cron.schedule(
  'mv_sector_deepdive_nightly',
  '25 15 * * *',
  $$ REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_sector_deepdive; $$
);
"""

_CRON_UNSCHEDULE = "SELECT cron.unschedule('mv_sector_deepdive_nightly');"

_DROP_UNIQUE_INDEX = (
    "DROP INDEX IF EXISTS atlas.uix_mv_sector_deepdive_sector_name;"
)

_DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_sector_deepdive CASCADE;"


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
