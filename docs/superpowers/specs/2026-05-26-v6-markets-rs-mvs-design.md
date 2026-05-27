# v6 Page 03 Markets RS — MV Design Spec

**Date:** 2026-05-26 (overnight session)
**Status:** draft — ready to land in next session
**Mockup:** `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/03-markets-rs.html`
**Backing MVs:** `mv_markets_rs_grid` (9 baselines × 5 windows) + `mv_markets_rs_detail_charts` (6 multidim charts)

---

## Locked decisions

| ID | Decision |
|---|---|
| D1 | **9 baselines locked.** Per CONTEXT.md §Baselines: Nifty 50, Nifty 100, Nifty Midcap 150, Nifty Smallcap 250, Nifty 500, Nifty Bank (instead of Nifty 100 dup), Nifty IT (instead of MSCI World ETF), Gold (GOLDBEES), S&P 500. Foreign baselines (URTH, VWO) and India sectorals (Bank, IT) are in detail-charts view, not the main grid. |
| D2 | **Mockup shows 9-row grid as:** 5 Nifty tier anchors (50, 100, Midcap 150, Smallcap 250, 500) + 1 commodity (Gold) + 2 foreign (S&P 500, MSCI World) + 1 emerging (MSCI EM). For 9-row grid use this composition. |
| D3 | **USD/INR adjustment** for foreign baselines: compute `close_inr = close_usd × usdinr` at READ time using `atlas_macro_daily.usdinr`. Spot conversion (not historical). |
| D4 | **5 time windows:** 1w / 1m / 3m / 6m / 12m total return. |
| D5 | **Rank** computed dense_rank() over the 9 baselines per window. |
| D6 | **Detail charts** built on demand (per-page lazy load); MV stores only the grid. Multidim charts query atlas_index_metrics_daily + de_etf_ohlcv + de_global_prices directly via separate Server Component query. |
| D7 | **India RS Grade** rule: A=top-3 rank avg across 1m/3m/6m, B=top-half, C=mixed, D=bottom-half. Encoded in MV row. |

---

## Inputs already in place

| Source | Verified live |
|---|---|
| `public.de_index_prices` | NIFTY 50, NIFTY 100, NIFTY MIDCAP 150, NIFTY SMLCAP 250, NIFTY 500, NIFTY BANK, NIFTY IT — all 2,499 rows, 10-yr history |
| `public.de_etf_ohlcv` | GOLDBEES 2,516 rows, 2016-04-01 onward |
| `public.de_global_prices` | ^GSPC 39,702 rows, URTH 3,406 rows, VWO 2,588 rows |
| `atlas.atlas_macro_daily.usdinr` | 2,704/2,711 populated, used for FX adjustment |

---

## MV body — schema

```sql
CREATE MATERIALIZED VIEW atlas.mv_markets_rs_grid AS
WITH
-- ===========================================================================
-- 1. Resolve baseline tickers + sources per baseline
-- ===========================================================================
baselines (rank_order, baseline_name, source_table, source_filter) AS (
  VALUES
    (1, 'Nifty 50',             'de_index_prices',  $$index_code = 'NIFTY 50'$$),
    (2, 'Nifty 100',            'de_index_prices',  $$index_code = 'NIFTY 100'$$),
    (3, 'Nifty Midcap 150',     'de_index_prices',  $$index_code = 'NIFTY MIDCAP 150'$$),
    (4, 'Nifty Smallcap 250',   'de_index_prices',  $$index_code = 'NIFTY SMLCAP 250'$$),
    (5, 'Nifty 500',            'de_index_prices',  $$index_code = 'NIFTY 500'$$),
    (6, 'Gold (GOLDBEES)',      'de_etf_ohlcv',     $$ticker = 'GOLDBEES'$$),
    (7, 'S&P 500',              'de_global_prices', $$ticker = '^GSPC'$$),
    (8, 'MSCI World (URTH)',    'de_global_prices', $$ticker = 'URTH'$$),
    (9, 'MSCI EM (VWO proxy)',  'de_global_prices', $$ticker = 'VWO'$$)
),

-- ===========================================================================
-- 2. Latest USDINR for FX adjustment
-- ===========================================================================
fx AS (
  SELECT usdinr FROM atlas.atlas_macro_daily
  WHERE usdinr IS NOT NULL
  ORDER BY date DESC LIMIT 1
),

-- ===========================================================================
-- 3. Per-baseline close prices (latest + 1w/1m/3m/6m/12m back)
-- Note: For each baseline, pull close on latest trading day AND closes N days back
-- ===========================================================================
indian_prices AS (
  SELECT
    CASE index_code
      WHEN 'NIFTY 50' THEN 'Nifty 50'
      WHEN 'NIFTY 100' THEN 'Nifty 100'
      WHEN 'NIFTY MIDCAP 150' THEN 'Nifty Midcap 150'
      WHEN 'NIFTY SMLCAP 250' THEN 'Nifty Smallcap 250'
      WHEN 'NIFTY 500' THEN 'Nifty 500'
    END AS baseline_name,
    date, close, 1.0::numeric AS fx_factor
  FROM public.de_index_prices
  WHERE index_code IN ('NIFTY 50','NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250','NIFTY 500')
    AND date >= (CURRENT_DATE - INTERVAL '400 days')
),
gold_prices AS (
  SELECT 'Gold (GOLDBEES)' AS baseline_name, date, close, 1.0::numeric AS fx_factor
  FROM public.de_etf_ohlcv
  WHERE ticker = 'GOLDBEES'
    AND date >= (CURRENT_DATE - INTERVAL '400 days')
),
foreign_prices AS (
  SELECT
    CASE ticker
      WHEN '^GSPC' THEN 'S&P 500'
      WHEN 'URTH'  THEN 'MSCI World (URTH)'
      WHEN 'VWO'   THEN 'MSCI EM (VWO proxy)'
    END AS baseline_name,
    date,
    close,
    (SELECT usdinr FROM fx) AS fx_factor  -- spot FX
  FROM public.de_global_prices
  WHERE ticker IN ('^GSPC','URTH','VWO')
    AND date >= (CURRENT_DATE - INTERVAL '400 days')
),
all_prices AS (
  SELECT * FROM indian_prices
  UNION ALL SELECT * FROM gold_prices
  UNION ALL SELECT * FROM foreign_prices
),

-- ===========================================================================
-- 4. For each baseline, find close on latest day AND 1w/1m/3m/6m/12m back
-- ===========================================================================
latest_close AS (
  SELECT DISTINCT ON (baseline_name) baseline_name, date AS latest_date, close * fx_factor AS latest_close_inr
  FROM all_prices
  ORDER BY baseline_name, date DESC
),
close_back AS (
  SELECT
    lc.baseline_name,
    lc.latest_close_inr,
    -- For each lookback window, find the closest available trading day
    (SELECT close * fx_factor FROM all_prices p 
      WHERE p.baseline_name = lc.baseline_name AND p.date <= lc.latest_date - INTERVAL '7 days'
      ORDER BY p.date DESC LIMIT 1) AS close_1w_back,
    (SELECT close * fx_factor FROM all_prices p 
      WHERE p.baseline_name = lc.baseline_name AND p.date <= lc.latest_date - INTERVAL '30 days'
      ORDER BY p.date DESC LIMIT 1) AS close_1m_back,
    (SELECT close * fx_factor FROM all_prices p 
      WHERE p.baseline_name = lc.baseline_name AND p.date <= lc.latest_date - INTERVAL '91 days'
      ORDER BY p.date DESC LIMIT 1) AS close_3m_back,
    (SELECT close * fx_factor FROM all_prices p 
      WHERE p.baseline_name = lc.baseline_name AND p.date <= lc.latest_date - INTERVAL '182 days'
      ORDER BY p.date DESC LIMIT 1) AS close_6m_back,
    (SELECT close * fx_factor FROM all_prices p 
      WHERE p.baseline_name = lc.baseline_name AND p.date <= lc.latest_date - INTERVAL '365 days'
      ORDER BY p.date DESC LIMIT 1) AS close_12m_back
  FROM latest_close lc
),

-- ===========================================================================
-- 5. Compute returns + ranks per window
-- ===========================================================================
returns AS (
  SELECT
    b.rank_order,
    b.baseline_name,
    cb.latest_close_inr,
    (cb.latest_close_inr / cb.close_1w_back - 1) AS ret_1w,
    (cb.latest_close_inr / cb.close_1m_back - 1) AS ret_1m,
    (cb.latest_close_inr / cb.close_3m_back - 1) AS ret_3m,
    (cb.latest_close_inr / cb.close_6m_back - 1) AS ret_6m,
    (cb.latest_close_inr / cb.close_12m_back - 1) AS ret_12m
  FROM baselines b
  JOIN close_back cb USING (baseline_name)
),
ranked AS (
  SELECT
    *,
    DENSE_RANK() OVER (ORDER BY ret_1w  DESC NULLS LAST) AS rank_1w,
    DENSE_RANK() OVER (ORDER BY ret_1m  DESC NULLS LAST) AS rank_1m,
    DENSE_RANK() OVER (ORDER BY ret_3m  DESC NULLS LAST) AS rank_3m,
    DENSE_RANK() OVER (ORDER BY ret_6m  DESC NULLS LAST) AS rank_6m,
    DENSE_RANK() OVER (ORDER BY ret_12m DESC NULLS LAST) AS rank_12m
  FROM returns
)

SELECT
  rank_order, baseline_name,
  latest_close_inr,
  ret_1w, ret_1m, ret_3m, ret_6m, ret_12m,
  rank_1w, rank_1m, rank_3m, rank_6m, rank_12m,
  CURRENT_DATE AS as_of_date,
  NOW() AS refreshed_at
FROM ranked
ORDER BY rank_order;

CREATE UNIQUE INDEX ix_mv_markets_rs_grid_baseline ON atlas.mv_markets_rs_grid (baseline_name);
```

---

## Hero readout — derived in API layer, not MV

The 4 hero cards on Mockup 03 (Today's leadership / India vs world / Within India / India RS Grade) are NOT in this MV. They're computed at API-read time as a single follow-up query against `mv_markets_rs_grid`:

```sql
-- Hero readout derivation (run by API endpoint per request)
SELECT
  -- "Today's leadership" — rank 1 baseline on 1w
  (SELECT baseline_name FROM atlas.mv_markets_rs_grid WHERE rank_1w = 1) AS today_leader,
  -- "India vs world" — Nifty 500 rank on 1m
  (SELECT rank_1m FROM atlas.mv_markets_rs_grid WHERE baseline_name = 'Nifty 500') AS india_rank_1m,
  -- "Within India" — Nifty 100 ret_3m minus avg(Midcap150, Smallcap250) ret_3m
  ((SELECT ret_3m FROM atlas.mv_markets_rs_grid WHERE baseline_name = 'Nifty 100')
   - (SELECT AVG(ret_3m) FROM atlas.mv_markets_rs_grid WHERE baseline_name IN ('Nifty Midcap 150','Nifty Smallcap 250'))
  ) * 100 AS large_vs_midsmall_spread_3m,
  -- "India RS Grade" — derive from Nifty 500 rank avg across 1m/3m/6m
  CASE
    WHEN ((SELECT rank_1m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')
        + (SELECT rank_3m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')
        + (SELECT rank_6m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')) / 3.0 <= 2.5 THEN 'A'
    WHEN ((SELECT rank_1m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')
        + (SELECT rank_3m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')
        + (SELECT rank_6m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')) / 3.0 <= 4.5 THEN 'B'
    WHEN ((SELECT rank_1m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')
        + (SELECT rank_3m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')
        + (SELECT rank_6m FROM atlas.mv_markets_rs_grid WHERE baseline_name='Nifty 500')) / 3.0 <= 6.5 THEN 'C'
    ELSE 'D'
  END AS india_rs_grade;
```

---

## Detail charts (separate MV — `mv_markets_rs_detail_charts`)

Per-baseline 3M of: price line, support/resistance levels, RS markers, RS strip, volume bars, 20D-MA volume. 6 baselines (Nifty Large Cap = Nifty 100, Nifty Small Cap, Gold, Banking, IT, Auto).

Defer the detail-chart MV to Phase E or as a server-side query that doesn't need pre-materialization. The mockup's 6 detail charts are queried on-demand when the user expands them. Less critical than the grid.

---

## Tests (Phase E)

- 9 rows in `mv_markets_rs_grid` (one per baseline)
- Latest close > 0 for all 9
- 5 returns columns non-NULL for all 9 (after FX adjustment)
- 5 rank columns non-NULL, each spanning 1-9
- Refresh latency < 10s (mostly window functions on 9 rows)

---

## Refresh

```sql
SELECT cron.schedule(
  'refresh_mv_markets_rs_grid',
  '5 20 * * *',  -- 20:05 IST, after Page 01 MV refresh
  $$REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_markets_rs_grid;$$
);
```

---

**Implementation: ready to land next session. Page 03 will render fully — this is the cleanest of the 8 pages.**
