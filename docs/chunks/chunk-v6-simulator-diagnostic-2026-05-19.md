# v6 Simulator Diagnostic — Root Cause Analysis
## Phase 9 Walk-Forward Implausible Results

**Date:** 2026-05-19  
**Analyst:** Forge Implementer  
**Scope:** `atlas/trading/v6/simulator.py`, `scripts/v6_walk_forward.py`, DB schema  
**Confidence:** 9/10

---

## Executive Summary

The Phase 9 walk-forward results (54.7% CAGR/2021, 51.7% CAGR/2022, 67.6%/2023, Calmar 372) are not real outperformance — they are the compounded output of **four concurrent data and methodology bugs**. The three most impactful are: (1) corrupt OHLCV prices that create ret_1d values of 70x-530x for Nifty 500 blue-chips like SBIN and NTPC, inflating forward returns; (2) a single 2026-05-06 universe snapshot with no point-in-time filter, creating survivorship bias in every historical period; and (3) a signal database with `rs_3m_nifty500` NULL for all 1.39M rows and critical columns missing for all of 2022, reducing the composite to a pure momentum sort. A fourth structural issue — monthly-only NAV points — suppresses reported MDD by roughly 5-10x. None of the reported numbers can be trusted until these four issues are fixed.

---

## Detailed Findings

### Finding 1 — CRITICAL: Corrupt OHLCV prices produce insane forward returns

**Evidence:**  
The `public.de_equity_ohlcv` table contains rows where `close` is ~11,000-11,500 (Nifty futures/index level) instead of the actual equity price (~150-500). These appear to be data-entry errors from a futures feed being written to the equity table.

| Symbol | Date | Corrupt close | Actual close | Implied ret_1d |
|---|---|---|---|---|
| SBIN | 2020-05-25 | 11,000 | ~151 | +71.9x |
| SBIN | 2020-04-06 | 10,862 | ~186 | +57.3x |
| IDFCFIRSTB | 2022-01-26 | 11,049 | ~45 | +243.5x |
| NTPC | 2024-03-26 | 64.6x | — | — |
| IFCI | multiple | 109-180x | — | — |

`atlas_stock_metrics_daily.realized_vol_63` inherits these corrupt returns:
- SBIN at 2021-01-29: `realized_vol_63 = 7530.75%`
- IDFCFIRSTB: `realized_vol_63 = 22116.86%`
- IFCI: `realized_vol_63 = 33277.39%`

Corruption scale: ~150 rows/year with `close > 10,000 AND volume < 1,000`.

**Impact on simulator:**
- `_fetch_forward_returns` uses `ret_1d` directly — one corrupt day in a selected stock's holding period can contribute `weight × 71.9 = 256%` to `book_return` in a single period.
- SBIN, NTPC, NTPC, NHPC all pass the ADV ≥ 5 crore filter and can enter the portfolio.
- `_fetch_returns_panel` for HRP uses the same `ret_1d`. One corrupt stock in the 28-stock cohort inflates `realized_portfolio_vol` → `vol_scalar → 0` → `gross → FLOOR 0.30`. This suppresses some periods and inflates others randomly.

### Finding 2 — CRITICAL: Non-point-in-time universe (survivorship bias)

**Evidence:**  
`atlas_universe_stocks` has exactly **one snapshot** dated `effective_from = 2026-05-06`. All 500 rows have this single date. The `get_investable()` query applies **no `effective_from`/`effective_to` filter** — it returns all current (2026) Nifty 500 members that have any OHLCV data in the lookback window.

Scale confirmed:
- Current Nifty 500 members with OHLCV data in 2021: **409 of 500**
- Current Nifty 500 members with OHLCV data in 2022: **426 of 500**

The missing 91-74 are either newly listed stocks or stocks that joined the index after their historical period. The survivorship bias works in the opposite direction that's usually most dangerous (new listings are included, delisted losers also excluded), but the 2021 universe is **not the actual 2021 Nifty 500** — it's "which current Nifty 500 members existed then."

The note in `universe.py` acknowledges this: *"When Plan 1A D1 backfill lands, swap the in_nifty_500 boolean to the PIT atlas_index_membership table"* — but `atlas_v6_index_membership` is not yet populated with historical data.

### Finding 3 — CRITICAL: Degenerate signal panel (56% of composite weight non-functional)

**Evidence — rs_3m_nifty500 (NULL for all 1.39M rows):**
```sql
SELECT COUNT(*), COUNT(rs_3m_nifty500) FROM atlas.atlas_stock_metrics_daily;
-- Result: (1390535, 0)  ← rs_3m_nifty500 is NEVER populated
```

This column drives two signals:
- `beta_alpha_63d` (weight 0.15): `= rs_3m_nifty500 or 0.0` → always 0 for ALL stocks
- `residual_momentum` (weight 0.13): same → always 0 for ALL stocks

**Evidence — 2022 data gap (Jan through Nov 2022 = zero rows):**

| Month | ret_12m | ema_200_stock | max_drawdown_252 |
|---|---|---|---|
| 2022-01 | 0 | 0 | 0 |
| 2022-02 through 2022-09 | 0 | 0 | 0 |
| 2022-10 | 0 | 5,170 | 0 |
| 2022-11 | 0 | 11,827 | 0 |
| 2022-12 | 1,220 | 12,195 | 1,832 |

For the 2022 OOS year, 56% of designed composite weight is degenerate:

| Signal | Weight | Status for 2022 |
|---|---|---|
| `natr_14` | 0.15 | ACTIVE |
| `beta_alpha_63d` | 0.15 | DEAD — rs_3m always NULL |
| `mom_low_vol` | 0.15 | DEAD — ret_12m NULL Jan-Nov |
| `residual_momentum` | 0.13 | DEAD — rs_3m always NULL |
| `proximity_52wh` | 0.13 | CONSTANT=1.0 — ema_200 NULL |
| `industry_rs` | 0.13 | ACTIVE (uses ret_3m) |
| `fip_smoothness` | 0.05 | ACTIVE (uses ret_1m) |
| `bab` | 0.05 | ACTIVE (uses vol_ratio_63) |
| `quality_proxy` | 0.05 | PARTIAL (mdd missing) |

Effective active weight: 38%. The composite degenerates to a pure momentum + ATR-proximity + BAB sort.

**Consequence:** In 2022, the composite selects the highest-momentum names at the June/July 2022 market bottom, which then capture the sharp August 2022 rally. This is inadvertent "buy the dip" look-ahead, not genuine signal alpha.

### Finding 4 — CRITICAL: Monthly NAV granularity suppresses MDD by 5-10x

**Evidence:**  
`equity_curve` is appended **once per period** (monthly). `_compute_aggregate_stats` computes drawdown from this monthly series. Intra-month price moves — including -8% drops that recover by month-end — are invisible.

2022 Nifty 500 monthly-only view vs actual:
- Month-end-to-month-end MDD: `-10.73%` (simulator would see similar)
- Actual Nifty 500 intra-year MDD: approximately `-17%` peak-to-trough (includes the Jan-Jun 2022 drawdown that partially recovered by Aug)

A portfolio with genuine -12% intra-month drawdown in June 2022 appears to have -5.8% MDD in the simulator because it only samples the month-end NAV. The reported Calmar of 372 for 2021 (CAGR/MDD = 54.7% / 0.15%) is a mathematical artifact of an MDD that is essentially the rounding error from a single bad month-end.

### Finding 5 — CONCERN: Corrupt realized_vol produces erratic gross multiplier

The `vol_targeted_gross` function uses realized_vol from the HRP returns panel. When any cohort stock has corrupt `ret_1d` in the 252-day lookback, `realized_portfolio_vol` can become enormous, pinning `gross` to `FLOOR = 0.30`. In other periods where the cohort is "clean," gross may reach `CEILING = 1.10`.

This is not a systematic inflation or deflation — it introduces period-level noise that makes the backtest unreliable. It does not explain the directional inflation but does explain why Calmar ratios vary wildly (372 vs 6.34 across OOS years).

### Findings 6-8 — OK

- **Slippage:** Correctly computed and subtracted. ~0.3% per rebalance = ~3.6% annual drag.
- **CAGR arithmetic:** Correct. The error is in the inputs (`period.book_return`), not the aggregation math.
- **Benchmark return:** `nifty500_close` is 96% populated (987/1031 rows) and `_benchmark_return_compat` correctly uses nearest-date lookups. 2022 benchmark was correctly computed as +1.6%.

---

## Suggested Fix List (not implemented)

**FIX 1 (mandatory before any further backtest):** Clean corrupt OHLCV prices  
Filter: `close > 5000 AND volume < 100 AND ABS(close / LAG(close) - 1) > 5.0`. Null-out those rows in `de_equity_ohlcv` and recompute `ret_1d` in `atlas_stock_metrics_daily`. Or as a faster mitigation: winsorize `ret_1d` at ±0.25 in all simulator queries before compounding.

**FIX 2 (mandatory before any further backtest):** Point-in-time universe  
Populate `atlas_v6_index_membership` with quarterly NSE Nifty 500 changes (available from NSE circular archives). `get_investable()` must filter `WHERE date BETWEEN effective_from AND COALESCE(effective_to, 'infinity')`.

**FIX 3 (mandatory before 2022-2024 OOS is valid):** Backfill rs_3m_nifty500  
Compute `(stock_ret_3m - nifty500_ret_3m)` for all historical dates and write to `atlas_stock_metrics_daily`. This restores `beta_alpha_63d` and `residual_momentum` signals.

**FIX 4 (mandatory before 2022 OOS is valid):** Backfill 2022 missing columns  
`ret_12m`, `ema_200_stock`, `max_drawdown_252` are all zero-filled for Jan-Nov 2022. Run a targeted backfill compute for that gap window. These are standard rolling computations derivable from the existing OHLCV data.

**FIX 5 (mandatory for honest MDD reporting):** Daily NAV equity curve  
Build daily equity curve from `ret_1d` for all held positions using their daily weights. Use this for MDD. Monthly MDD is not a valid risk metric for an equity long book.

**FIX 6 (concern-level):** Winsorize ret_1d in returns panel for HRP  
Cap `ret_1d` at ±0.25 before building the covariance matrix. This prevents one corrupt row from pinning the gross to the floor.

---

## Confidence Assessment

Confidence: **9/10**

The four critical findings are confirmed by direct SQL evidence (row counts, actual values, realized_vol numbers). The only uncertainty is whether the corrupt OHLCV prices actually get selected into the forward returns window for a given period — this depends on which stocks the composite selects, which varies per rebalance date. But given that SBIN, NTPC, and NHPC (all high-ADV Nifty 50 members) are in the corrupt list and all likely appear in any momentum-based selection in bullish periods, this is highly likely to be inflating at least some periods.

The fix ordering is: (1) FIX 2 (PIT universe) + FIX 1 (clean OHLCV) + FIX 5 (daily MDD) simultaneously, then (2) FIX 3 + FIX 4 (backfill signals), then (3) re-run Phase 9 walk-forward with clean data.
