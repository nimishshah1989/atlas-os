# MV India Pulse — Design Spec

**MV name:** `atlas.mv_india_pulse`
**Migration:** `100_mv_india_pulse.py`
**Mockup:** `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/02-india-pulse.html`
**Date:** 2026-05-27
**Status:** APPLIED

---

## Row shape

One row per calendar date. The MV is wide: scalars for the 4 hero inputs +
volatility triple + refresh metadata; nested JSONB for 8 sections that
require arrays at render time. The frontend reads the latest row
(`ORDER BY as_of_date DESC LIMIT 1`); historical dates support time-travel
and backfill validation.

---

## Source table inventory

| Table | Row count | Date range | Columns used |
|---|---|---|---|
| `atlas.atlas_market_regime_daily` | 2609 | 2016-01-04 → 2026-05 | date, pct_above_ema_200, pct_above_ema_50, india_vix, ad_ratio, mcclellan_oscillator, new_52w_highs, new_52w_lows, ad_line, advances_count, declines_count |
| `atlas.atlas_regime_daily` | sparse | 2024-2026 | smallcap_rs_z, cross_sectional_dispersion, vix_percentile, breadth_pct_above_200dma |
| `atlas.atlas_macro_daily` | 2711 | 2016-01-01 → 2026-05 | date, usdinr, india_10y_yield, brent_inr, cpi_yoy, fii_cash_equity_flow_cr, dii_flow, us_10y_yield, dxy, vix_9d |
| `atlas.atlas_index_metrics_daily` | 264203 | 2016-04 → 2026-05 | index_code, date, ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m, rs_3m_nifty500 |
| `public.de_index_prices` | ~800K | 2016-04 → 2026-05 | index_code, date, close |
| `atlas.atlas_sector_metrics_daily` | 76295 | 2017-01 → 2026-05 | sector_name, date, rs_1w, rs_1m (≡ bottomup_ret_1m), bottomup_ret_3m |
| `atlas.atlas_stock_metrics_daily` | 1377002 | 2016 → 2026-05 | ret_1d (for cross-section dispersion; via `atlas_market_regime_daily.cross_section_dispersion` preferred) |

---

## Section-by-section mapping

### Hero strip (4 scalars)

| Mockup field | Source | Column | Notes |
|---|---|---|---|
| Small-cap RS Z-score | `atlas_regime_daily` | `smallcap_rs_z` | COALESCE: if atlas_regime_daily empty for date, use precomputed in atlas_market_regime_daily (v5 computed column). Falls back to NULL with explicit flag. |
| Breadth % above 200 DMA | `atlas_market_regime_daily` | `pct_above_ema_200` | Already a % (0-1 or 0-100; check scale). v6 `atlas_regime_daily.breadth_pct_above_200dma` also available where populated. |
| India VIX | `atlas_market_regime_daily` | `india_vix` | Spot VIX |
| Cross-section dispersion | `atlas_regime_daily` | `cross_sectional_dispersion` | NULL-safe: if empty, compute from `atlas_market_regime_daily` if column exists there, else NULL |

Hero tile "foot copy" (e.g. "Negative for 6 weeks") is computed at render time from the MV's historical series; it is NOT pre-baked in the MV. The MV provides the scalar values + 90-day history array that the frontend uses to compute this dynamically.

### Headline indices (8 rich cards)

JSONB key: `headline_indices` — JSON array of 8 objects.

Index codes used (from `atlas_index_metrics_daily.index_code`):
- `NIFTY 50` / `Nifty50` — check actual index_code values in table
- `NIFTY100` / `Nifty 100`
- `NIFTY MIDCAP 150`
- `NIFTY SMLCAP 250` / `Nifty Smallcap 250`
- `NIFTY 500`
- `NIFTY BANK`
- `NIFTY IT`
- `GOLDBEES` or Gold proxied via `GOLD` in de_index_prices

Each object:
```json
{
  "index_code": "NIFTY 50",
  "label": "Nifty 50",
  "close": 24832.00,
  "ret_1d": -0.0062,
  "ret_1w": -0.0091,
  "ret_1m": -0.0410,
  "ret_3m": 0.0180,
  "ret_6m": 0.1260,
  "rs_3m_vs_nifty500": 0.0560
}
```

Sparkline (30-day price series) is NOT in the MV — the frontend queries `de_index_prices` directly for sparklines. The MV carries the latest scalars only.

### Breadth table (9 rows)

JSONB key: `breadth_table` — JSON array of 9 objects.

Source: `atlas.atlas_market_regime_daily` — one row per date holds all breadth metrics.

| Row | Source column | Δ1w/Δ1m/Δ3m | Notes |
|---|---|---|---|
| % above 200 DMA | `pct_above_ema_200` | LAG 5/21/63 | × 100 for % display |
| % above 100 DMA | NULL (not in source table) | NULL | absent from atlas_market_regime_daily — omit or mark data_gap |
| % above 50 DMA | `pct_above_ema_50` | LAG 5/21/63 | × 100 |
| 52w highs | `new_52w_highs` | LAG | integer count |
| 52w lows | `new_52w_lows` | LAG | integer count |
| A/D ratio | `ad_ratio` | LAG | 5d rolling |
| McClellan oscillator | `mcclellan_oscillator` | LAG | signed |
| % at 4-week high | NULL | NULL | not in atlas_market_regime_daily; absent in MV |
| Cumulative A-D line | `ad_line` | LAG | running total |

Note: "% above 100 DMA" and "% at 4-week high" rows are absent from source data. The MV marks these with `data_gap: true` in the JSONB object; the frontend renders a grey "–" cell.

Window LAG calculation: `value - LAG(value, N) OVER (ORDER BY date)` where N=5 (1w), 21 (1m), 63 (3m). This is computed in the MV CTE using window functions over the date spine.

### Dispersion & concentration

**Cross-section dispersion 60d series:**
JSONB key: `dispersion_60d_series` — array of 60 `{date, value}` objects.
Source: `atlas.atlas_regime_daily.cross_sectional_dispersion` (preferred) or
`atlas.atlas_market_regime_daily` if it carries a dispersion column.

**Sector return dispersion (bar chart, today):**
JSONB key: `sector_dispersion_today` — array of `{sector_name, ret_1d}` sorted desc.
Source: compute from `atlas_sector_metrics_daily.bottomup_ret_1m` approximation (daily ret
is not directly stored; use LAG over 1 row or derive from `ret_1d` if available).
Fallback: mark as `data_gap: true` if 1d ret not available at sector level.

**Concentration (top-10 / 11-50 / 51-200 / bottom-300):**
JSONB key: `concentration` — 4 buckets × 3 windows (1w/1m/3m).
Source: `atlas.atlas_stock_metrics_daily` — requires per-stock ret × market_cap weighting.
This is a heavy computation. Decision: **DEFER to Phase D** — too expensive for MV refresh
without index weight data. MV marks `concentration: null` and frontend shows "Coming soon".

**Average pairwise correlation 60d:**
JSONB key: `pairwise_correlation_60d` — scalar (latest), plus 60-day series array.
Source: requires pairwise correlation matrix across 500 stocks — not pre-computed.
Decision: **DEFER to Phase D**. MV marks `pairwise_correlation_60d: null`.

### Volatility 3-up

Scalars in MV root columns:

| Field | Source | Column |
|---|---|---|
| Spot India VIX | `atlas_market_regime_daily` | `india_vix` |
| 5-year percentile | computed in MV | `PERCENT_RANK() OVER (5y window)` on `india_vix` |
| Term structure (VIX − VIX9d) | `atlas_macro_daily` | `india_vix - vix_9d` (atlas_macro_daily.vix_9d) |

The VIX 5-year percentile is computed via:
```sql
PERCENT_RANK() OVER (
  ORDER BY india_vix
  ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
)
```
Actually: `PERCENT_RANK() OVER (PARTITION BY date_trunc('year', date) ... )` — No.
Use a CTE that computes the trailing 5-year vix percentile relative to the past 1260 rows.

### Tier leadership

JSONB key: `tier_leadership` — object with:
- `smallcap_rs_z_series_90d`: 90-day array of `{date, sc_z, mc_z}` 
- `tier_returns_table`: 5-window × 3-tier returns (SC/MC/LC) + spreads

Source: 
- RS Z-scores: `atlas.atlas_regime_daily.smallcap_rs_z` (sparse). For midcap RS Z, 
  compute from `atlas_index_metrics_daily` using:
  `(ret_Xm_midcap - ret_Xm_nifty100) / stddev_over_window`
- Tier returns: `atlas_index_metrics_daily` — NIFTY SMLCAP 250, NIFTY MIDCAP 150, NIFTY100

### Sector heatmap (22 sectors × 3 windows)

JSONB key: `sector_heatmap` — array of 22 sector objects, each with:
```json
{
  "sector_name": "Energy",
  "rs_1w": 0.034,
  "ret_1m": 0.028,
  "ret_3m": -0.012
}
```

Source: `atlas.atlas_sector_metrics_daily`
- `rs_1w` (added in migration 097) — relative strength 1 week
- `bottomup_ret_1m` → renamed `ret_1m` 
- `bottomup_ret_3m` → renamed `ret_3m`

Note: The mockup shows "22 sectors". The sector table has ~30+ sector_names; the MV
will include whatever sectors have data for the latest date, capped at the 22 most
common per CONTEXT.md sector taxonomy.

### Macro cards (8 cards)

JSONB key: `macro_cards` — array of 8 card objects:

```json
{
  "id": "usdinr",
  "label": "USD / INR",
  "value": 85.42,
  "ret_1d": 0.0021,
  "ret_1m": 0.014,
  "sparkline_30d": [{date, value}, ...]
}
```

| Card | Source column | Fallback |
|---|---|---|
| USD/INR | `atlas_macro_daily.usdinr` | NULL |
| India 10Y | `atlas_macro_daily.india_10y_yield` | NULL |
| Brent ₹/bbl | `atlas_macro_daily.brent_inr` | NULL |
| Real yield (10Y − CPI) | `india_10y_yield - cpi_yoy` | NULL if either NULL |
| FII net flow 1M cumulative | `SUM(fii_cash_equity_flow_cr) OVER 21d` | NULL |
| DII net flow 1M cumulative | `SUM(dii_flow) OVER 21d` | NULL |
| US 10Y | `atlas_macro_daily.us_10y_yield` | NULL |
| DXY | `atlas_macro_daily.dxy` | NULL |

Sparkline (30-day series) is stored in the JSONB array: last 30 rows from `atlas_macro_daily`.

### Narrative ribbon (bond-vs-equity)

JSONB key: `narrative_ribbon` — object with scalar fields:
```json
{
  "india_10y_yield": 6.94,
  "real_yield": 1.86,
  "fii_flow_1m_cr": -38400,
  "equity_earnings_yield": null
}
```

The narrative text is computed at render time from these scalars by the frontend.
The MV carries the numbers; the front generates the prose.

---

## Refresh strategy

| Item | Detail |
|---|---|
| pg_cron job | `mv_india_pulse_nightly` at 20:30 IST (14:30 UTC, `'30 14 * * *'`) |
| Refresh mode | `REFRESH MATERIALIZED VIEW CONCURRENTLY` after initial full refresh |
| Unique index | `ON atlas.mv_india_pulse (as_of_date)` — required for CONCURRENTLY |
| First refresh | `REFRESH MATERIALIZED VIEW atlas.mv_india_pulse` (non-CONCURRENT, one-time) |
| Trigger chain | After `atlas_macro_nightly` (20:15 IST) and `atlas_regime_writer` (20:00 IST) |

---

## Known limitations / data gaps

| Section | Gap | Severity |
|---|---|---|
| % above 100 DMA | Not in `atlas_market_regime_daily` | LOW — mockup row shown as "--" |
| % at 4-week high | Not in `atlas_market_regime_daily` | LOW — mockup row shown as "--" |
| Concentration (top-10 attribution) | Needs market-cap weights per stock per day | MEDIUM — deferred Phase D |
| Pairwise correlation 60d | O(n²) per stock computation | MEDIUM — deferred Phase D |
| Midcap RS Z-score | Not pre-computed; approximated from index returns | LOW — close enough for display |
| Sector dispersion (today's 1d returns) | 1d sector return not directly in sector_metrics_daily | LOW — use LAG or omit |
| Sparklines in macro_cards JSONB | 30-day arrays stored in JSONB — increases MV size | ACCEPTABLE |

---

## Expected row count

Date spine = `atlas.atlas_market_regime_daily.date` (2609 rows, 2016-01-04 to 2026-05).
All dates 2016-01-04 onwards will produce a row; many JSONB sections will have NULLs before 2020
where macro data is incomplete. Minimum coverage target (≥ 2020-01-01): ~1560 rows.

---

## Sample output (latest row, abbreviated)

```json
{
  "as_of_date": "2026-05-26",
  "smallcap_rs_z": -0.840,
  "breadth_pct_above_200dma": 0.420,
  "india_vix": 18.4,
  "cross_section_dispersion": 0.087,
  "vix_9d": 18.0,
  "vix_5y_pct": 0.68,
  "vix_term_structure": 0.41,
  "headline_indices": [
    {"index_code": "Nifty 50", "label": "Nifty 50", "close": 24832.0, "ret_1d": -0.0062, "ret_1m": -0.041, "ret_3m": 0.018, "ret_6m": 0.126, "rs_3m_vs_nifty500": 0.056},
    ...
  ],
  "breadth_table": [
    {"metric": "pct_above_200dma", "today": 42.0, "delta_1w": -3.0, "delta_1m": -16.0, "delta_3m": -29.0, "data_gap": false},
    {"metric": "pct_above_50dma",  "today": 26.0, "delta_1w": -6.0, "delta_1m": -31.0, "delta_3m": -48.0, "data_gap": false},
    {"metric": "new_52w_highs",    "today": 8,    "delta_1w": -4,   "delta_1m": -27,   "delta_3m": -54,   "data_gap": false},
    {"metric": "new_52w_lows",     "today": 31,   "delta_1w": 12,   "delta_1m": 24,    "delta_3m": 29,    "data_gap": false},
    {"metric": "ad_ratio",         "today": 0.61, "delta_1w": -0.18,"delta_1m": -0.42, "delta_3m": -0.71, "data_gap": false},
    {"metric": "mcclellan",        "today": -84,  "delta_1w": -52,  "delta_1m": 12,    "delta_3m": 68,    "data_gap": false},
    {"metric": "ad_line",          "today": -1840,"delta_1w": -420, "delta_1m": -1210, "delta_3m": -2150, "data_gap": false},
    {"metric": "pct_above_100dma", "today": null, "delta_1w": null, "delta_1m": null,  "delta_3m": null,  "data_gap": true},
    {"metric": "pct_4w_high",      "today": null, "delta_1w": null, "delta_1m": null,  "delta_3m": null,  "data_gap": true}
  ],
  "sector_heatmap": [
    {"sector_name": "Energy", "rs_1w": 0.034, "ret_1m": 0.028, "ret_3m": -0.012},
    ...
  ],
  "macro_cards": [
    {"id": "usdinr",         "label": "USD/INR",           "value": 85.42, "ret_1d": 0.0021, "ret_1m": 0.014, "sparkline_30d": [...]},
    {"id": "india_10y",      "label": "India 10Y",          "value": 6.94,  "ret_1d": 0.0008,"ret_1m": 0.0021,"sparkline_30d": [...]},
    {"id": "brent_inr",      "label": "Brent ₹/bbl",        "value": 7180,  "ret_1d": 0.018, "ret_1m": 0.062, "sparkline_30d": [...]},
    {"id": "real_yield",     "label": "Real yield",          "value": 1.86,  "ret_1d": null,  "ret_1m": 0.0012,"sparkline_30d": [...]},
    {"id": "fii_flow_1m",    "label": "FII net 1M",          "value": -38400,"ret_1d": null,  "ret_1m": null,  "sparkline_30d": [...]},
    {"id": "dii_flow_1m",    "label": "DII net 1M",          "value": 41200, "ret_1d": null,  "ret_1m": null,  "sparkline_30d": [...]},
    {"id": "us_10y",         "label": "US 10Y",              "value": 4.62,  "ret_1d": 0.0006,"ret_1m": 0.0018,"sparkline_30d": [...]},
    {"id": "dxy",            "label": "DXY",                 "value": 106.8, "ret_1d": 0.0037,"ret_1m": 0.018, "sparkline_30d": [...]}
  ],
  "tier_leadership": {
    "series_90d": [{"date": "...", "sc_z": -0.84, "mc_z": -0.27}, ...],
    "returns_table": [
      {"window": "1w",  "sc": -0.021, "mc": -0.013, "lc": -0.006, "sc_lc_spread": -0.015, "mc_lc_spread": -0.007},
      ...
    ]
  },
  "dispersion_60d_series": [{"date": "...", "value": 0.087}, ...],
  "narrative_ribbon": {
    "india_10y_yield": 6.94,
    "real_yield": 1.86,
    "fii_flow_1m_cr": -38400,
    "equity_earnings_yield": null
  },
  "refreshed_at": "2026-05-26T20:30:00+05:30"
}
```
