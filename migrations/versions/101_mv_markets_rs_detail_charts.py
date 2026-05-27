"""v6 — mv_markets_rs_detail_charts (Page 03 detail chart grid).

Marker migration. Applied via Supabase MCP execute_sql against live
atlas-os project nanvgbhootvvthjujkvs on 2026-05-27.
Mac psycopg2 hangs against Supabase; MCP execute_sql is the working write path.

MV: atlas.mv_markets_rs_detail_charts
Row shape: ONE row per (as_of_date, baseline_code).
Latest as_of_date per baseline serves Page 03 "Detail charts" section.
Historical rows support time-travel.

Baselines (9):
  India tier:      NIFTY_50, NIFTY_100, NIFTY_MIDCAP_150, NIFTY_SMLCAP_250, NIFTY_500
  Cross-market:    SP500 (^GSPC, USD→INR), MSCI_WORLD (URTH, USD→INR), MSCI_EM (VWO, USD→INR)
  Commodity:       GOLD (GOLDBEES ETF, already INR)

Each row contains 180 trading days of chart data per baseline:
  price_series      JSONB array 180 × {d, o, h, l, c}  — INR-adjusted close
  rs_series         JSONB array 180 × {d, v}            — excess return vs Nifty 500 (3m rolling)
  volume_series     JSONB array 180 × {d, v, up}        — volume + up/down flag
  ma20_series       JSONB array 180 × {d, v}            — 20-day rolling avg close
  rs_new_high_dates JSONB array of date strings         — dates within window where RS new-high
  rs_new_low_dates  JSONB array of date strings         — dates within window where RS new-low
  support_level     numeric — MIN(close) over last 180 rows
  resistance_level  numeric — MAX(close) over last 180 rows
  latest_close      numeric — close on as_of_date
  rs_latest         numeric — latest RS value
  rs_delta_3m       numeric — latest RS minus RS 180 rows ago

Coverage: 2020-01-01 onwards. All 9 baselines have ≥1640 trading days.
Expected rows: ~14,800 (9 baselines × ~1,640 trading days).

Source tables:
  public.de_index_prices         — India index OHLCV
  public.de_etf_ohlcv            — GOLDBEES ETF OHLCV
  public.de_global_prices        — ^GSPC, URTH, VWO OHLCV (USD)
  atlas.atlas_index_metrics_daily — rs_3m_nifty500 for India indices
  atlas.atlas_macro_daily.usdinr  — per-day FX for USD baselines

Refresh: pg_cron 'mv_markets_rs_detail_charts_nightly' at 20:35 IST (14:35 UTC).
Design doc: docs/v6/mvs/2026-05-27-mv-markets-rs-detail-charts-design.md

Performance approach:
  - All array aggregation done via single-pass window functions + ROW_NUMBER
  - The 180-row window for each as_of_date uses self-join on row_num range
  - No correlated subquery loops — single pass over ~50K base rows
  - Expected runtime on Supabase shared compute: 90–180 seconds for full refresh

Revision ID: 101
Revises: 100
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# MV body — full SQL
# ---------------------------------------------------------------------------
_CREATE_MV = """
CREATE MATERIALIZED VIEW atlas.mv_markets_rs_detail_charts AS
WITH

-- ============================================================
-- 1. USD/INR FX rates with gap-fill via MAX in ordered window.
--    carry-forward: use most recent non-null usdinr within 7 days.
-- ============================================================
fx_raw AS (
  SELECT date, usdinr
  FROM atlas.atlas_macro_daily
  WHERE date >= '2019-06-01'
    AND usdinr IS NOT NULL
),

-- ============================================================
-- 2. India index OHLCV — 5 baselines, INR, 2019-06-01+
-- ============================================================
india_raw AS (
  SELECT
    date,
    CASE index_code
      WHEN 'NIFTY 50'         THEN 'NIFTY_50'
      WHEN 'NIFTY 100'        THEN 'NIFTY_100'
      WHEN 'NIFTY MIDCAP 150' THEN 'NIFTY_MIDCAP_150'
      WHEN 'NIFTY SMLCAP 250' THEN 'NIFTY_SMLCAP_250'
      WHEN 'NIFTY 500'        THEN 'NIFTY_500'
    END                         AS baseline_code,
    open::numeric               AS o,
    high::numeric               AS h,
    low::numeric                AS l,
    close::numeric              AS c,
    volume::bigint              AS vol
  FROM public.de_index_prices
  WHERE index_code IN (
      'NIFTY 50', 'NIFTY 100', 'NIFTY MIDCAP 150',
      'NIFTY SMLCAP 250', 'NIFTY 500'
    )
    AND date >= '2019-06-01'
),

-- ============================================================
-- 3. GOLDBEES ETF — Gold baseline, already INR
-- ============================================================
gold_raw AS (
  SELECT
    date,
    'GOLD'              AS baseline_code,
    open::numeric       AS o,
    high::numeric       AS h,
    low::numeric        AS l,
    close::numeric      AS c,
    volume::bigint      AS vol
  FROM public.de_etf_ohlcv
  WHERE ticker = 'GOLDBEES'
    AND date >= '2019-06-01'
),

-- ============================================================
-- 4. Global prices USD → INR.
--    FX join: match on date; if no exact FX row, carry last known
--    FX within 7 days via lateral max-date sub-select.
-- ============================================================
global_raw AS (
  SELECT
    g.date,
    CASE g.ticker
      WHEN '^GSPC' THEN 'SP500'
      WHEN 'URTH'  THEN 'MSCI_WORLD'
      WHEN 'VWO'   THEN 'MSCI_EM'
    END                                                      AS baseline_code,
    ROUND((g.open  * fx.usdinr)::numeric, 4)                AS o,
    ROUND((g.high  * fx.usdinr)::numeric, 4)                AS h,
    ROUND((g.low   * fx.usdinr)::numeric, 4)                AS l,
    ROUND((g.close * fx.usdinr)::numeric, 4)                AS c,
    g.volume::bigint                                         AS vol
  FROM public.de_global_prices g
  -- FX carry-forward: find the most recent usdinr on or before this date
  JOIN LATERAL (
    SELECT usdinr
    FROM fx_raw
    WHERE fx_raw.date <= g.date
    ORDER BY fx_raw.date DESC
    LIMIT 1
  ) fx ON true
  WHERE g.ticker IN ('^GSPC', 'URTH', 'VWO')
    AND g.date >= '2019-06-01'
    AND g.close IS NOT NULL
),

-- ============================================================
-- 5. All baselines unified
-- ============================================================
all_raw AS (
  SELECT date, baseline_code, o, h, l, c, vol FROM india_raw
  UNION ALL
  SELECT date, baseline_code, o, h, l, c, vol FROM gold_raw
  UNION ALL
  SELECT date, baseline_code, o, h, l, c, vol FROM global_raw
),

-- ============================================================
-- 6. Nifty 500 close — reference for RS computation
-- ============================================================
n500 AS (
  SELECT date, close::numeric AS c
  FROM public.de_index_prices
  WHERE index_code = 'NIFTY 500'
    AND date >= '2019-06-01'
),

-- ============================================================
-- 7. Pre-computed RS from atlas_index_metrics_daily (India indices)
-- ============================================================
india_rs AS (
  SELECT
    date,
    CASE index_code
      WHEN 'NIFTY 50'         THEN 'NIFTY_50'
      WHEN 'NIFTY 100'        THEN 'NIFTY_100'
      WHEN 'NIFTY MIDCAP 150' THEN 'NIFTY_MIDCAP_150'
      WHEN 'NIFTY SMLCAP 250' THEN 'NIFTY_SMLCAP_250'
      WHEN 'NIFTY 500'        THEN 'NIFTY_500'
    END AS baseline_code,
    rs_3m_nifty500
  FROM atlas.atlas_index_metrics_daily
  WHERE index_code IN (
      'NIFTY 50', 'NIFTY 100', 'NIFTY MIDCAP 150',
      'NIFTY SMLCAP 250', 'NIFTY 500'
    )
    AND date >= '2019-06-01'
),

-- ============================================================
-- 8. Enriched prices: window functions in a single pass.
--    All per-baseline ordering done here.
--    - prev_c: yesterday close (for up-day flag)
--    - ma20: 20-day rolling avg
--    - c_63d_ago: close 63 trading rows ago (for RS calc)
--    - n500_c_63d_ago: Nifty 500 close 63 rows ago
--    - row_num: position within baseline (DESC: 1 = latest)
-- ============================================================
enriched AS (
  SELECT
    p.date,
    p.baseline_code,
    p.o,
    p.h,
    p.l,
    p.c,
    p.vol,
    -- Row numbers (1 = latest trading day for this baseline)
    ROW_NUMBER() OVER (
      PARTITION BY p.baseline_code ORDER BY p.date DESC
    ) AS rn_desc,
    ROW_NUMBER() OVER (
      PARTITION BY p.baseline_code ORDER BY p.date ASC
    ) AS rn_asc,
    -- Up-day flag
    CASE
      WHEN p.c >= LAG(p.c) OVER (
        PARTITION BY p.baseline_code ORDER BY p.date
      ) THEN true
      ELSE false
    END AS is_up,
    -- 20-day moving average
    ROUND(
      AVG(p.c) OVER (
        PARTITION BY p.baseline_code ORDER BY p.date
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
      )::numeric, 2
    ) AS ma20,
    -- 63-trading-day ago close for this baseline
    LAG(p.c, 63) OVER (
      PARTITION BY p.baseline_code ORDER BY p.date
    ) AS c_63,
    -- Nifty 500 close today
    n.c                   AS n500_c,
    -- Nifty 500 close 63 rows ago
    LAG(n.c, 63) OVER (
      PARTITION BY p.baseline_code ORDER BY p.date
    ) AS n500_c_63,
    -- Pre-computed RS (India indices only)
    ir.rs_3m_nifty500     AS rs_pre
  FROM all_raw p
  LEFT JOIN n500     n  ON n.date = p.date
  LEFT JOIN india_rs ir ON ir.date = p.date AND ir.baseline_code = p.baseline_code
),

-- ============================================================
-- 9. RS value per row + new-high/low flags.
--    No nested window functions — RS is computed first, flags second.
-- ============================================================
with_rs AS (
  SELECT
    date,
    baseline_code,
    o, h, l, c, vol, is_up, ma20, rn_desc, rn_asc,
    -- RS: use pre-computed for India indices; derive for others
    CASE
      WHEN rs_pre IS NOT NULL THEN rs_pre
      WHEN c_63 IS NOT NULL AND c_63 > 0
           AND n500_c IS NOT NULL
           AND n500_c_63 IS NOT NULL AND n500_c_63 > 0
      THEN ROUND(
        (c / c_63 - 1) - (n500_c / n500_c_63 - 1),
        6
      )
      ELSE NULL
    END AS rs
  FROM enriched
),

-- ============================================================
-- 10. RS high/low markers — separate pass to avoid window nesting.
--     new_high: rs > running max of prior 90 rows
--     new_low:  rs < running min of prior 90 rows
-- ============================================================
with_flags AS (
  SELECT
    date,
    baseline_code,
    o, h, l, c, vol, is_up, ma20, rn_desc, rn_asc, rs,
    CASE
      WHEN rs IS NOT NULL
           AND rs > MAX(rs) OVER (
             PARTITION BY baseline_code ORDER BY date
             ROWS BETWEEN 90 PRECEDING AND 1 PRECEDING
           )
      THEN true ELSE false
    END AS rs_new_hi,
    CASE
      WHEN rs IS NOT NULL
           AND rs < MIN(rs) OVER (
             PARTITION BY baseline_code ORDER BY date
             ROWS BETWEEN 90 PRECEDING AND 1 PRECEDING
           )
      THEN true ELSE false
    END AS rs_new_lo
  FROM with_rs
),

-- ============================================================
-- 11. Filter to date spine (2020-01-01+) for output rows.
--     rn_desc=1 is the latest row per baseline.
--     We emit one output row per (as_of_date, baseline_code)
--     where as_of_date is in our target range.
-- ============================================================
dated AS (
  SELECT *
  FROM with_flags
  WHERE date >= '2020-01-01'
),

-- ============================================================
-- 12. For each row in `dated`, collect the 180-row window
--     using self-join with rn_asc difference.
--     Self-join: ref.rn_asc BETWEEN (ref.rn_asc - 179) AND ref.rn_asc
--
--     NOTE: This is a single pass per baseline using range join.
--     Each output row = (as_of_date, baseline) gets its 180-row window.
-- ============================================================
windowed AS (
  SELECT
    ref.date                                           AS as_of_date,
    ref.baseline_code,
    ref.c                                              AS latest_close,
    ref.rs                                             AS rs_latest,

    -- S/R: min and max close within the 180-row window
    MIN(win.c) OVER (
      PARTITION BY ref.baseline_code, ref.date
    ) AS support_level,
    MAX(win.c) OVER (
      PARTITION BY ref.baseline_code, ref.date
    ) AS resistance_level,

    -- Individual window row data (for aggregation below)
    win.date                                           AS win_date,
    win.o, win.h, win.l, win.c                         AS win_c,
    win.vol, win.is_up, win.ma20, win.rs,
    win.rs_new_hi, win.rs_new_lo,

    -- RS 180 rows ago (first row of window)
    FIRST_VALUE(win.rs) OVER (
      PARTITION BY ref.baseline_code, ref.date
      ORDER BY win.date ASC
    ) AS rs_180d_ago

  FROM dated ref
  JOIN with_flags win
    ON win.baseline_code = ref.baseline_code
   AND win.rn_asc BETWEEN (ref.rn_asc - 179) AND ref.rn_asc
),

-- ============================================================
-- 13. Aggregate window rows into JSONB arrays per (as_of_date, baseline).
-- ============================================================
aggregated AS (
  SELECT
    as_of_date,
    baseline_code,
    MAX(latest_close)    AS latest_close,
    MAX(rs_latest)       AS rs_latest,
    MAX(rs_180d_ago)     AS rs_180d_ago,
    MIN(support_level)   AS support_level,
    MAX(resistance_level) AS resistance_level,

    -- price_series: sorted ASC by date, 180 rows
    jsonb_agg(
      jsonb_build_object(
        'd', win_date,
        'o', ROUND(o::numeric, 2),
        'h', ROUND(h::numeric, 2),
        'l', ROUND(l::numeric, 2),
        'c', ROUND(win_c::numeric, 2)
      )
      ORDER BY win_date
    ) AS price_series,

    -- rs_series: only where RS is not null
    jsonb_agg(
      CASE WHEN rs IS NOT NULL
        THEN jsonb_build_object('d', win_date, 'v', rs)
        ELSE NULL END
      ORDER BY win_date
    ) FILTER (WHERE rs IS NOT NULL) AS rs_series,

    -- volume_series: only where vol is not null
    jsonb_agg(
      CASE WHEN vol IS NOT NULL
        THEN jsonb_build_object('d', win_date, 'v', vol, 'up', is_up)
        ELSE NULL END
      ORDER BY win_date
    ) FILTER (WHERE vol IS NOT NULL) AS volume_series,

    -- ma20_series: only where ma20 is not null (first 19 rows will be null)
    jsonb_agg(
      CASE WHEN ma20 IS NOT NULL
        THEN jsonb_build_object('d', win_date, 'v', ma20)
        ELSE NULL END
      ORDER BY win_date
    ) FILTER (WHERE ma20 IS NOT NULL) AS ma20_series,

    -- rs_new_high_dates: sparse array of dates
    jsonb_agg(
      CASE WHEN rs_new_hi THEN win_date::text ELSE NULL END
      ORDER BY win_date
    ) FILTER (WHERE rs_new_hi) AS rs_new_high_dates,

    -- rs_new_low_dates: sparse array of dates
    jsonb_agg(
      CASE WHEN rs_new_lo THEN win_date::text ELSE NULL END
      ORDER BY win_date
    ) FILTER (WHERE rs_new_lo) AS rs_new_low_dates

  FROM windowed
  GROUP BY as_of_date, baseline_code
)

-- ============================================================
-- 14. FINAL SELECT — one row per (as_of_date, baseline_code)
-- ============================================================
SELECT
  a.as_of_date,
  a.baseline_code,

  -- Human-readable metadata
  CASE a.baseline_code
    WHEN 'NIFTY_50'         THEN 'Nifty 50'
    WHEN 'NIFTY_100'        THEN 'Nifty 100'
    WHEN 'NIFTY_MIDCAP_150' THEN 'Nifty Midcap 150'
    WHEN 'NIFTY_SMLCAP_250' THEN 'Nifty Smallcap 250'
    WHEN 'NIFTY_500'        THEN 'Nifty 500'
    WHEN 'GOLD'             THEN 'Gold (GOLDBEES)'
    WHEN 'SP500'            THEN 'S&P 500'
    WHEN 'MSCI_WORLD'       THEN 'MSCI World (URTH)'
    WHEN 'MSCI_EM'          THEN 'MSCI EM (VWO)'
  END                                           AS baseline_label,

  CASE a.baseline_code
    WHEN 'NIFTY_50'         THEN 'India tier'
    WHEN 'NIFTY_100'        THEN 'India tier'
    WHEN 'NIFTY_MIDCAP_150' THEN 'India tier'
    WHEN 'NIFTY_SMLCAP_250' THEN 'India tier'
    WHEN 'NIFTY_500'        THEN 'India tier'
    WHEN 'GOLD'             THEN 'Commodity'
    WHEN 'SP500'            THEN 'Developed'
    WHEN 'MSCI_WORLD'       THEN 'Developed'
    WHEN 'MSCI_EM'          THEN 'Emerging'
  END                                           AS baseline_group,

  CASE a.baseline_code
    WHEN 'SP500'      THEN true
    WHEN 'MSCI_WORLD' THEN true
    WHEN 'MSCI_EM'    THEN true
    ELSE false
  END                                           AS is_usd_baseline,

  -- Scalars
  ROUND(a.latest_close::numeric,  2)            AS latest_close,
  ROUND(a.rs_latest::numeric,     6)            AS rs_latest,
  ROUND((a.rs_latest - a.rs_180d_ago)::numeric, 6) AS rs_delta_3m,
  ROUND(a.support_level::numeric, 2)            AS support_level,
  ROUND(a.resistance_level::numeric, 2)         AS resistance_level,

  -- JSONB chart arrays
  a.price_series,
  a.rs_series,
  a.volume_series,
  a.ma20_series,
  COALESCE(a.rs_new_high_dates, '[]'::jsonb)    AS rs_new_high_dates,
  COALESCE(a.rs_new_low_dates,  '[]'::jsonb)    AS rs_new_low_dates,

  -- Metadata
  NOW()                                         AS refreshed_at

FROM aggregated a
WHERE a.latest_close IS NOT NULL

WITH NO DATA;
"""

_CREATE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX uix_mv_markets_rs_detail_charts_date_baseline
  ON atlas.mv_markets_rs_detail_charts (as_of_date, baseline_code);
"""

_REFRESH_MV = """
REFRESH MATERIALIZED VIEW atlas.mv_markets_rs_detail_charts;
"""

_CRON_SCHEDULE = """
SELECT cron.schedule(
  'mv_markets_rs_detail_charts_nightly',
  '35 14 * * *',
  $$ REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_markets_rs_detail_charts; $$
);
"""

_CRON_UNSCHEDULE = "SELECT cron.unschedule('mv_markets_rs_detail_charts_nightly');"

_DROP_UNIQUE_INDEX = (
    "DROP INDEX IF EXISTS atlas.uix_mv_markets_rs_detail_charts_date_baseline;"
)

_DROP_MV = (
    "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_markets_rs_detail_charts CASCADE;"
)


def upgrade() -> None:
    """Create MV, unique index, initial full refresh, schedule nightly cron."""
    op.execute(_CREATE_MV)
    op.execute(_CREATE_UNIQUE_INDEX)
    op.execute(_REFRESH_MV)
    op.execute(_CRON_SCHEDULE)


def downgrade() -> None:
    """Drop cron job + MV in dependency-safe order."""
    op.execute(_CRON_UNSCHEDULE)
    op.execute(_DROP_UNIQUE_INDEX)
    op.execute(_DROP_MV)
