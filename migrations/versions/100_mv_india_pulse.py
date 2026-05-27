"""v6 — mv_india_pulse materialized view (Page 02 India Pulse).

Marker migration. The MV was APPLIED on 2026-05-27 directly via Supabase MCP
execute_sql against live atlas-os project nanvgbhootvvthjujkvs.
Mac psycopg2 hangs against Supabase (existing memory entry reference_ec2_access),
so Alembic CLI is not usable from local Mac; MCP execute_sql is the working write path.

MV: atlas.mv_india_pulse
Row shape: ONE row per as_of_date (date spine from atlas_market_regime_daily).
Latest row serves Page 02 India Pulse; historical rows support time-travel.

Sections served:
  - Hero strip (4 scalars): smallcap_rs_z, breadth_pct_above_200dma, india_vix,
    cross_section_dispersion
  - Headline indices (JSONB): 8 indices × level + 1d/1w/1m/3m/6m + RS vs Nifty500
  - Breadth table (JSONB): 7 breadth metrics with Δ1w/Δ1m/Δ3m; 2 gaps flagged
  - Volatility: spot VIX + 5y-percentile scalar + term-structure (VIX − VIX9d)
  - Tier leadership (JSONB): SC vs MC vs LC returns × 5 windows + spreads;
    RS Z-score 90d series
  - Sector heatmap (JSONB): 22 sectors × rs_1w/ret_1m/ret_3m
  - Macro cards (JSONB): 8 macro indicators with value + 1d/1m change + 30d sparkline
  - Narrative ribbon (JSONB): scalars for bond-vs-equity narrative computation
  - Dispersion 60d series (JSONB): trailing cross-section dispersion daily series

Data gaps (deferred to Phase D):
  - % above 100 DMA: not in atlas_market_regime_daily → data_gap: true
  - % at 4-week high: not in atlas_market_regime_daily → data_gap: true
  - Concentration (top-10/11-50/51-200/bottom-300): requires per-stock mkt-cap weights
  - Pairwise correlation 60d: O(n²) per day computation, too heavy for MV
  - Sector daily return (for dispersion bar chart): 1d sector ret not stored

Refresh: pg_cron 'mv_india_pulse_nightly' at 20:30 IST (14:30 UTC) daily.
CONCURRENTLY after first full build. Unique index on as_of_date required.

Design doc: docs/v6/mvs/2026-05-27-mv-india-pulse-design.md

Revision ID: 100
Revises: 099
Create Date: 2026-05-27 IST
"""

from __future__ import annotations

from alembic import op

revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# MV body — full SQL
# ---------------------------------------------------------------------------
_CREATE_MV = """
CREATE MATERIALIZED VIEW atlas.mv_india_pulse AS
WITH

-- ============================================================
-- 1. Date spine — from atlas_market_regime_daily (2609 rows)
-- ============================================================
dates AS (
  SELECT date AS as_of_date
  FROM atlas.atlas_market_regime_daily
),

-- ============================================================
-- 2. Regime inputs (v5 wide table)
-- ============================================================
regime_v5 AS (
  SELECT
    date,
    pct_above_ema_200,
    pct_above_ema_50,
    india_vix,
    ad_ratio,
    mcclellan_oscillator,
    new_52w_highs,
    new_52w_lows,
    ad_line,
    advances_count,
    declines_count
  FROM atlas.atlas_market_regime_daily
),

-- ============================================================
-- 3. Regime inputs (v6 new table — sparse, prefer over v5 where populated)
-- ============================================================
regime_v6 AS (
  SELECT
    date,
    smallcap_rs_z,
    cross_sectional_dispersion,
    vix_percentile,
    breadth_pct_above_200dma
  FROM atlas.atlas_regime_daily
),

-- ============================================================
-- 4. Macro vix9d join — only need vix_9d for term structure
--    (full macro processing is in macro_deltas CTE below)
-- ============================================================
macro_vix9d AS (
  SELECT date, vix_9d
  FROM atlas.atlas_macro_daily
),

-- ============================================================
-- 5. Macro sparklines — last 30 days per macro date (as JSON)
-- ============================================================
macro_sparklines AS (
  SELECT
    m.date,
    -- usdinr 30d sparkline
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.usdinr) ORDER BY sp.date)
     FROM atlas.atlas_macro_daily sp
     WHERE sp.date > m.date - INTERVAL '31 days' AND sp.date <= m.date
       AND sp.usdinr IS NOT NULL
    ) AS usdinr_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.india_10y_yield) ORDER BY sp.date)
     FROM atlas.atlas_macro_daily sp
     WHERE sp.date > m.date - INTERVAL '31 days' AND sp.date <= m.date
       AND sp.india_10y_yield IS NOT NULL
    ) AS india_10y_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.brent_inr) ORDER BY sp.date)
     FROM atlas.atlas_macro_daily sp
     WHERE sp.date > m.date - INTERVAL '31 days' AND sp.date <= m.date
       AND sp.brent_inr IS NOT NULL
    ) AS brent_inr_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v',
        CASE WHEN sp.india_10y_yield IS NOT NULL AND sp.cpi_yoy IS NOT NULL
             THEN sp.india_10y_yield - sp.cpi_yoy ELSE NULL END) ORDER BY sp.date)
     FROM atlas.atlas_macro_daily sp
     WHERE sp.date > m.date - INTERVAL '31 days' AND sp.date <= m.date
    ) AS real_yield_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.fii_cash_equity_flow_cr) ORDER BY sp.date)
     FROM atlas.atlas_macro_daily sp
     WHERE sp.date > m.date - INTERVAL '31 days' AND sp.date <= m.date
    ) AS fii_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.dii_flow) ORDER BY sp.date)
     FROM atlas.atlas_macro_daily sp
     WHERE sp.date > m.date - INTERVAL '31 days' AND sp.date <= m.date
    ) AS dii_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.us_10y_yield) ORDER BY sp.date)
     FROM atlas.atlas_macro_daily sp
     WHERE sp.date > m.date - INTERVAL '31 days' AND sp.date <= m.date
       AND sp.us_10y_yield IS NOT NULL
    ) AS us_10y_spark,
    (SELECT jsonb_agg(jsonb_build_object('date', sp.date, 'v', sp.dxy) ORDER BY sp.date)
     FROM atlas.atlas_macro_daily sp
     WHERE sp.date > m.date - INTERVAL '31 days' AND sp.date <= m.date
       AND sp.dxy IS NOT NULL
    ) AS dxy_spark
  FROM atlas.atlas_macro_daily m
),

-- ============================================================
-- 6. Index metrics — 8 headline indices
-- ============================================================
idx AS (
  SELECT
    date,
    index_code,
    ret_1d,
    ret_1w,
    ret_1m,
    ret_3m,
    ret_6m,
    ret_12m,
    rs_3m_nifty500
  FROM atlas.atlas_index_metrics_daily
  WHERE index_code IN (
    'NIFTY 50', 'NIFTY 100', 'NIFTY MIDCAP 150',
    'NIFTY SMLCAP 250', 'NIFTY 500', 'NIFTY BANK', 'NIFTY IT'
  )
),

-- ============================================================
-- 7. Index close prices — for headline indices level display
-- ============================================================
idx_close AS (
  SELECT
    date,
    index_code,
    close
  FROM public.de_index_prices
  WHERE index_code IN (
    'NIFTY 50', 'NIFTY 100', 'NIFTY MIDCAP 150',
    'NIFTY SMLCAP 250', 'NIFTY 500', 'NIFTY BANK', 'NIFTY IT'
  )
),

-- ============================================================
-- 8. Gold (GOLDBEES proxy from benchmark returns cache)
-- ============================================================
gold AS (
  SELECT
    date,
    close,
    ret_1d,
    ret_1w,
    ret_1m,
    ret_3m,
    ret_6m,
    ret_12m,
    -- Gold has no RS vs Nifty500 pre-computed; compute from ret_Xm and Nifty500 ret_Xm
    NULL::numeric AS rs_3m_nifty500
  FROM atlas.atlas_benchmark_returns_cache
  WHERE benchmark_code = 'GOLD'
),

-- ============================================================
-- 9. Headline indices JSONB — one array per date
-- ============================================================
headline_json AS (
  SELECT
    d.date AS as_of_date,
    jsonb_build_array(
      -- Nifty 50
      jsonb_build_object(
        'index_code', 'NIFTY 50', 'label', 'Nifty 50',
        'close',      ic50.close,
        'ret_1d',     i50.ret_1d, 'ret_1w', i50.ret_1w,
        'ret_1m',     i50.ret_1m, 'ret_3m', i50.ret_3m,
        'ret_6m',     i50.ret_6m,
        'rs_3m_vs_nifty500', i50.rs_3m_nifty500
      ),
      -- Nifty 100
      jsonb_build_object(
        'index_code', 'NIFTY 100', 'label', 'Nifty 100',
        'close',      ic100.close,
        'ret_1d',     i100.ret_1d, 'ret_1w', i100.ret_1w,
        'ret_1m',     i100.ret_1m, 'ret_3m', i100.ret_3m,
        'ret_6m',     i100.ret_6m,
        'rs_3m_vs_nifty500', i100.rs_3m_nifty500
      ),
      -- Nifty Midcap 150
      jsonb_build_object(
        'index_code', 'NIFTY MIDCAP 150', 'label', 'Nifty Midcap 150',
        'close',      icmc.close,
        'ret_1d',     imc.ret_1d, 'ret_1w', imc.ret_1w,
        'ret_1m',     imc.ret_1m, 'ret_3m', imc.ret_3m,
        'ret_6m',     imc.ret_6m,
        'rs_3m_vs_nifty500', imc.rs_3m_nifty500
      ),
      -- Nifty Smallcap 250
      jsonb_build_object(
        'index_code', 'NIFTY SMLCAP 250', 'label', 'Nifty Smallcap 250',
        'close',      icsc.close,
        'ret_1d',     isc.ret_1d, 'ret_1w', isc.ret_1w,
        'ret_1m',     isc.ret_1m, 'ret_3m', isc.ret_3m,
        'ret_6m',     isc.ret_6m,
        'rs_3m_vs_nifty500', isc.rs_3m_nifty500
      ),
      -- Nifty 500 (baseline)
      jsonb_build_object(
        'index_code', 'NIFTY 500', 'label', 'Nifty 500',
        'close',      ic500.close,
        'ret_1d',     i500.ret_1d, 'ret_1w', i500.ret_1w,
        'ret_1m',     i500.ret_1m, 'ret_3m', i500.ret_3m,
        'ret_6m',     i500.ret_6m,
        'rs_3m_vs_nifty500', NULL  -- baseline, no RS vs self
      ),
      -- Nifty Bank
      jsonb_build_object(
        'index_code', 'NIFTY BANK', 'label', 'Nifty Bank',
        'close',      icbnk.close,
        'ret_1d',     ibnk.ret_1d, 'ret_1w', ibnk.ret_1w,
        'ret_1m',     ibnk.ret_1m, 'ret_3m', ibnk.ret_3m,
        'ret_6m',     ibnk.ret_6m,
        'rs_3m_vs_nifty500', ibnk.rs_3m_nifty500
      ),
      -- Nifty IT
      jsonb_build_object(
        'index_code', 'NIFTY IT', 'label', 'Nifty IT',
        'close',      icit.close,
        'ret_1d',     iit.ret_1d, 'ret_1w', iit.ret_1w,
        'ret_1m',     iit.ret_1m, 'ret_3m', iit.ret_3m,
        'ret_6m',     iit.ret_6m,
        'rs_3m_vs_nifty500', iit.rs_3m_nifty500
      ),
      -- Gold (GOLDBEES proxy)
      jsonb_build_object(
        'index_code', 'GOLD', 'label', 'Gold (₹/10g)',
        'close',      g.close,
        'ret_1d',     g.ret_1d, 'ret_1w', g.ret_1w,
        'ret_1m',     g.ret_1m, 'ret_3m', g.ret_3m,
        'ret_6m',     g.ret_6m,
        'rs_3m_vs_nifty500', NULL  -- computed vs Nifty500 separately if needed
      )
    ) AS headline_indices
  FROM (SELECT DISTINCT date FROM atlas.atlas_market_regime_daily) d
  -- Nifty 50
  LEFT JOIN idx i50   ON i50.date = d.date   AND i50.index_code = 'NIFTY 50'
  LEFT JOIN idx_close ic50 ON ic50.date = d.date AND ic50.index_code = 'NIFTY 50'
  -- Nifty 100
  LEFT JOIN idx i100  ON i100.date = d.date  AND i100.index_code = 'NIFTY 100'
  LEFT JOIN idx_close ic100 ON ic100.date = d.date AND ic100.index_code = 'NIFTY 100'
  -- Midcap 150
  LEFT JOIN idx imc   ON imc.date = d.date   AND imc.index_code = 'NIFTY MIDCAP 150'
  LEFT JOIN idx_close icmc ON icmc.date = d.date AND icmc.index_code = 'NIFTY MIDCAP 150'
  -- Smallcap 250
  LEFT JOIN idx isc   ON isc.date = d.date   AND isc.index_code = 'NIFTY SMLCAP 250'
  LEFT JOIN idx_close icsc ON icsc.date = d.date AND icsc.index_code = 'NIFTY SMLCAP 250'
  -- Nifty 500
  LEFT JOIN idx i500  ON i500.date = d.date  AND i500.index_code = 'NIFTY 500'
  LEFT JOIN idx_close ic500 ON ic500.date = d.date AND ic500.index_code = 'NIFTY 500'
  -- Nifty Bank
  LEFT JOIN idx ibnk  ON ibnk.date = d.date  AND ibnk.index_code = 'NIFTY BANK'
  LEFT JOIN idx_close icbnk ON icbnk.date = d.date AND icbnk.index_code = 'NIFTY BANK'
  -- Nifty IT
  LEFT JOIN idx iit   ON iit.date = d.date   AND iit.index_code = 'NIFTY IT'
  LEFT JOIN idx_close icit ON icit.date = d.date AND icit.index_code = 'NIFTY IT'
  -- Gold
  LEFT JOIN gold g    ON g.date = d.date
),

-- ============================================================
-- 10. VIX 5-year percentile — rolling window computation
-- ============================================================
vix_pct AS (
  SELECT
    date,
    india_vix,
    -- 5yr = 1260 trading days
    PERCENT_RANK() OVER (
      ORDER BY india_vix
    ) AS vix_5y_pct_all_time,
    -- More precise: rolling 5y window percentile using 1260 rows lookback
    ROUND(
      CAST(
        PERCENT_RANK() OVER (
          ORDER BY india_vix
          ROWS BETWEEN 1260 PRECEDING AND CURRENT ROW
        ) AS numeric
      ), 4
    ) AS vix_5y_pct
  FROM atlas.atlas_market_regime_daily
  WHERE india_vix IS NOT NULL
),

-- ============================================================
-- 11a. Breadth deltas — pre-compute LAG values (window fns can't
--      be nested inside jsonb_build_object directly in PostgreSQL)
-- ============================================================
breadth_deltas AS (
  SELECT
    date,
    pct_above_ema_200,
    pct_above_ema_50,
    new_52w_highs,
    new_52w_lows,
    ad_ratio,
    mcclellan_oscillator,
    ad_line,
    -- 200 DMA deltas (in %, ×100)
    (pct_above_ema_200 - LAG(pct_above_ema_200, 5)  OVER w) * 100  AS pct200_d1w,
    (pct_above_ema_200 - LAG(pct_above_ema_200, 21) OVER w) * 100  AS pct200_d1m,
    (pct_above_ema_200 - LAG(pct_above_ema_200, 63) OVER w) * 100  AS pct200_d3m,
    -- 50 DMA deltas (in %)
    (pct_above_ema_50 - LAG(pct_above_ema_50, 5)  OVER w) * 100    AS pct50_d1w,
    (pct_above_ema_50 - LAG(pct_above_ema_50, 21) OVER w) * 100    AS pct50_d1m,
    (pct_above_ema_50 - LAG(pct_above_ema_50, 63) OVER w) * 100    AS pct50_d3m,
    -- 52w highs deltas
    new_52w_highs - LAG(new_52w_highs, 5)  OVER w                  AS highs_d1w,
    new_52w_highs - LAG(new_52w_highs, 21) OVER w                  AS highs_d1m,
    new_52w_highs - LAG(new_52w_highs, 63) OVER w                  AS highs_d3m,
    -- 52w lows deltas
    new_52w_lows - LAG(new_52w_lows, 5)  OVER w                    AS lows_d1w,
    new_52w_lows - LAG(new_52w_lows, 21) OVER w                    AS lows_d1m,
    new_52w_lows - LAG(new_52w_lows, 63) OVER w                    AS lows_d3m,
    -- A/D ratio deltas
    ad_ratio - LAG(ad_ratio, 5)  OVER w                            AS adr_d1w,
    ad_ratio - LAG(ad_ratio, 21) OVER w                            AS adr_d1m,
    ad_ratio - LAG(ad_ratio, 63) OVER w                            AS adr_d3m,
    -- McClellan deltas
    mcclellan_oscillator - LAG(mcclellan_oscillator, 5)  OVER w    AS mcl_d1w,
    mcclellan_oscillator - LAG(mcclellan_oscillator, 21) OVER w    AS mcl_d1m,
    mcclellan_oscillator - LAG(mcclellan_oscillator, 63) OVER w    AS mcl_d3m,
    -- A/D line deltas
    ad_line - LAG(ad_line, 5)  OVER w                              AS adl_d1w,
    ad_line - LAG(ad_line, 21) OVER w                              AS adl_d1m,
    ad_line - LAG(ad_line, 63) OVER w                              AS adl_d3m
  FROM atlas.atlas_market_regime_daily
  WINDOW w AS (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
),

-- ============================================================
-- 11b. Breadth table JSONB — 9 rows (7 live + 2 data gaps)
-- ============================================================
breadth_json AS (
  SELECT
    b.date AS as_of_date,
    jsonb_build_array(
      jsonb_build_object(
        'metric', 'pct_above_200dma', 'label', '% above 200 DMA',
        'today',    ROUND((b.pct_above_ema_200 * 100)::numeric, 1),
        'delta_1w', ROUND(b.pct200_d1w::numeric, 1),
        'delta_1m', ROUND(b.pct200_d1m::numeric, 1),
        'delta_3m', ROUND(b.pct200_d3m::numeric, 1),
        'data_gap', false
      ),
      jsonb_build_object(
        'metric', 'pct_above_100dma', 'label', '% above 100 DMA',
        'today', NULL, 'delta_1w', NULL, 'delta_1m', NULL, 'delta_3m', NULL,
        'data_gap', true
      ),
      jsonb_build_object(
        'metric', 'pct_above_50dma', 'label', '% above 50 DMA',
        'today',    ROUND((b.pct_above_ema_50 * 100)::numeric, 1),
        'delta_1w', ROUND(b.pct50_d1w::numeric, 1),
        'delta_1m', ROUND(b.pct50_d1m::numeric, 1),
        'delta_3m', ROUND(b.pct50_d3m::numeric, 1),
        'data_gap', false
      ),
      jsonb_build_object(
        'metric', 'new_52w_highs', 'label', '52-week highs',
        'today',    b.new_52w_highs,
        'delta_1w', b.highs_d1w, 'delta_1m', b.highs_d1m, 'delta_3m', b.highs_d3m,
        'data_gap', false
      ),
      jsonb_build_object(
        'metric', 'new_52w_lows', 'label', '52-week lows',
        'today',    b.new_52w_lows,
        'delta_1w', b.lows_d1w, 'delta_1m', b.lows_d1m, 'delta_3m', b.lows_d3m,
        'data_gap', false
      ),
      jsonb_build_object(
        'metric', 'ad_ratio', 'label', 'Advance/decline ratio',
        'today',    ROUND(b.ad_ratio::numeric, 2),
        'delta_1w', ROUND(b.adr_d1w::numeric, 2),
        'delta_1m', ROUND(b.adr_d1m::numeric, 2),
        'delta_3m', ROUND(b.adr_d3m::numeric, 2),
        'data_gap', false
      ),
      jsonb_build_object(
        'metric', 'mcclellan', 'label', 'McClellan oscillator',
        'today',    ROUND(b.mcclellan_oscillator::numeric, 0),
        'delta_1w', ROUND(b.mcl_d1w::numeric, 0),
        'delta_1m', ROUND(b.mcl_d1m::numeric, 0),
        'delta_3m', ROUND(b.mcl_d3m::numeric, 0),
        'data_gap', false
      ),
      jsonb_build_object(
        'metric', 'pct_4w_high', 'label', '% at 4-week high',
        'today', NULL, 'delta_1w', NULL, 'delta_1m', NULL, 'delta_3m', NULL,
        'data_gap', true
      ),
      jsonb_build_object(
        'metric', 'ad_line', 'label', 'Cumulative A-D line',
        'today',    ROUND(b.ad_line::numeric, 0),
        'delta_1w', ROUND(b.adl_d1w::numeric, 0),
        'delta_1m', ROUND(b.adl_d1m::numeric, 0),
        'delta_3m', ROUND(b.adl_d3m::numeric, 0),
        'data_gap', false
      )
    ) AS breadth_table
  FROM breadth_deltas b
),

-- ============================================================
-- 12. Sector heatmap JSONB — latest sector metrics per date
--     rs_1w (from migration 097), ret_1m, ret_3m
-- ============================================================
sector_heatmap_json AS (
  SELECT
    s.date AS as_of_date,
    jsonb_agg(
      jsonb_build_object(
        'sector_name', s.sector_name,
        'rs_1w',       ROUND(s.rs_1w::numeric, 4),
        'ret_1m',      ROUND(s.bottomup_ret_1m::numeric, 4),
        'ret_3m',      ROUND(s.bottomup_ret_3m::numeric, 4)
      )
      ORDER BY COALESCE(s.rs_1w, 0) DESC
    ) AS sector_heatmap
  FROM atlas.atlas_sector_metrics_daily s
  GROUP BY s.date
),

-- ============================================================
-- 13. Tier leadership — returns table + RS Z-score series
--     SC/MC/LC from index_metrics_daily
-- ============================================================
tier_idx AS (
  SELECT
    date,
    -- Smallcap 250 returns
    MAX(CASE WHEN index_code = 'NIFTY SMLCAP 250' THEN ret_1w  END) AS sc_ret_1w,
    MAX(CASE WHEN index_code = 'NIFTY SMLCAP 250' THEN ret_1m  END) AS sc_ret_1m,
    MAX(CASE WHEN index_code = 'NIFTY SMLCAP 250' THEN ret_3m  END) AS sc_ret_3m,
    MAX(CASE WHEN index_code = 'NIFTY SMLCAP 250' THEN ret_6m  END) AS sc_ret_6m,
    MAX(CASE WHEN index_code = 'NIFTY SMLCAP 250' THEN ret_12m END) AS sc_ret_12m,
    -- Midcap 150 returns
    MAX(CASE WHEN index_code = 'NIFTY MIDCAP 150' THEN ret_1w  END) AS mc_ret_1w,
    MAX(CASE WHEN index_code = 'NIFTY MIDCAP 150' THEN ret_1m  END) AS mc_ret_1m,
    MAX(CASE WHEN index_code = 'NIFTY MIDCAP 150' THEN ret_3m  END) AS mc_ret_3m,
    MAX(CASE WHEN index_code = 'NIFTY MIDCAP 150' THEN ret_6m  END) AS mc_ret_6m,
    MAX(CASE WHEN index_code = 'NIFTY MIDCAP 150' THEN ret_12m END) AS mc_ret_12m,
    -- Nifty 100 as large-cap anchor
    MAX(CASE WHEN index_code = 'NIFTY 100'        THEN ret_1w  END) AS lc_ret_1w,
    MAX(CASE WHEN index_code = 'NIFTY 100'        THEN ret_1m  END) AS lc_ret_1m,
    MAX(CASE WHEN index_code = 'NIFTY 100'        THEN ret_3m  END) AS lc_ret_3m,
    MAX(CASE WHEN index_code = 'NIFTY 100'        THEN ret_6m  END) AS lc_ret_6m,
    MAX(CASE WHEN index_code = 'NIFTY 100'        THEN ret_12m END) AS lc_ret_12m
  FROM atlas.atlas_index_metrics_daily
  WHERE index_code IN ('NIFTY SMLCAP 250', 'NIFTY MIDCAP 150', 'NIFTY 100')
  GROUP BY date
),

tier_leadership_json AS (
  SELECT
    t.date AS as_of_date,
    jsonb_build_object(
      'returns_table', jsonb_build_array(
        jsonb_build_object('window', '1w',
          'sc', ROUND(t.sc_ret_1w::numeric, 4), 'mc', ROUND(t.mc_ret_1w::numeric, 4), 'lc', ROUND(t.lc_ret_1w::numeric, 4),
          'sc_lc_spread', ROUND((COALESCE(t.sc_ret_1w,0) - COALESCE(t.lc_ret_1w,0))::numeric, 4),
          'mc_lc_spread', ROUND((COALESCE(t.mc_ret_1w,0) - COALESCE(t.lc_ret_1w,0))::numeric, 4)
        ),
        jsonb_build_object('window', '1m',
          'sc', ROUND(t.sc_ret_1m::numeric, 4), 'mc', ROUND(t.mc_ret_1m::numeric, 4), 'lc', ROUND(t.lc_ret_1m::numeric, 4),
          'sc_lc_spread', ROUND((COALESCE(t.sc_ret_1m,0) - COALESCE(t.lc_ret_1m,0))::numeric, 4),
          'mc_lc_spread', ROUND((COALESCE(t.mc_ret_1m,0) - COALESCE(t.lc_ret_1m,0))::numeric, 4)
        ),
        jsonb_build_object('window', '3m',
          'sc', ROUND(t.sc_ret_3m::numeric, 4), 'mc', ROUND(t.mc_ret_3m::numeric, 4), 'lc', ROUND(t.lc_ret_3m::numeric, 4),
          'sc_lc_spread', ROUND((COALESCE(t.sc_ret_3m,0) - COALESCE(t.lc_ret_3m,0))::numeric, 4),
          'mc_lc_spread', ROUND((COALESCE(t.mc_ret_3m,0) - COALESCE(t.lc_ret_3m,0))::numeric, 4)
        ),
        jsonb_build_object('window', '6m',
          'sc', ROUND(t.sc_ret_6m::numeric, 4), 'mc', ROUND(t.mc_ret_6m::numeric, 4), 'lc', ROUND(t.lc_ret_6m::numeric, 4),
          'sc_lc_spread', ROUND((COALESCE(t.sc_ret_6m,0) - COALESCE(t.lc_ret_6m,0))::numeric, 4),
          'mc_lc_spread', ROUND((COALESCE(t.mc_ret_6m,0) - COALESCE(t.lc_ret_6m,0))::numeric, 4)
        ),
        jsonb_build_object('window', '12m',
          'sc', ROUND(t.sc_ret_12m::numeric, 4), 'mc', ROUND(t.mc_ret_12m::numeric, 4), 'lc', ROUND(t.lc_ret_12m::numeric, 4),
          'sc_lc_spread', ROUND((COALESCE(t.sc_ret_12m,0) - COALESCE(t.lc_ret_12m,0))::numeric, 4),
          'mc_lc_spread', ROUND((COALESCE(t.mc_ret_12m,0) - COALESCE(t.lc_ret_12m,0))::numeric, 4)
        )
      ),
      -- SC RS Z-score from v6 atlas_regime_daily (sparse; NULL where not computed)
      'smallcap_rs_z', rv6.smallcap_rs_z
    ) AS tier_leadership
  FROM tier_idx t
  LEFT JOIN atlas.atlas_regime_daily rv6 ON rv6.date = t.date
),

-- ============================================================
-- 14. Dispersion 60-day series (JSONB) — trailing window per date
-- ============================================================
dispersion_series_json AS (
  SELECT
    r.date AS as_of_date,
    (
      SELECT jsonb_agg(
        jsonb_build_object('date', s.date, 'value', ROUND(s.cross_sectional_dispersion::numeric, 6))
        ORDER BY s.date
      )
      FROM atlas.atlas_regime_daily s
      WHERE s.date > r.date - INTERVAL '61 days'
        AND s.date <= r.date
        AND s.cross_sectional_dispersion IS NOT NULL
    ) AS dispersion_60d_series
  FROM atlas.atlas_market_regime_daily r
),

-- ============================================================
-- 15. Macro pre-deltas — pre-compute LAG values to avoid nesting
--     window functions inside jsonb_build_object
-- ============================================================
macro_deltas AS (
  SELECT
    m.date,
    m.usdinr,
    m.india_10y_yield,
    m.brent_inr,
    m.cpi_yoy,
    m.fii_cash_equity_flow_cr,
    m.dii_flow,
    m.us_10y_yield,
    m.dxy,
    m.vix_9d,
    -- Real yield
    CASE WHEN m.india_10y_yield IS NOT NULL AND m.cpi_yoy IS NOT NULL
         THEN m.india_10y_yield - m.cpi_yoy ELSE NULL END AS real_yield,
    -- Rolling 21-day cumulative FII/DII
    SUM(m.fii_cash_equity_flow_cr) OVER (ORDER BY m.date ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) AS fii_flow_1m_cr,
    SUM(m.dii_flow) OVER (ORDER BY m.date ROWS BETWEEN 20 PRECEDING AND CURRENT ROW) AS dii_flow_1m_cr,
    -- 1-month LAGs
    LAG(m.usdinr, 21)       OVER (ORDER BY m.date) AS usdinr_1m_ago,
    LAG(m.india_10y_yield, 21) OVER (ORDER BY m.date) AS india_10y_1m_ago,
    LAG(m.brent_inr, 21)    OVER (ORDER BY m.date) AS brent_inr_1m_ago,
    LAG(m.us_10y_yield, 21) OVER (ORDER BY m.date) AS us_10y_1m_ago,
    LAG(m.dxy, 21)          OVER (ORDER BY m.date) AS dxy_1m_ago,
    -- 1-day changes
    m.usdinr - LAG(m.usdinr, 1) OVER (ORDER BY m.date)                         AS usdinr_ret_1d,
    m.india_10y_yield - LAG(m.india_10y_yield, 1) OVER (ORDER BY m.date)       AS india_10y_ret_1d,
    m.brent_inr / NULLIF(LAG(m.brent_inr, 1) OVER (ORDER BY m.date), 0) - 1   AS brent_inr_ret_1d,
    m.us_10y_yield - LAG(m.us_10y_yield, 1) OVER (ORDER BY m.date)             AS us_10y_ret_1d,
    m.dxy / NULLIF(LAG(m.dxy, 1) OVER (ORDER BY m.date), 0) - 1               AS dxy_ret_1d
  FROM atlas.atlas_macro_daily m
),

-- ============================================================
-- 16. Macro cards JSONB — 8 cards with sparklines
-- ============================================================
macro_cards_agg AS (
  SELECT
    md.date AS as_of_date,
    jsonb_build_array(
      jsonb_build_object(
        'id', 'usdinr', 'label', 'USD / INR',
        'value',    ROUND(md.usdinr::numeric, 4),
        'ret_1d',   ROUND(md.usdinr_ret_1d::numeric, 6),
        'ret_1m',   CASE WHEN md.usdinr_1m_ago IS NOT NULL
                         THEN ROUND((md.usdinr / NULLIF(md.usdinr_1m_ago, 0) - 1)::numeric, 6)
                         ELSE NULL END,
        'sparkline_30d', sp.usdinr_spark
      ),
      jsonb_build_object(
        'id', 'india_10y', 'label', 'India 10Y G-Sec yield',
        'value',    ROUND(md.india_10y_yield::numeric, 4),
        'ret_1d',   ROUND(md.india_10y_ret_1d::numeric, 6),
        'ret_1m',   CASE WHEN md.india_10y_1m_ago IS NOT NULL
                         THEN ROUND((md.india_10y_yield - md.india_10y_1m_ago)::numeric, 4)
                         ELSE NULL END,
        'sparkline_30d', sp.india_10y_spark
      ),
      jsonb_build_object(
        'id', 'brent_inr', 'label', 'Brent crude ₹/bbl',
        'value',    ROUND(md.brent_inr::numeric, 2),
        'ret_1d',   ROUND(md.brent_inr_ret_1d::numeric, 6),
        'ret_1m',   CASE WHEN md.brent_inr_1m_ago IS NOT NULL
                         THEN ROUND((md.brent_inr / NULLIF(md.brent_inr_1m_ago, 0) - 1)::numeric, 6)
                         ELSE NULL END,
        'sparkline_30d', sp.brent_inr_spark
      ),
      jsonb_build_object(
        'id', 'real_yield', 'label', 'Real yield (10Y − CPI)',
        'value',    ROUND(md.real_yield::numeric, 4),
        'ret_1d',   NULL,
        'ret_1m',   NULL,
        'sparkline_30d', sp.real_yield_spark
      ),
      jsonb_build_object(
        'id', 'fii_flow_1m', 'label', 'FII net flow · 1M cumulative',
        'value',    ROUND(md.fii_flow_1m_cr::numeric, 0),
        'ret_1d',   ROUND(md.fii_cash_equity_flow_cr::numeric, 0),
        'ret_1m',   NULL,
        'sparkline_30d', sp.fii_spark
      ),
      jsonb_build_object(
        'id', 'dii_flow_1m', 'label', 'DII net flow · 1M cumulative',
        'value',    ROUND(md.dii_flow_1m_cr::numeric, 0),
        'ret_1d',   ROUND(md.dii_flow::numeric, 0),
        'ret_1m',   NULL,
        'sparkline_30d', sp.dii_spark
      ),
      jsonb_build_object(
        'id', 'us_10y', 'label', 'US 10Y yield',
        'value',    ROUND(md.us_10y_yield::numeric, 4),
        'ret_1d',   ROUND(md.us_10y_ret_1d::numeric, 6),
        'ret_1m',   CASE WHEN md.us_10y_1m_ago IS NOT NULL
                         THEN ROUND((md.us_10y_yield - md.us_10y_1m_ago)::numeric, 4)
                         ELSE NULL END,
        'sparkline_30d', sp.us_10y_spark
      ),
      jsonb_build_object(
        'id', 'dxy', 'label', 'DXY · USD index',
        'value',    ROUND(md.dxy::numeric, 2),
        'ret_1d',   ROUND(md.dxy_ret_1d::numeric, 6),
        'ret_1m',   CASE WHEN md.dxy_1m_ago IS NOT NULL
                         THEN ROUND((md.dxy / NULLIF(md.dxy_1m_ago, 0) - 1)::numeric, 6)
                         ELSE NULL END,
        'sparkline_30d', sp.dxy_spark
      )
    ) AS macro_cards
  FROM macro_deltas md
  LEFT JOIN macro_sparklines sp ON sp.date = md.date
)

-- ============================================================
-- 17. FINAL SELECT — one row per as_of_date
-- ============================================================
SELECT
  d.as_of_date,

  -- ---- Hero scalars ----
  COALESCE(rv6.breadth_pct_above_200dma, rv5.pct_above_ema_200)      AS breadth_pct_above_200dma,
  rv5.india_vix,
  rv6.cross_sectional_dispersion                                      AS cross_section_dispersion,
  rv6.smallcap_rs_z,
  rv6.vix_percentile                                                  AS vix_pct_v6,

  -- ---- Volatility triple (vix_spot = india_vix; alias for clarity) ----
  rv5.india_vix                                                       AS vix_spot,
  ROUND(vp.vix_5y_pct::numeric, 4)                                   AS vix_5y_pct,
  CASE
    WHEN rv5.india_vix IS NOT NULL AND mv9.vix_9d IS NOT NULL
    THEN ROUND((rv5.india_vix - mv9.vix_9d)::numeric, 4)
    ELSE NULL
  END                                                                  AS vix_term_structure,

  -- ---- JSONB sections ----
  hj.headline_indices,
  bj.breadth_table,
  shj.sector_heatmap,
  tlj.tier_leadership,
  dsj.dispersion_60d_series,

  -- ---- Macro cards ----
  mcj.macro_cards,

  -- ---- Narrative ribbon scalars ----
  jsonb_build_object(
    'india_10y_yield',       ROUND(md.india_10y_yield::numeric, 4),
    'real_yield',            ROUND(md.real_yield::numeric, 4),
    'cpi_yoy',               ROUND(md.cpi_yoy::numeric, 4),
    'fii_flow_1m_cr',        ROUND(md.fii_flow_1m_cr::numeric, 0),
    'dii_flow_1m_cr',        ROUND(md.dii_flow_1m_cr::numeric, 0),
    'equity_earnings_yield', NULL  -- requires P/E data; deferred
  )                                                                    AS narrative_ribbon,

  -- ---- Metadata ----
  NOW()                                                                AS refreshed_at

FROM dates d
LEFT JOIN regime_v5   rv5  ON rv5.date  = d.as_of_date
LEFT JOIN regime_v6   rv6  ON rv6.date  = d.as_of_date
LEFT JOIN macro_vix9d mv9  ON mv9.date  = d.as_of_date
LEFT JOIN macro_deltas md  ON md.date   = d.as_of_date
LEFT JOIN vix_pct     vp   ON vp.date   = d.as_of_date
LEFT JOIN headline_json   hj  ON hj.as_of_date  = d.as_of_date
LEFT JOIN breadth_json    bj  ON bj.as_of_date  = d.as_of_date
LEFT JOIN sector_heatmap_json shj ON shj.as_of_date = d.as_of_date
LEFT JOIN tier_leadership_json tlj ON tlj.as_of_date = d.as_of_date
LEFT JOIN dispersion_series_json dsj ON dsj.as_of_date = d.as_of_date
LEFT JOIN macro_cards_agg mcj ON mcj.as_of_date = d.as_of_date

WITH NO DATA;
"""

_CREATE_UNIQUE_INDEX = """
CREATE UNIQUE INDEX uix_mv_india_pulse_as_of_date
  ON atlas.mv_india_pulse (as_of_date);
"""

_REFRESH_MV = """
REFRESH MATERIALIZED VIEW atlas.mv_india_pulse;
"""

_CRON_SCHEDULE = """
SELECT cron.schedule(
  'mv_india_pulse_nightly',
  '30 14 * * *',
  $$ REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_india_pulse; $$
);
"""

_CRON_UNSCHEDULE = "SELECT cron.unschedule('mv_india_pulse_nightly');"

_DROP_UNIQUE_INDEX = "DROP INDEX IF EXISTS atlas.uix_mv_india_pulse_as_of_date;"

_DROP_MV = "DROP MATERIALIZED VIEW IF EXISTS atlas.mv_india_pulse CASCADE;"


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
