# MV Markets RS Detail Charts — Design Spec

**MV name:** `atlas.mv_markets_rs_detail_charts`
**Migration:** `101_mv_markets_rs_detail_charts.py`
**Mockup:** `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/03-markets-rs.html`
**Section:** "Detail charts — price, volume & RS in one frame"
**Date:** 2026-05-27
**Status:** DRAFT

---

## Row shape

**ONE row per (as_of_date, baseline_code)**. The latest `as_of_date` per baseline
serves the live page; historical rows enable time-travel.

Each row carries the **last 180 trading days** of chart data in JSONB arrays. This bounds
the maximum row size: 180 elements × ~100 bytes each = ~18KB per row per baseline.
At 9 baselines × ~1,640 trading days (2020-01-01 to 2026-05-27) = ~14,760 rows total.

---

## Source table inventory

| Table | Verified row count | Date range | Usage |
|---|---|---|---|
| `public.de_index_prices` | ~12,500 (5 codes × 2,500) | 2016-04 → 2026-05 | Price OHLCV for India index baselines |
| `public.de_etf_ohlcv` GOLDBEES | 2,516 | 2016-04-01 → 2026-05 | Price proxy for Gold baseline |
| `public.de_global_prices` ^GSPC | 39,702 | 1928-01-02 → 2026-05 | Price for S&P 500 (USD → INR) |
| `public.de_global_prices` URTH | 3,406 | 2012-01 → 2026-05 | MSCI World ETF proxy |
| `public.de_global_prices` VWO | 2,588 | 2016-01 → 2026-05 | MSCI EM ETF proxy |
| `atlas.atlas_index_metrics_daily` | 264,203 | 2016-04 → 2026-05 | RS series (rs_3m_nifty500) for India indices |
| `atlas.atlas_macro_daily.usdinr` | 2,704 populated | 2016-01 → 2026-05 | Per-day FX conversion for USD baselines |

---

## 9 Baselines

| # | baseline_code | Label | Source table | Source filter | RS source | FX adjust |
|---|---|---|---|---|---|---|
| 1 | `NIFTY_50` | Nifty 50 | `de_index_prices` | `index_code = 'NIFTY 50'` | `atlas_index_metrics_daily` | No |
| 2 | `NIFTY_100` | Nifty 100 | `de_index_prices` | `index_code = 'NIFTY 100'` | `atlas_index_metrics_daily` | No |
| 3 | `NIFTY_MIDCAP_150` | Nifty Midcap 150 | `de_index_prices` | `index_code = 'NIFTY MIDCAP 150'` | `atlas_index_metrics_daily` | No |
| 4 | `NIFTY_SMLCAP_250` | Nifty Smallcap 250 | `de_index_prices` | `index_code = 'NIFTY SMLCAP 250'` | `atlas_index_metrics_daily` | No |
| 5 | `NIFTY_500` | Nifty 500 | `de_index_prices` | `index_code = 'NIFTY 500'` | `atlas_index_metrics_daily` | No |
| 6 | `GOLD` | Gold (GOLDBEES) | `de_etf_ohlcv` | `ticker = 'GOLDBEES'` | Computed from ret vs Nifty 500 | No (already INR) |
| 7 | `SP500` | S&P 500 | `de_global_prices` | `ticker = '^GSPC'` | Computed from ret vs Nifty 500 | Yes (USD × usdinr) |
| 8 | `MSCI_WORLD` | MSCI World (URTH) | `de_global_prices` | `ticker = 'URTH'` | Computed from ret vs Nifty 500 | Yes (USD × usdinr) |
| 9 | `MSCI_EM` | MSCI EM (VWO) | `de_global_prices` | `ticker = 'VWO'` | Computed from ret vs Nifty 500 | Yes (USD × usdinr) |

---

## JSONB array shapes per row

### price_series (180 elements)
```json
[
  {"d": "2025-11-29", "o": 23800.50, "h": 23950.00, "l": 23750.00, "c": 23910.00},
  ...
]
```
For index baselines: raw close from `de_index_prices`.
For GOLDBEES: raw close from `de_etf_ohlcv`.
For USD baselines: `close × usdinr` per-day from `atlas_macro_daily`.

### rs_series (180 elements)
```json
[
  {"d": "2025-11-29", "v": 0.0312},
  ...
]
```
RS value = excess return vs Nifty 500 over 63 trading days (3 months).
- For India indices: `rs_3m_nifty500` from `atlas_index_metrics_daily` (pre-computed).
- For non-index baselines (Gold, SP500, URTH, VWO): computed as
  `(baseline_close_T / baseline_close_T-63 - 1) - (nifty500_close_T / nifty500_close_T-63 - 1)`.

### volume_series (180 elements)
```json
[
  {"d": "2025-11-29", "v": 154820000, "up": true},
  ...
]
```
`up = true` if close >= previous close. Only available for ETF/global baselines that have volume.
For index baselines (`de_index_prices`): volume if available, NULL otherwise.

### ma20_series (180 elements)
```json
[
  {"d": "2025-11-29", "v": 23750.40},
  ...
]
```
20-day rolling average of close price (requires 20 extra lookback rows in CTE).
NULL for first 19 rows in history.

### rs_new_high_dates / rs_new_low_dates (sparse arrays — variable length)
```json
["2025-12-15", "2026-01-08", "2026-02-03"]
```
Dates within the 180-day window where rs_series hit a new running high/low
vs the prior 90 calendar days. Used to render RS new-high/low diamonds on the price pane.

---

## Scalar fields per row

| Column | Type | Computation |
|---|---|---|
| `support_level` | numeric | MIN(close) over last 180 trading days (simple S/R approximation) |
| `resistance_level` | numeric | MAX(close) over last 180 trading days |
| `latest_close` | numeric | Close on as_of_date |
| `rs_latest` | numeric | Latest rs value (last element of rs_series) |
| `rs_delta_3m` | numeric | rs_latest − rs_series[0] (3-month RS change) |
| `refreshed_at` | timestamptz | NOW() at refresh time |

---

## RS computation for non-index baselines

For baselines sourced from `de_global_prices` or `de_etf_ohlcv`, the RS vs Nifty 500
is NOT pre-computed in `atlas_index_metrics_daily`. Computation:

```
rs_3m(t) = (close_baseline(t) / close_baseline(t-63)) − (close_n500(t) / close_n500(t-63)) − 1
```

Where close values are in the same currency (INR for all). The Nifty 500 close is pulled
from `de_index_prices` with `index_code = 'NIFTY 500'`.

Edge cases:
- NULL close on any day: rs = NULL for that date (propagated explicitly).
- No usdinr for a date: use previous available usdinr (LAST_VALUE within 5-day gap tolerance).
- Gaps > 5 trading days with no usdinr: NULL close_inr, NULL rs.

---

## S/R level methodology

Simple last-180-day high (R) and low (S) of the INR-adjusted close price series.
This is explicitly an approximation — production pivot-level S/R analysis is deferred.
Both values are stored as scalars per row so the frontend can render the horizontal lines.

---

## Coverage by baseline

| Baseline | Data from | 5-year coverage (≥2020-01-01) | Notes |
|---|---|---|---|
| Nifty 50/100/MC150/SC250/500 | 2016-04 | Full | `de_index_prices` + `atlas_index_metrics_daily` |
| GOLDBEES | 2016-04-01 | Full | `de_etf_ohlcv` |
| S&P 500 | 1928-01-02 | Full | `de_global_prices` |
| MSCI World (URTH) | 2012-01 | Full | `de_global_prices` |
| MSCI EM (VWO) | 2016-01 | Full since 2020 | `de_global_prices` |

All 9 baselines have continuous history ≥ 2020-01-01. DoD criterion met.

---

## Expected row count

- Date spine: 2020-01-01 → 2026-05-27 ≈ 1,644 trading days
- Baselines: 9
- Total: 9 × 1,644 ≈ **14,796 rows**
- MV size estimate: 14,796 × ~20KB average JSONB = ~296MB (acceptable for Supabase)

---

## Refresh strategy

- `WITH NO DATA` on creation
- `CREATE UNIQUE INDEX` on `(as_of_date, baseline_code)` — required for CONCURRENTLY
- `REFRESH MATERIALIZED VIEW` on first build (blocking; expect 60–120s on t3.large)
- `pg_cron` `mv_markets_rs_detail_charts_nightly` at `35 14 * * *` (20:35 IST = 14:35 UTC)
  - After `mv_india_pulse_nightly` (20:30 IST) and `atlas_macro_nightly` (20:15 IST)
  - `REFRESH MATERIALIZED VIEW CONCURRENTLY`

---

## Performance notes

- The CTE date spine is bounded to `>= '2020-01-01'`
- Each baseline's 180-day window uses a correlated window function, not a subquery per date
- The 20-day MA requires `ROWS BETWEEN 20 PRECEDING AND CURRENT ROW` on ordered data
- No Python/application-layer processing — all SQL window functions
- EXPLAIN ANALYZE expected cost: medium (< 5s on Supabase shared compute)

---

## Design decisions

| ID | Decision |
|---|---|
| DD1 | Row per (date, baseline) not per date. Avoids 9-JSONB-array nesting; each row is independently refreshable and queryable. |
| DD2 | 180 trading days per row (not 252/365). Balances JSONB size vs chart usability. Frontend window control (1M/3M/6M/12M) applies client-side slice on the 180-element array. |
| DD3 | RS computed as 3-month excess return (63 trading days). Matches `rs_3m_nifty500` in `atlas_index_metrics_daily` for India indices; same formula applied to non-index baselines for consistency. |
| DD4 | S/R = 180-day high/low. Simple but sufficient for the mockup's horizontal S/R line rendering. Production pivot-level S/R is a Phase E enhancement. |
| DD5 | USD baselines converted to INR per-day using `atlas_macro_daily.usdinr`. Last-known value within 5-day gap fills weekends/holidays where macro data absent. |
| DD6 | rs_new_high_dates: date where rs_series value > MAX(rs_series over prior 90 days). Threshold: new rolling high. Sparse array length varies; typically 3-15 per window. |
