# B.1 FII/DII Monthly Fix Approach

chunk: B.1-fii-dii-monthly
project: atlas-os
date: 2026-05-27
status: in-progress

## Problem

`fii_cash_equity_flow_cr` and `dii_flow` on `atlas.atlas_macro_daily` are at 0.04% coverage
(1 row out of ~2752). All NSE daily-historical endpoints are 404 or bot-blocked. Only
today's value is fetchable via the NSE React API.

## Approved Solution

Use monthly FII/DII net flow data, bundled as a static JSON in the repo, forward-filled to
daily rows — same pattern as `cpi_yoy` in `mospi_cpi_ingest.py`.

User direction: "FII/DII is available at a monthly level from multiple sources. Let's not get
stuck — basic FII/DII can be taken care of."

## Data Source

SEBI Monthly Bulletin / NSDL FPI Data (public, no auth required).
Source URL: https://www.sebi.gov.in/statistics/1311939932480.html (FII/FPI flows table)
and confirmed from multiple public aggregators including Groww, NDTV, MoneyControl.

The monthly FII net flow = Foreign Institutional Investors net (buy − sell) in cash equity.
The monthly DII net flow = Domestic Institutional Investors net (buy − sell) in cash equity.

Values are in ₹ Crore. Net flows for each month.

## Manual Bundle

Since NSDL/SEBI don't have a machine-readable API, the 120+ monthly values (2016-01
through 2026-04) are hand-curated from published sources (SEBI monthly bulletins, NSE
FII/DII activity pages, public financial portals) and embedded as a static list in
`atlas/ingest/macro/fii_dii_monthly_ingest.py`.

Source and bundle date documented in the module docstring.
Data verified against publicly available SEBI/NSE reports.

## Actual Data Scale

- atlas_macro_daily: ~2,752 rows (2016-01-01 to 2026-05-27)
- Monthly FII/DII: ~124 months (2016-01 to 2026-04)
- After forward-fill: each month's value propagates to all ~21 trading days
- Row-by-row upsert: 2,752 rows is well under 1K threshold — iterrows on 124 items is fine

## Approach

1. New module: `atlas/ingest/macro/fii_dii_monthly_ingest.py`
   - Bundled static list: `_BUNDLED_FII_DII_MONTHLY` as list[(year, month, fii_net_cr, dii_net_cr)]
   - `get_bundled_fii_dii_monthly() -> pd.DataFrame` — returns the monthly data
   - `upsert_fii_dii_monthly(df, engine)` — writes to atlas_macro_daily using the CPI
     carry-forward pattern: UPDATE WHERE date >= first_of_month AND date < first_of_next_month
   - `run_all(engine) -> int` — calls both, returns months processed

2. Update `atlas/ingest/macro/runner.py`:
   - Import `fii_dii_monthly_ingest`
   - Add step 2b: run `fii_dii_monthly_ingest.run_all(eng)` in both `run_backfill` and
     `run_incremental`
   - After step 2b: `_forward_fill_any_col("fii_cash_equity_flow_cr", eng, start)` and
     `_forward_fill_any_col("dii_flow", eng, start)` — add both to safe_cols frozenset
   - Remove the BLOCKED comment from step 2

3. Tests: `tests/ingest/macro/test_fii_dii_monthly_ingest.py`
   - ~10 months fixture data in `tests/ingest/macro/fixtures/fii_dii_monthly_sample.json`
   - Test: bundled data loads with correct columns
   - Test: upsert calls UPDATE SQL with correct month range params
   - Test: Decimal values stored, not float
   - Test: empty df returns 0
   - Test: run_all returns count

## Forward-Fill Strategy

After `upsert_fii_dii_monthly()`, call `_forward_fill_any_col()` for both cols.
This fills weekends/holidays within the month (already covered by the month-range UPDATE)
AND any gap months where data is NULL.

Need to add `fii_cash_equity_flow_cr` and `dii_flow` to `_forward_fill_any_col` safe_cols
frozenset in runner.py.

## Edge Cases

- NULLs: months with no data → skip (don't overwrite with NULL)
- Dec→Jan boundary: handled same as CPI (next_year = year + 1)
- Month-range UPDATE approach writes to ALL daily rows in that month — no date alignment issue
- 2026-05 current month: include latest available data (through 2026-04 confirmed, 2026-05 partial)

## Expected Runtime on t3.large

- Bundle parse: <1s (124 rows)
- 124 UPDATE statements: ~2s total
- Forward-fill 2 cols: ~1s each
- Total: <5s

## Wiki Patterns Applied

- Idempotent Upsert: month-range UPDATE is idempotent (same as CPI pattern)
- Decimal Not Float: str→Decimal at storage boundary
- Data Completeness Audit: log row counts before/after
