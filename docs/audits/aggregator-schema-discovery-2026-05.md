# Aggregator Schema Discovery — 2026-05-19

## Problem
Three aggregators in `atlas/intelligence/aggregations/` reference non-existent tables,
leaving `atlas_sector_state_v2`, `atlas_fund_state_v2`, `atlas_etf_state_v2` permanently
empty (0 rows each).

## Fund Holdings — No raw holdings table exists

**Finding:** No table has `(mstar_id, as_of_date, instrument_id, weight_pct)` shape.

The fund pipeline computes composition/holdings at the **monthly fund level** and stores
results in `atlas_fund_lens_monthly`:

| Column | Type | Notes |
|---|---|---|
| mstar_id | varchar | fund key |
| as_of_date | date | monthly disclosure date |
| aligned_aum_pct | numeric | % of AUM in stage-2 holdings |
| avoid_aum_pct | numeric | % in stage-4 |
| composition_state | varchar | Aligned / Mixed / Misaligned |
| holdings_state | varchar | Strong-Holdings / Weak-Holdings |
| strong_aum_pct | numeric | |
| weak_aum_pct | numeric | |

- **3,506 rows**, date range 2026-01-31 to 2026-05-04
- No per-instrument weight rows. The existing lens pipeline already aggregated.

`atlas_fund_holdings_changes` stores entry/exit events (not weights). Not usable
as a holdings panel.

**Resolution:** `load_fund_holdings_panel` redefines its output to match
`atlas_fund_lens_monthly` shape (one row per fund-month). `aggregate_fund_composition`
passes through the already-computed states directly.

## ETF Holdings — No raw holdings table exists

**Finding:** No `atlas_etf_holdings` or similar table.

ETF state is stored in `atlas_etf_states_daily` (279,897 rows, 2016-04-07 to
2026-05-18) with `rs_state`, `momentum_state`. The current `atlas_etf_signal_unified`
view maps these to approximate pct_stage_2/3/4.

`atlas_universe_etfs` has metadata (ticker, theme, linked_index) for 126 ETFs.

**Resolution:** `load_etf_holdings_panel` reads from `atlas_etf_states_daily` directly.
`aggregate_etf_states` maps rs_state/momentum_state to Weinstein states, producing
etf-day rows for `atlas_etf_state_v2`.

## Market Cap for Sector Weighting

**Finding:** No `market_cap_inr` column anywhere in the atlas schema.

`atlas_universe_stocks` has no market cap column. `atlas_stock_metrics_daily` (1,390,535
rows) has RS ranks, returns, EMAs — but no market cap.

**Resolution:** Sector weighting falls back to **equal-weight** (all market_cap = 1.0).
This is honest: claiming market-cap weighting when no market cap data exists would be
fabricated. Equal-weight aggregation is clearly documented in the sector aggregator. The
`market_cap` column in the panel query is replaced with a constant 1.0.

## Stock State Availability

- `atlas_stock_state_daily`: 276,969 rows, 2023-01-02 to 2026-05-18, classifier
  `v2.0-validated`. 747 stocks with sector on 2026-05-18.
- `atlas_universe_stocks`: 750 rows, sector populated on all.

## v2 Table Status

All three v2 tables: **0 rows** (confirmed). Schema matches aggregator output columns
exactly. Natural key constraints exist:
- `atlas_sector_state_v2`: UNIQUE (sector, date)
- `atlas_fund_state_v2`: UNIQUE (mstar_id, date)
- `atlas_etf_state_v2`: UNIQUE (etf_ticker, date)

## Implementation Plan

1. **sector.py** — remove `market_cap_inr` from SQL, add `1 AS market_cap` constant.
   Equal-weight. No other changes needed.
2. **fund.py** — rewrite `_HOLDINGS_SQL` to read `atlas_fund_lens_monthly`. Rewrite
   `aggregate_fund_composition` to pass through pre-computed states.
3. **etf.py** — rewrite `_HOLDINGS_SQL` to read `atlas_etf_states_daily`. Rewrite
   `aggregate_etf_states` to map existing states to v2 output shape.
4. Tests — update column names in synthetic fixtures to match new panel shape.
5. Seed 2026-05-18 data before view swap.
6. Migration 089 — redefine unified views to read v2 tables.
