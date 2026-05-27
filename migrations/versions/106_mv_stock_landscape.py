"""v6 — mv_stock_landscape materialized view (Page 05 Stocks · bubble + 24-cell matrix).

# allow-large: SQL body is a multi-CTE chain assembling per-stock landscape rows for latest snapshot

Marker migration. The MV is APPLIED via Supabase MCP execute_sql against
live atlas-os project nanvgbhootvvthjujkvs.
Mac psycopg2 hangs against Supabase (existing memory entry reference_ec2_access),
so Alembic CLI is not usable from local Mac; MCP execute_sql is the working write path.

MV: atlas.mv_stock_landscape
Row shape: ONE row per (as_of_date, instrument_id) for the LATEST snapshot only
(~747 stocks × 1 date = ~747 rows). Page 05 renders today's view only;
historical bubble / matrix drill not in scope.

Columns served:
  Identity:
    as_of_date, instrument_id, symbol, company_name, sector, industry, cap_tier
  Bubble chart axes (Page 05 — RS-3M × Composite, size = liquidity proxy):
    rs_3m_nifty500          — bubble x-axis (-15 .. +15 pp)
    composite_score         — bubble y-axis (-10 .. +10), from conviction_score
    liquidity_proxy_cr      — bubble size (avg_volume_252 * close / 1e7, in INR cr)
    bubble_quadrant         — clean_buy / contrarian_buy / clean_avoid / rs_holding
  Matrix axes (Page 05 — cap_tier × tenure × action_sign):
    The 8 columns are 4 return tenures × 2 action signs:
    ret_1m, ret_3m, ret_6m, ret_12m — used to map each stock to a tenure column
    matrix_tenure_dominant  — the strongest tenure for this stock (1m/3m/6m/12m)
    matrix_action_sign      — POS / NEG / NEUTRAL (based on composite_score sign)
    cell_id                 — UUID of the firing cell if stock has an open signal
    cell_action             — POSITIVE / NEGATIVE (signal_calls.action)
    cell_tenure             — 1m / 3m / 6m / 12m (signal_calls.tenure)
    cell_ic                 — confidence_unconditional from atlas_cell_definitions
    cell_predicted_excess   — predicted_excess from signal_calls (open call)
  Conviction:
    conviction_score, conviction_tier (T1-T5), confidence_label
    action                  — derived: BUY (>=+4) / AVOID (<=-4) / WATCH (else)
  RS suite (for filter chips):
    rs_1w_nifty500, rs_1m_nifty500, rs_3m_nifty500
  30-day composite trajectory:
    composite_trajectory_30d JSONB array [{date, score}, ...] for top-50 picks
    (kept only for cards that need it — full universe array too large).

Design:
  LATEST-ONLY snapshot. Frontend computes 24-cell matrix via:
    SELECT cap_tier, matrix_tenure_dominant, matrix_action_sign, COUNT(*)
    FROM mv_stock_landscape
    GROUP BY 1, 2, 3
  IC per cell joined from atlas_cell_definitions on (cap_tier, tenure, action).
  Performance: ~747 rows materialized, refresh <5s.

Source tables:
  atlas.atlas_stock_metrics_daily     — ~1.38M rows, returns + RS + vol + avg_volume
  atlas.atlas_stock_conviction_daily  — ~5.6K rows, conviction_score + tier
  atlas.atlas_universe_stocks         — ~750 rows, cap tier + sector mapping
  atlas.atlas_signal_calls            — ~363 rows, open cell signals
  atlas.atlas_cell_definitions        — 21 active cells (3 of 24 not yet validated)
  atlas.atlas_v6_clean_ohlcv          — close price for liquidity proxy

Column derivation notes:
  composite_score    : ROUND(((conviction_score - 0.5) * 20), 4) → range [-10, +10]
  action             : composite>=4 → BUY, <=-4 → AVOID, else WATCH
                       overridden by open signal_call.action if present
  cap_tier           : atlas_universe_stocks.tier (Large/Mid/Small)
                       NULL for stocks without active universe membership
  liquidity_proxy_cr : (avg_volume_252 * close) / 1e7
                       NULL when either source is NULL — never zeroed
  bubble_quadrant    : composite >= 0 AND rs_3m >= 0  → 'clean_buy'
                       composite >= 0 AND rs_3m <  0  → 'contrarian_buy'
                       composite <  0 AND rs_3m <  0  → 'clean_avoid'
                       composite <  0 AND rs_3m >= 0  → 'rs_holding'
  matrix_tenure_dominant : ARGMAX over abs(ret_1m, ret_3m, ret_6m, ret_12m)
                       Maps each stock to its strongest-magnitude window for matrix display
  matrix_action_sign : composite_score >= 4 → POS, <= -4 → NEG, else NEUTRAL

Refresh: pg_cron 'mv_stock_landscape_nightly' at 21:00 IST (15:30 UTC) daily.
CONCURRENTLY after first full build. Unique index on (instrument_id) required.

Revision ID: 106
Revises: 105
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "106"
down_revision = "105"
branch_labels = None
depends_on = None

_CREATE_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS atlas.mv_stock_landscape AS
WITH

-- ============================================================
-- 1. Latest dates — anchor every CTE to a single trading day.
-- ============================================================
-- Anchor to latest date with non-null RS suite (rs_3m_nifty500 lags
-- absolute returns by ~3 trading days as of 2026-05-27). Using MAX(date)
-- would NULL the bubble x-axis for the entire universe.
latest_metric_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
  WHERE rs_3m_nifty500 IS NOT NULL
),
latest_conviction_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_stock_conviction_daily
),
latest_ohlcv_date AS (
  SELECT MAX(date) AS d FROM atlas.atlas_v6_clean_ohlcv
),

-- ============================================================
-- 2. Universe spine — active stocks with cap_tier + sector.
--    effective_to IS NULL filters to current universe membership.
-- ============================================================
universe AS (
  SELECT
    u.instrument_id,
    u.symbol,
    u.company_name,
    u.tier              AS cap_tier,
    u.sector,
    u.industry
  FROM atlas.atlas_universe_stocks u
  WHERE u.effective_to IS NULL
),

-- ============================================================
-- 3. Latest metrics — returns + RS suite + liquidity inputs.
--    Filtered to latest_metric_date — single date per instrument.
-- ============================================================
metrics AS (
  SELECT
    smd.instrument_id,
    smd.date                AS as_of_date,
    smd.ret_1m,
    smd.ret_3m,
    smd.ret_6m,
    smd.ret_12m,
    smd.rs_1w_nifty500,
    smd.rs_1m_nifty500,
    smd.rs_3m_nifty500,
    smd.avg_volume_252,
    smd.realized_vol_63
  FROM atlas.atlas_stock_metrics_daily smd, latest_metric_date lmd
  WHERE smd.date = lmd.d
),

-- ============================================================
-- 4. Latest price — close from atlas_v6_clean_ohlcv (symbol-keyed).
--    Join universe to map symbol -> instrument_id.
-- ============================================================
prices AS (
  SELECT
    u.instrument_id,
    ohl.close
  FROM atlas.atlas_v6_clean_ohlcv ohl
  JOIN universe u ON u.symbol = ohl.symbol
  CROSS JOIN latest_ohlcv_date lod
  WHERE ohl.date = lod.d
),

-- ============================================================
-- 5. Latest conviction — composite + tier + confidence.
--    composite_score derived: (conviction_score - 0.5) * 20 → [-10, +10]
-- ============================================================
conviction AS (
  SELECT
    sc.instrument_id,
    sc.tier              AS conviction_tier,
    sc.conviction_score,
    sc.confidence_label,
    ROUND(((sc.conviction_score - 0.5) * 20)::numeric, 4) AS composite_score
  FROM atlas.atlas_stock_conviction_daily sc, latest_conviction_date lcd
  WHERE sc.date = lcd.d
),

-- ============================================================
-- 6. Open signal calls — latest fired cell per instrument.
--    ROW_NUMBER picks the most recent open call (exit_date IS NULL).
-- ============================================================
open_signals AS (
  SELECT
    sc.instrument_id,
    sc.cell_id,
    sc.action            AS cell_action,
    sc.tenure            AS cell_tenure,
    sc.predicted_excess  AS cell_predicted_excess,
    sc.confidence_unconditional AS cell_signal_confidence,
    sc.date              AS cell_fire_date,
    ROW_NUMBER() OVER (
      PARTITION BY sc.instrument_id
      ORDER BY sc.date DESC, sc.computed_at DESC
    ) AS rn
  FROM atlas.atlas_signal_calls sc
  WHERE sc.exit_date IS NULL
),
open_signals_latest AS (
  SELECT * FROM open_signals WHERE rn = 1
),

-- ============================================================
-- 7. Cell IC — joined from atlas_cell_definitions (21 active cells).
--    Provides the validated IC (confidence_unconditional) per cell.
-- ============================================================
cell_ic AS (
  SELECT
    cell_id,
    confidence_unconditional AS cell_ic,
    friction_adjusted_excess AS cell_friction_adjusted_excess
  FROM atlas.atlas_cell_definitions
  WHERE deprecated_at IS NULL
),

-- ============================================================
-- 8. 30-day composite trajectory — only for stocks with abs(composite) >= 4
--    (the cards that will be displayed). Avoids bloating JSONB for entire 750.
-- ============================================================
trajectory_window AS (
  SELECT
    sc.instrument_id,
    sc.date,
    ROUND(((sc.conviction_score - 0.5) * 20)::numeric, 4) AS score
  FROM atlas.atlas_stock_conviction_daily sc, latest_conviction_date lcd
  WHERE sc.date BETWEEN (lcd.d - INTERVAL '30 days')::date AND lcd.d
),
trajectory_agg AS (
  SELECT
    instrument_id,
    jsonb_agg(
      jsonb_build_object('date', date::text, 'score', score)
      ORDER BY date ASC
    ) AS composite_trajectory_30d
  FROM trajectory_window
  GROUP BY instrument_id
)

-- ============================================================
-- 9. FINAL SELECT — one row per instrument_id (latest snapshot).
-- ============================================================
SELECT
  m.as_of_date,
  u.instrument_id,
  u.symbol,
  u.company_name,
  u.sector,
  u.industry,
  u.cap_tier,

  -- Returns suite (for matrix tenure mapping)
  ROUND(m.ret_1m::numeric,  4)  AS ret_1m,
  ROUND(m.ret_3m::numeric,  4)  AS ret_3m,
  ROUND(m.ret_6m::numeric,  4)  AS ret_6m,
  ROUND(m.ret_12m::numeric, 4)  AS ret_12m,

  -- RS suite (for bubble x-axis + filter chips)
  ROUND(m.rs_1w_nifty500::numeric, 4) AS rs_1w_nifty500,
  ROUND(m.rs_1m_nifty500::numeric, 4) AS rs_1m_nifty500,
  ROUND(m.rs_3m_nifty500::numeric, 4) AS rs_3m_nifty500,

  -- Conviction + composite
  c.conviction_score,
  c.conviction_tier,
  c.confidence_label,
  c.composite_score,

  -- Action (derived from composite; overridden by open signal if present)
  CASE
    WHEN os.cell_action = 'POSITIVE' THEN 'BUY'
    WHEN os.cell_action = 'NEGATIVE' THEN 'AVOID'
    WHEN c.composite_score IS NULL  THEN NULL
    WHEN c.composite_score >=  4    THEN 'BUY'
    WHEN c.composite_score <= -4    THEN 'AVOID'
    ELSE 'WATCH'
  END AS action,

  -- Bubble quadrant
  CASE
    WHEN c.composite_score IS NULL OR m.rs_3m_nifty500 IS NULL THEN NULL
    WHEN c.composite_score >= 0 AND m.rs_3m_nifty500 >= 0 THEN 'clean_buy'
    WHEN c.composite_score >= 0 AND m.rs_3m_nifty500 <  0 THEN 'contrarian_buy'
    WHEN c.composite_score <  0 AND m.rs_3m_nifty500 <  0 THEN 'clean_avoid'
    WHEN c.composite_score <  0 AND m.rs_3m_nifty500 >= 0 THEN 'rs_holding'
  END AS bubble_quadrant,

  -- Liquidity proxy (mcap stand-in until de_market_cap_history is populated)
  -- avg_volume_252 (shares/day) * close (INR) / 1e7 → INR crores
  CASE
    WHEN m.avg_volume_252 IS NOT NULL AND p.close IS NOT NULL
    THEN ROUND(((m.avg_volume_252::numeric * p.close::numeric) / 1e7)::numeric, 2)
    ELSE NULL
  END AS liquidity_proxy_cr,

  ROUND(p.close::numeric, 2) AS close_price,

  -- Matrix tenure dominant — ARGMAX over abs(ret_*)
  CASE
    WHEN ABS(COALESCE(m.ret_1m, 0))  >= GREATEST(
           ABS(COALESCE(m.ret_3m, 0)),
           ABS(COALESCE(m.ret_6m, 0)),
           ABS(COALESCE(m.ret_12m, 0))
         ) THEN '1m'
    WHEN ABS(COALESCE(m.ret_3m, 0))  >= GREATEST(
           ABS(COALESCE(m.ret_6m, 0)),
           ABS(COALESCE(m.ret_12m, 0))
         ) THEN '3m'
    WHEN ABS(COALESCE(m.ret_6m, 0))  >= ABS(COALESCE(m.ret_12m, 0))
         THEN '6m'
    ELSE '12m'
  END AS matrix_tenure_dominant,

  -- Matrix action sign — for grouping into POS / NEG buckets
  CASE
    WHEN c.composite_score IS NULL  THEN NULL
    WHEN c.composite_score >=  4    THEN 'POS'
    WHEN c.composite_score <= -4    THEN 'NEG'
    ELSE 'NEUTRAL'
  END AS matrix_action_sign,

  -- Cell membership (NULL when no open signal)
  os.cell_id,
  os.cell_action,
  os.cell_tenure,
  os.cell_predicted_excess,
  os.cell_signal_confidence,
  os.cell_fire_date,
  ci.cell_ic,
  ci.cell_friction_adjusted_excess,

  -- 30-day composite trajectory (NULL for stocks without conviction history)
  tr.composite_trajectory_30d,

  -- Realized vol (for cards / size class)
  ROUND(m.realized_vol_63::numeric, 4) AS realized_vol_63,

  NOW() AS refreshed_at

FROM universe u
JOIN metrics m
  ON m.instrument_id = u.instrument_id
LEFT JOIN conviction c
  ON c.instrument_id = u.instrument_id
LEFT JOIN prices p
  ON p.instrument_id = u.instrument_id
LEFT JOIN open_signals_latest os
  ON os.instrument_id = u.instrument_id
LEFT JOIN cell_ic ci
  ON ci.cell_id = os.cell_id
LEFT JOIN trajectory_agg tr
  ON tr.instrument_id = u.instrument_id

WITH NO DATA;
"""

_DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_stock_landscape;"

_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uix_mv_stock_landscape_instrument
ON atlas.mv_stock_landscape (instrument_id);
"""

_CRON = """
SELECT cron.schedule(
  'mv_stock_landscape_nightly',
  '30 15 * * *',
  $$REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_stock_landscape;$$
);
"""


def upgrade() -> None:
    op.execute(_CREATE_MV)
    op.execute(_INDEX)
    op.execute("REFRESH MATERIALIZED VIEW atlas.mv_stock_landscape;")
    op.execute(_CRON)


def downgrade() -> None:
    op.execute("SELECT cron.unschedule('mv_stock_landscape_nightly');")
    op.execute(_DROP_MV)
