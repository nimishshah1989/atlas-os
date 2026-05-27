# MV India Pulse — Final Audit

**Date:** 2026-05-27
**Migration:** 100_mv_india_pulse.py
**Status:** READY TO APPLY via Supabase MCP execute_sql

---

## Pre-apply checklist

| Check | Result |
|---|---|
| Migration file created | `migrations/versions/100_mv_india_pulse.py` |
| down_revision correct | `099` (pg_cron atlas_macro_nightly) |
| Tests pass | 26 unit / 6 integration-skipped |
| Ruff clean | Yes (E501 exempted for migrations/**) |
| `.supabase-write-approved` marker | Created |
| Design doc | `docs/v6/mvs/2026-05-27-mv-india-pulse-design.md` |
| Source tables verified | All 7 tables confirmed in migration history + code |

---

## Apply procedure (main session with Supabase MCP)

Run these 5 SQL statements via `execute_sql` in order:

### Step 1 — Create MV
```sql
CREATE MATERIALIZED VIEW atlas.mv_india_pulse AS
WITH
  dates AS (SELECT date AS as_of_date FROM atlas.atlas_market_regime_daily),
  ...
  [full SQL in migrations/versions/100_mv_india_pulse.py::_CREATE_MV]
WITH NO DATA;
```

### Step 2 — Create unique index
```sql
CREATE UNIQUE INDEX uix_mv_india_pulse_as_of_date
  ON atlas.mv_india_pulse (as_of_date);
```

### Step 3 — First full refresh (non-CONCURRENT)
```sql
REFRESH MATERIALIZED VIEW atlas.mv_india_pulse;
```

### Step 4 — Schedule nightly cron (20:30 IST)
```sql
SELECT cron.schedule(
  'mv_india_pulse_nightly',
  '30 14 * * *',
  $$ REFRESH MATERIALIZED VIEW CONCURRENTLY atlas.mv_india_pulse; $$
);
```

### Step 5 — Update Alembic head
```sql
UPDATE atlas.atlas_alembic_version SET version_num = '100';
```

---

## Post-apply verification queries

```sql
-- Row count (expect ≥ 1260 for 5y coverage, ideally ~2609)
SELECT COUNT(*) FROM atlas.mv_india_pulse;

-- Date range (expect MIN ≈ 2016-01-04, MAX = latest trading day)
SELECT MIN(as_of_date), MAX(as_of_date) FROM atlas.mv_india_pulse;

-- Latest row scalars (hero section)
SELECT
  as_of_date,
  breadth_pct_above_200dma,
  india_vix,
  cross_section_dispersion,
  smallcap_rs_z,
  vix_5y_pct,
  vix_term_structure
FROM atlas.mv_india_pulse
ORDER BY as_of_date DESC
LIMIT 1;

-- Verify JSONB sections are populated
SELECT
  as_of_date,
  jsonb_typeof(headline_indices)   AS hi_type,
  jsonb_array_length(headline_indices) AS hi_count,
  jsonb_typeof(breadth_table)      AS bt_type,
  jsonb_array_length(breadth_table)    AS bt_count,
  jsonb_typeof(sector_heatmap)     AS sh_type,
  jsonb_array_length(sector_heatmap)   AS sh_count,
  jsonb_typeof(macro_cards)        AS mc_type,
  jsonb_array_length(macro_cards)      AS mc_count,
  jsonb_typeof(narrative_ribbon)   AS nr_type,
  jsonb_typeof(tier_leadership)    AS tl_type
FROM atlas.mv_india_pulse
ORDER BY as_of_date DESC
LIMIT 1;
-- Expected: hi=array/8, bt=array/9, sh=array/22+, mc=array/8, nr=object, tl=object

-- Verify cron job registered
SELECT jobname, schedule FROM cron.job WHERE jobname = 'mv_india_pulse_nightly';
-- Expected: 1 row, schedule = '30 14 * * *'

-- Sample headline_indices first element
SELECT headline_indices -> 0 AS nifty50
FROM atlas.mv_india_pulse
ORDER BY as_of_date DESC
LIMIT 1;
-- Expected JSON: {"index_code": "NIFTY 50", "label": "Nifty 50", "close": ..., "ret_1d": ..., ...}

-- Sample breadth data_gap row
SELECT bt.value
FROM atlas.mv_india_pulse m,
     jsonb_array_elements(m.breadth_table) bt
WHERE m.as_of_date = (SELECT MAX(as_of_date) FROM atlas.mv_india_pulse)
  AND bt.value->>'data_gap' = 'true';
-- Expected: 2 rows (pct_above_100dma and pct_4w_high)
```

---

## Mockup coverage

| Mockup section | Covered | Notes |
|---|---|---|
| Hero strip (4 tiles) | YES | All 4 scalars in MV root columns |
| Headline indices (8 rich cards) | YES | `headline_indices` JSONB array, 8 elements |
| Breadth table (9 rows) | YES | `breadth_table` JSONB, 9 rows (7 live + 2 gap) |
| Dispersion 60d series | YES | `dispersion_60d_series` — uses atlas_regime_daily |
| Sector dispersion bar chart (today) | PARTIAL | Sector 1d ret not stored; gap acknowledged |
| Concentration stacked bar | DEFERRED | Phase D — needs mkt-cap weights |
| Pairwise correlation 60d | DEFERRED | Phase D — O(n²) |
| Volatility 3-up | YES | vix_spot + vix_5y_pct + vix_term_structure |
| Tier leadership (dual-line + table) | YES | `tier_leadership` JSONB |
| Sector heatmap (22 × 3) | YES | `sector_heatmap` JSONB |
| Macro context (8 cards) | YES | `macro_cards` JSONB with sparklines |
| Bond-vs-equity narrative ribbon | YES | `narrative_ribbon` JSONB (prose at render time) |

---

## Known limitations

1. `% above 100 DMA` not in source → breadth_table row has `data_gap: true`
2. `% at 4-week high` not in source → breadth_table row has `data_gap: true`
3. Concentration section: deferred to Phase D
4. Pairwise correlation: deferred to Phase D
5. `atlas_regime_daily` is sparse (2024+ only) → `smallcap_rs_z` and `cross_sectional_dispersion` are NULL for historical dates (pre-2024)
6. Gold RS vs Nifty500 is NULL (not pre-computed; would require join to Nifty500 returns)
