# B.1 Macro Ingest Approach

chunk: B.1
project: atlas-os
date: 2026-05-27
status: in-progress

## Task

Fill 8 NULL columns on `atlas.atlas_macro_daily` via 5 ingest scripts from free public sources.

## Actual Data Scale

atlas_macro_daily: ~2,600 rows (trading days 2016-04-07 to present).
All writes are upserts on date PK — safe to re-run.
Data volume is well under 1K rows per source per fetch — pandas is fine.

## Missing columns (verified against migration history)

Migration 097 added: `dii_flow`, `us_10y_yield`, `brent_inr`, `cpi_yoy`, `vix_9d`
NOT YET in DB: `india_10y_yield`, `fii_cash_equity_flow_cr`, `risk_free_91d`

Migration 099 must:
1. Add 3 missing columns to atlas_macro_daily
2. Register pg_cron job `atlas_macro_nightly`

## Chosen Approach

Scale: ~2,600 rows total. Well under 1K threshold.
Approach: Python upsert via `atlas.db.get_engine()` with `ON CONFLICT (date) DO UPDATE`.
No iterrows on large datasets — each source fetches once as DataFrame, then bulk-insert via `to_sql` with `method='multi'` or row-by-row (2,600 rows is tiny).

### Source map

| Column | Source | Series/URL | Auth |
|--------|--------|-----------|------|
| us_10y_yield | FRED API | DGS10 | FRED_API_KEY |
| india_10y_yield | FRED API | INDIRLTLT01STM | FRED_API_KEY |
| brent_usd (temp) | FRED API | DCOILBRENTEU | FRED_API_KEY |
| risk_free_91d | FRED API | INTGSB91D156N (91-day T-bill India proxy) | FRED_API_KEY |
| fii_cash_equity_flow_cr | NSE historical CSV | archives.nseindia.com FII/DII files | None (public) |
| dii_flow | NSE historical CSV | Same source | None (public) |
| cpi_yoy | MOSPI CPI data | Manual CPI index data | None (public) |
| vix_9d | NSE VIX historical | nseindia.com VIX download | None (public) |
| brent_inr | Derived = brent_usd × usdinr | From atlas_macro_daily.usdinr | None |

### FRED API key

No FRED key in `.env` on local Mac or EC2. Strategy:
- Implement with `os.environ.get("FRED_API_KEY", "")` — graceful degradation if missing
- Flag missing key in runner output
- For risk_free_91d: use FRED series `INTGSB91D156N` (India 91-day Government Securities)
  - Fallback: use 0.065 (6.5%) RBI benchmark as constant if FRED unavailable (document as proxy)

### NSE bhavcopy / FII-DII

NSE blocks direct scraping. Alternative: use pre-downloaded historical data from
the NSE FII/DII Historical Activity page. The actual production data source is:
`https://archives.nseindia.com/content/fo/all_foii_dii.csv` (single historical CSV)

Since NSE blocks unauthenticated requests and returns anti-bot responses, the
ingest script will:
1. Attempt direct download with proper User-Agent headers
2. Fall back to a documented fixture/manual path if blocked
3. Tests use fixture CSV files in `tests/ingest/macro/fixtures/`

### MOSPI CPI

MOSPI doesn't have a stable API. Use a hardcoded CPI dataset embedded in the
module (RBI/MOSPI combined CPI All-India from 2013 onwards). This is a bounded
~150-row monthly series that changes once per month — embedding is acceptable.
Document as "seeded from RBI DBIE CPI releases."

### NSE VIX

NSE VIX historical data is available via the NSE FTP/download endpoint.
Production URL: `https://www.nseindia.com/api/historical/vixhistory?data=[{...}]`
Use standard NSE session cookie approach with requests + session headers.
vix_9d = 9-day rolling backward EMA of India VIX (documented proxy — NSE does
not publish 9d VIX directly).

## Edge cases handled

- NULLs: FRED returns "." for missing observations — filter explicitly
- Weekends/holidays: atlas_macro_daily has trading days only; no gap for non-trading days
- MOSPI CPI is monthly — carry forward to fill daily rows via SQL forward-fill
- brent_inr: only computed where both brent_usd and usdinr are non-null
- Risk-free proxy: FRED `INTGSB91D156N` is monthly — carry forward same as CPI

## Wiki patterns applied

- Idempotent Upsert: ON CONFLICT (date) DO UPDATE for all writes
- Decimal Not Float: str->Decimal for all financial values at storage boundary
- Data Completeness Audit: log row counts before/after each source

## Expected runtime on t3.large

FRED 4 series × 10 years = ~4 API calls, ~5s each = ~20s
NSE FII/DII single CSV = ~10s download + ~5s parse
VIX historical = ~15s
CPI (embedded) = ~1s
Total upsert: 2,600 rows × 4 columns = trivial
**Estimated: 5-10 minutes including retries**
