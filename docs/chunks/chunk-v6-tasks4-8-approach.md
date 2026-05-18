# Approach: v6 Data Prerequisites Tasks 4–8

**Date:** 2026-05-19
**Chunk:** v6-tasks4-8 (D2-D6)
**Status:** planning

## Data scale
- `atlas_etf_metrics_daily`: instrument-level daily data, ~220 ETFs × days
- `atlas_stock_metrics_daily`: ~500 stocks × trading days, ~250K+ rows
- `atlas_instrument_master`: ~700 rows (master lookup)
- `atlas_governance_daily`: new table, starts empty
- `atlas_macro_daily`: new table, starts empty
- All new tables built by migration 080 (committed in prior tasks)

## Approach per task

### Task 4 (D2: ETF coverage + Yahoo backfill)
- `EtfCoverageChecker`: SQL MIN/MAX query on `atlas_etf_metrics_daily` joined to instrument master — under 1K result rows, SQL aggregation is correct
- `YahooBackfiller`: uses `yf.download`, inserts with ON CONFLICT DO NOTHING — idempotent
- yfinance 1.3.0 already installed. Plan specifies `>=0.2.40`, already satisfied.

### Task 5 (D3: Macro daily series)
- `UsdInrFetcher`, `DxyFetcher`: wrap `yf.download` with date window → 2-column DataFrame
- `FiiFlowFetcher`: `requests.get` + `pd.read_csv` on NSE CSV endpoint
- `IndiaTenYearFetcher`, `RiskFree91dFetcher`: placeholder stubs returning empty DF
- `BreadthComputer`: single SQL query with COUNT FILTER — pushes computation to Postgres, zero pandas memory
- `MacroDailyUpserter`: ON CONFLICT DO UPDATE on date primary key

### Task 6 (D4: F&O ban list)
- `FnoBanFetcher`: `requests.get` + `pd.read_csv`, parse Symbol column
- `FnoBanUpserter`: two-step SQL: SET true for banned, SET false for previously-banned-not-in-list
- Fixture: 3-row CSV with `Sr.No.,Symbol` header

### Task 7 (D5: Promoter pledge quarterly)
- `compute_pledge_ratio`: pure function, returns None on zero-total (NULL-safe)
- `parse_pledge_filing`: date parse + ratio calc per filing entry
- `PledgeQuarterIngester.ingest_filing`: forward-fills daily rows from effective_date through next_quarter_end - 1 day
- `_next_quarter_end(d)`: helper for quarter boundary calculation
- Day count: Q3 2024 (Sep 30) → next quarter end (Dec 31) - 1 = Dec 30 → 92 days

### Task 8 (D6: Auditor + promoter group master)
- `TOP_10_AUDITORS`: constant tuple of 13 auditor name prefixes
- `is_top_10_auditor`: fuzzy match by normalizing `&` → `and` then checking first-word overlap
- `parse_screener_html`: BeautifulSoup `.company-line` selector
- `GovernanceMasterUpserter.upsert`: ON CONFLICT DO UPDATE with `auditor_is_top_10` computed at write time
- `beautifulsoup4` is installed in venv (bs4 available); need to add to pyproject.toml

## Wiki patterns checked
- [Idempotent Upsert](wiki/patterns/idempotent-upsert.md) — ON CONFLICT pattern used throughout
- [Decimal Not Float](wiki/patterns/decimal-not-float.md) — financial values; plan uses Numeric columns, Python uses float for intermediate only
- [SQL Window Computation](wiki/patterns/sql-window-computation.md) — BreadthComputer uses COUNT FILTER in SQL

## Edge cases
- yfinance returns MultiIndex columns in newer versions — handle `.xs("Close", axis=1)` if needed
- NSE CSV column names may vary — use `next(c for c in df.columns if "symbol" in c.lower())`
- `pledge_ratio_pct` for TCS is 0.0 (not None) — `compute_pledge_ratio(5M, 0)` = 0.0, which is valid
- `_next_quarter_end` for Dec month returns Mar 31 of next year
- Forward-fill loop: 92 days for Q3 2024 (Sep 30 to Dec 30 inclusive)

## Expected runtime
- All tests are unit tests with mocked HTTP and in-memory/transactional DB
- ETF backfiller: real yfinance call would be <1s per symbol; tests mock it
- Pledge forward-fill: 92 SQL inserts per symbol — acceptable for quarterly batch

## Files in scope
- `atlas/data_prereqs/v6/etf_coverage.py` (new)
- `atlas/data_prereqs/v6/macro_daily.py` (new)
- `atlas/data_prereqs/v6/fno_ban.py` (new)
- `atlas/data_prereqs/v6/pledge.py` (new)
- `atlas/data_prereqs/v6/governance_master.py` (new)
- `tests/data_prereqs/v6/test_etf_coverage.py` (new)
- `tests/data_prereqs/v6/test_macro_daily.py` (new)
- `tests/data_prereqs/v6/test_fno_ban.py` (new)
- `tests/data_prereqs/v6/test_pledge.py` (new)
- `tests/data_prereqs/v6/test_governance_master.py` (new)
- `tests/data_prereqs/v6/fixtures/fno_ban_sample.csv` (new)
- `tests/data_prereqs/v6/fixtures/pledge_sample.json` (new)
- `tests/data_prereqs/v6/fixtures/screener_company_sample.html` (new)
- `pyproject.toml` (add beautifulsoup4)
