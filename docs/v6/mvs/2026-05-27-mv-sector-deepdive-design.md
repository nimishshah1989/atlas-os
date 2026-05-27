# MV 6 of 9 — `atlas.mv_sector_deepdive` Design

**Date**: 2026-05-27
**Migration**: 105
**Revises**: 104 (mv_sector_rrg)
**Cron**: 20:55 IST (15:25 UTC) daily

---

## Purpose

Serves Page 04a — Sector Deep-Dive (e.g. `/v6/sectors/Energy`). Each of the ~30 sectors gets a dedicated page combining:

- Hero strip: verdict, constituent count, composite score, RS 3M, 12M return
- Multidim chart (uses price/RS data from other MVs, not this one)
- RS grid vs 5 baselines across 6 windows (rs_windows JSONB)
- Constituent stocks table — top 30 by composite score
- Open BUY/SELL signals firing in sector
- Strength distribution chart (quintile breakdown)
- Top picks (top 10 by conviction)

---

## Row Shape

ONE row per `sector_name`. LATEST snapshot only — ~30 rows total.

This is intentionally not historical. The 04a page renders the current state of a sector; historical drill is deferred to a future feature.

---

## Data Scale

| Table | Rows | Filtered To |
|---|---|---|
| atlas_sector_metrics_daily | 74,752 | MAX(date) — 1 date |
| atlas_sector_states_daily | ~74,752 | MAX(date) — 1 date |
| atlas_universe_stocks | 750 | effective_to IS NULL |
| atlas_stock_metrics_daily | ~1.16M | MAX(date) — ~750 rows |
| atlas_stock_states_daily | ~1.16M | MAX(date) — ~750 rows |
| atlas_stock_conviction_daily | ~300K | MAX(date) — ~750 rows |
| atlas_signal_calls | ~363 | exit_date IS NULL |

Output: ~30 rows. All aggregation operates on at most ~750 rows (one date).

---

## CTE Chain

```
1. latest_sector_date / latest_stock_date / latest_conviction_date / latest_stock_state_date / latest_sector_state_date
   ↓ anchor dates for all subsequent CTEs
2. sector_spine
   ↓ ~30 distinct sectors from atlas_universe_stocks
3. sector_metrics
   ↓ bottomup_ret_1m/3m/6m + rs_1w/1m/3m/6m/12m at latest_sector_date
4. n500_rets
   ↓ Nifty 500 ret_1w + ret_12m (for 1W/12M back-derivation)
5. sector_states
   ↓ sector_state (Overweight/Neutral/Underweight) at latest_sector_state_date
6. constituent_counts
   ↓ COUNT(DISTINCT instrument_id) per sector from atlas_universe_stocks
7. stock_data
   ↓ Per-stock: returns, RS, vol, rs_state, composite_score, confidence_band, action
   ↓ Universe JOIN + stock_metrics LEFT JOIN + stock_states LEFT JOIN + conviction LEFT JOIN
8. stock_ranked
   ↓ ROW_NUMBER() OVER (PARTITION BY sector_name ORDER BY composite_score DESC NULLS LAST)
   ↓ ~750 rows at one date — trivially fast
9. strength_dist_agg
   ↓ NTILE(5) on ret_3m per sector — very_strong/strong/neutral/weak/very_weak counts
10. open_signals_raw
    ↓ Open BUY/SELL signal calls with universe JOIN for sector mapping
11. sector_constituents, sector_top_picks, sector_open_signals
    ↓ jsonb_agg with WHERE filters
FINAL SELECT: LEFT JOINs on ~30-row sector_spine
```

---

## JSONB Section Schemas

### `returns` (object)

```json
{
  "ret_1w":  3.42,
  "ret_1m":  7.14,
  "ret_3m": 10.92,
  "ret_6m":  8.52,
  "ret_12m": 24.6
}
```

- Values in percentage (fraction × 100), rounded to 2dp
- `ret_1w` = rs_1w + nifty500_ret_1w (back-derived, NULL if either is NULL)
- `ret_12m` = rs_12m + nifty500_ret_12m (back-derived, NULL if either is NULL)
- `ret_1m/3m/6m` = bottomup_ret_*m directly from sector_metrics_daily
- NULL propagated — never zeroed

### `rs_windows` (object)

```json
{
  "rs_1w":  4.3,
  "rs_1m":  7.2,
  "rs_3m": 10.9,
  "rs_6m":  8.5,
  "rs_12m": 4.5
}
```

- Percentage-point spread vs Nifty 500 (fraction × 100), rounded to 2dp
- NULL propagated

### `constituents_top30` (array, up to 30 elements)

```json
[
  {
    "symbol": "RELIANCE",
    "company_name": "Reliance Industries",
    "tier": "Large",
    "ret_1w": 3.8,
    "ret_1m": 7.1,
    "ret_3m": 12.4,
    "ret_6m": 18.2,
    "rs_3m_nifty500_pp": 9.2,
    "vol_60d": 16.2,
    "rs_state": "Leader",
    "composite_score": 6.4,
    "confidence_band": "H",
    "action": "POSITIVE"
  }
]
```

- Ordered by composite_score DESC (highest conviction first)
- `rs_state` from atlas_stock_states_daily (Leader/Strong/Consolidating/Emerging/Average/Weak/Laggard)
- `composite_score` = (conviction_score - 0.5) × 20, range [-10, +10]
- `confidence_band`: H (industry_grade) / M (baseline) / L (descriptive_only) / NULL
- `action`: POSITIVE / NEUTRAL / NEGATIVE (from conviction_score thresholds)
- Fewer than 30 elements for small sectors — valid

### `open_signals` (array)

```json
[
  {
    "symbol": "RELIANCE",
    "company_name": "Reliance Industries",
    "action": "POSITIVE",
    "tenure": "3m",
    "cap_tier_at_trigger": "Large",
    "confidence_unconditional": 0.82,
    "signal_date": "2026-05-24"
  }
]
```

- Only open signals (exit_date IS NULL)
- Only POSITIVE / NEGATIVE actions (not NEUTRAL)
- Ordered by signal_date DESC (most recent first)
- Empty array if no open signals for sector

### `strength_dist` (object)

```json
{
  "very_strong": 12,
  "strong": 15,
  "neutral": 18,
  "weak": 10,
  "very_weak": 7
}
```

- NTILE(5) on ret_3m: quintile 5 = very_strong (top 20%), 1 = very_weak
- Stocks with NULL ret_3m excluded from NTILE
- All zero if no stocks have non-NULL ret_3m

### `top_picks_top10` (array, up to 10 elements)

```json
[
  {
    "symbol": "RELIANCE",
    "company_name": "Reliance Industries",
    "composite_score": 6.4,
    "confidence_band": "H",
    "action": "POSITIVE"
  }
]
```

- Top 10 by composite_score WHERE composite_score > 0
- Empty array if no stocks with positive composite_score in sector

---

## Scalar Columns

| Column | Source | Notes |
|---|---|---|
| sector_name | atlas_universe_stocks | Primary key |
| verdict | atlas_sector_states_daily.sector_state | Overweight/Neutral/Underweight |
| constituent_count | COUNT(DISTINCT instrument_id) | Current universe snapshot |
| data_as_of | MAX(date) from sector_metrics | Informational |
| pct_above_ema20 | atlas_sector_metrics_daily | Fraction 0.0–1.0, NULLable |
| pct_above_ema200 | atlas_sector_metrics_daily | Fraction 0.0–1.0, NULLable |
| pct_at_52wh | atlas_sector_metrics_daily.pct_52wh | Fraction 0.0–1.0, NULLable |
| refreshed_at | NOW() | MV refresh timestamp |

---

## Performance Profile

- Output: ~30 rows
- Largest single-date scan: ~750 rows (stock_data CTE)
- No correlated subqueries on large tables
- No full-table window functions (unlike MVs 3–5)
- Expected REFRESH time: <5s

---

## NULL Handling

- All financial values: NULL propagated via CASE WHEN IS NOT NULL
- COALESCE used only for: open_signals/constituents/top_picks arrays (→ '[]'), strength_dist counts (→ 0), constituent_count (→ 0)
- verdict: COALESCE to 'Unknown' if sector_states has no row for the sector
- No financial values zeroed

---

## Cron Schedule

Position in nightly pipeline:
```
20:30 mv_india_pulse
20:35 mv_markets_rs_detail_charts
20:40 mv_sector_cards
20:45 mv_sector_breadth
20:50 mv_sector_rrg
20:55 mv_sector_deepdive  ← this MV
```
