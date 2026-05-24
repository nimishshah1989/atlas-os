# Chunk T1.8 — persistence.py approach

## Task
Write `atlas/intelligence/states/persistence.py` — upsert state-classifier panel
into `atlas.atlas_stock_state_daily` (migration 072).

## Data scale
Migration 072 creates a per-(instrument_id, date) table. At universe scale
(~500 NSE stocks × 252 trading days) = ~126 000 rows/year. Single daily run
inserts ~500 rows. Well under the 1K threshold where "anything works".

## Approach

### SQL vs Python
Single-panel insert (~500 rows) is tiny. `conn.execute(text(upsert_sql), params_list)`
via SQLAlchemy core is the right choice — no ORM overhead, no pandas overhead,
driver handles batching.

### Idempotency
`ON CONFLICT (instrument_id, date) DO UPDATE SET …` — matches the Idempotent Upsert
wiki pattern (45x referenced). The PK is `(instrument_id, date)` per migration 072.

### Within-batch deduplication
Per the Batch INSERT Within-Batch Duplicates bug pattern: deduplicate by
`(instrument_id, date)` before the INSERT. The spec's panel comes from
`classify_state_panel` which produces one row per stock per run date, but the
guard is cheap and prevents CardinalityViolationError if a caller ever passes
a multi-date panel with duplicate natural keys.

### Early-exit on empty panel
Test 4 requires `persist_state_panel(None, empty_df)` returns 0 without
touching the DB. Guard must be the very first statement before any DB call.

### numpy scalar conversion
Panel cells may be numpy int64 / float64. Some DB drivers reject numpy scalars.
Use `v.item()` on any value that has the `.item()` method (numpy scalars do;
Python scalars don't).

### Optional columns
Seven optional columns (dwell_percentile, within_state_rank, rs_rank_12m,
close_vs_sma_{50,150,200}, sma_200_slope, volume_ratio_50d, distribution_days)
map to None when absent from the panel or when the value is NaN.

## Wiki patterns checked
- Idempotent Upsert — ON CONFLICT DO UPDATE on PK. Followed exactly.
- Batch INSERT Within-Batch Duplicates — deduplicate by (instrument_id, date)
  before INSERT.

## Existing code being reused
- conftest.py db_engine fixture (session-scoped SQLAlchemy Engine)
- Migration 072 PK, CHECK constraints, column list

## Edge cases
- Empty panel: early return 0, no DB call
- NaN optional fields: mapped to None (SQL NULL)
- numpy scalars: `.item()` conversion at param-build time
- Duplicate rows in same panel: last-row-wins dedup by natural key
- `pd.isna()` returns True for np.nan, None, pd.NaT — covers all missing cases

## Expected runtime
500 rows, single `executemany`-style call via SQLAlchemy Core: < 100 ms on
t3.large. No concern at this scale.

## Files
- `atlas/intelligence/states/persistence.py` (new)
- `tests/intelligence/states/test_persistence.py` (new)
