# B.1 Macro Ingest FIX LOOP Approach

chunk: B.1-fix
project: atlas-os
date: 2026-05-27
status: in-progress

## Verified source state (curl-tested)

| Column | Original Source | Status | Fix |
|--------|----------------|--------|-----|
| risk_free_91d | FRED INTGSB91D156N | 400 - series does not exist | Use IRSTCI01INM156N (call money, monthly, 2016-2026) |
| fii_cash_equity_flow_cr | NSE archives all_foii_dii.csv | 404 confirmed from Mac AND EC2 | BLOCKED - see details below |
| dii_flow | Same source | 404 confirmed | BLOCKED same as fii |
| vix_9d | NSE archives hist_vix_data.csv | 404 confirmed | Yahoo Finance ^INDIAVIX daily API |
| india_10y_yield | FRED INDIRLTLT01STM | OK but monthly only | Forward-fill added |
| cpi_yoy | Bundled data | OK | Forward-fill already implemented |
| brent_inr | Derived | brent_usd in SERIES_MAP causes col-not-exist error | Remove brent_usd from SERIES_MAP |
| us_10y_yield | FRED DGS10 | OK daily | No change |

## FII/DII BLOCKED: Source Investigation

All attempted sources for FII/DII historical data failed:
- `https://archives.nseindia.com/content/fo/all_foii_dii.csv`: 404 from EC2 confirmed
- `https://www.nseindia.com/api/historicalOR/foCash/historicalcontract`: 404
- NSE fiidiiTradeReact: Returns today's 2 rows only (no historical params honored)
- Moneycontrol pricefeed/fii_dii: Empty response
- BSE API: Timeout
- NSDL: Connection error
- SEBI statistics XLS: 404

NSE home page returns 403 (both Mac and EC2), preventing session-based cookie extraction.

**Decision**: FII/DII historical backfill is BLOCKED. The React API endpoint gives current-day data and will be used for incremental/nightly updates only. The column will remain NULL for historical data. G3 requirement of ≥95% non-null CANNOT be met for this column via free public sources.

## Fix 1: risk_free_91d — IRSTCI01INM156N

Series: `IRSTCI01INM156N` — "Interest Rates: Immediate Rates (< 24 Hours): Call Money/Interbank"
- Verified on EC2 with actual FRED_API_KEY: returns 123 rows from 2016 through 2026-03
- Monthly frequency — requires forward-fill to daily
- Semantic note: Call money/overnight rate ≈ 91-day T-bill rate for macro context (both track RBI policy rate closely)
- Documented in docstring as a proxy

## Fix 2: NSE VIX — Yahoo Finance ^INDIAVIX

Source: `https://query2.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?period1={start}&period2={end}&interval=1d`
- Verified: 2568 rows from 2016-01-01 to 2026-05-26 with daily interval
- No auth required
- Clean JSON response; timestamps are Unix epoch
- Covers full atlas scope from 2016

## Fix 3: Monthly forward-fill

Columns requiring forward-fill: `india_10y_yield`, `risk_free_91d`, `cpi_yoy`
CPI already has carry-forward in mospi_cpi_ingest.py (via UPDATE WHERE date >= first_of_month).
Add equivalent `forward_fill_monthly_col(col, engine)` in runner.py using SQL window:
```sql
WITH last_known AS (
  SELECT date,
         last_value(col_placeholder IGNORE NULLS) OVER (ORDER BY date ROWS UNBOUNDED PRECEDING) AS filled
  FROM atlas.atlas_macro_daily
)
UPDATE atlas.atlas_macro_daily t
SET col_placeholder = lk.filled
FROM last_known lk
WHERE t.date = lk.date AND t.col_placeholder IS NULL AND lk.filled IS NOT NULL;
```
Note: PostgreSQL doesn't support IGNORE NULLS in last_value. Use a correlated subquery approach instead.

## Fix 4: brent_usd removed from SERIES_MAP

`brent_usd` is NOT a column in `atlas_macro_daily`. Remove it from SERIES_MAP in fred_ingest.py.
The runner.py already fetches brent_usd separately via `fetch_series("DCOILBRENTEU", ...)` and
holds it in memory — that's the correct pattern. The SERIES_MAP upsert path was erroneously including it.

Remove from:
- `SERIES_MAP` in fred_ingest.py
- `_SAFE_COLS` in fred_ingest.py (no longer needed there)

## VIX nse_vix_ingest.py rewrite

Switch from CSV download to Yahoo Finance JSON API:
1. `fetch_vix_from_yahoo(start, end)` — returns DataFrame with ["date", "india_vix"]
2. Keep `compute_vix_9d_ema()` unchanged
3. Keep `upsert_vix()` unchanged
4. `run_all()` calls fetch_vix_from_yahoo instead of fetch_vix_csv

Test fixtures: use existing fixture CSV for parse tests (still needed for parse_vix_csv
which may be called with a local CSV path). Add new test for fetch_vix_from_yahoo using mock.

## Expected coverage post-fix

| Column | Expected coverage | Source depth |
|--------|------------------|-------------|
| us_10y_yield | ≥98% | FRED DGS10 daily, no weekends |
| india_10y_yield | ≥95% after forward-fill | FRED monthly + ffill |
| risk_free_91d | ≥90% after forward-fill | FRED monthly 123 rows, 2016-2026-03 |
| fii_cash_equity_flow_cr | ~0% (BLOCKED) | NSE historical unreachable |
| dii_flow | ~0% (BLOCKED) | Same |
| cpi_yoy | ≥95% | Bundled monthly + carry-forward |
| brent_inr | ≥90% | FRED daily × usdinr |
| vix_9d | ≥98% | Yahoo Finance daily, 2016+ |

## Expected runtime

- risk_free_91d: 1 FRED call + forward-fill SQL ~5s
- VIX: 1 Yahoo Finance call + EMA compute + upsert ~20s
- Forward-fill SQL per column: ~1s each
- Total: ~2 min
