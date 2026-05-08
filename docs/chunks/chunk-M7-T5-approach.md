# M7 Task 5 — signal_adapter.py Approach

## Data Scale (from M2/M3 notes; EC2 unreachable locally)
- `de_ohlcv_daily`: ~2.3M rows (M2 milestone note), daily OHLCV for all NSE instruments
- `atlas_stock_decisions_daily`: ~100K-500K rows (estimate: ~2000 stocks × ~200 trading days)
- `atlas_etf_decisions_daily`: ~220 ETFs × ~200 days = ~44K rows
- `atlas_fund_decisions_daily`: ~2000+ funds × ~200 days = ~400K+ rows
- `de_mf_nav_history`: large, daily NAV for all mutual funds

At query time, results are filtered by `instrument_ids IN (...)` + date range → typically <10K rows in memory. No full table loads.

## Chosen Approach
- **SQL JOIN** between decisions table and price table (de_ohlcv_daily / de_mf_nav_history) — compute happens in Postgres, not Python
- `pd.read_sql(query, conn, params=...)` with `open_compute_session` for statement_timeout=0
- Results pivoted wide in pandas (date × instrument) after SQL fetch — result set is bounded by instruments × date range, well under 100K
- `np.ndarray` output for vectorbt compatibility

## Wiki Patterns Checked
- **SQLAlchemy Param-Cast Collision** — avoided `::type` casts in text(); no date casts needed here
- **Computation Boundary Pattern** — prices stay float64 for vectorbt (numpy internally); no Decimal needed at this read layer
- **Load All Then Compute** anti-pattern — avoided via WHERE clause on date range + instrument_ids IN list

## Existing Code Reused
- `open_compute_session` from `atlas/compute/_session.py` — handles statement_timeout=0 and rollback
- Pattern from `atlas/compute/decisions_stock.py` etc. for decisions table names

## Edge Cases
- Empty result from SQL JOIN → return SignalMatrix with shape (0,0); log warning for stocks/ETFs
- Missing prices (NULL close/nav) → warn via structlog, drop rows with `dropna(subset=["price"])`
- instruments list is empty → SQL `IN ()` would be invalid; caller responsibility to validate, but code handles gracefully via empty df path
- `pd.read_sql` with SQLAlchemy Connection: pandas >= 2.0 requires `conn.connection` (raw psycopg2) or engine directly; we pass `conn` but note fallback option
- pivot on empty df after dropna → handled by empty-check before pivot

## Notes on table name interpolation
`decisions_table` is f-string interpolated into `text()`. This is intentional — SQL doesn't allow parameterized table names. Only two valid values exist; caller validates. Risk is minimal, noted in docstring.

## Expected Runtime (t3.large, 2 vCPU, 8GB)
- Stock query for 5 instruments, 1 year: <1s (indexed on instrument_id + date)
- Fund query for 100 instruments, 2 years: 2-5s
- Pivot operations: <100ms (result sets are small)
