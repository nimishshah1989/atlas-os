# Chunk: TV Screener Task 4 — Nightly TV Metrics Fetch + Upsert

## Data Scale
- `atlas.atlas_universe_stocks`: ~750 rows (loaded fully — under 1K, anything works)
- `atlas.tv_metrics`: upsert target, one row per symbol, ~750 rows
- TV screener batch: 100 symbols per API call (~8 batches for 750 symbols)

## Chosen Approach
- Pure Python fetch via `tradingview-screener` library (already in pyproject.toml)
- SQLAlchemy 2.0 sync engine (`atlas.db.get_engine`) with `text()` wrappers on all raw SQL
- ON CONFLICT (symbol) DO UPDATE for idempotent nightly upserts
- `iterrows()` acceptable here: max 100 rows per batch (well under 1K threshold)

## Wiki Patterns Checked
1. **Idempotent Upsert** (patterns/idempotent-upsert.md) — ON CONFLICT DO UPDATE on natural key (symbol); safe to re-run nightly
2. **SQLAlchemy Param-Cast Collision** (bug-patterns/sqlalchemy-param-cast-collision.md) — spec's `::jsonb` cast would collide with `:raw_payload` bind param; must use `CAST(:raw_payload AS jsonb)` instead

## Existing Code Reused
- `atlas/db.py` → `get_engine()` — sync engine, same pattern as all other modules
- `atlas/intelligence/conviction/persistence.py` — bulk upsert pattern: `text(SQL)` at module level, `conn.execute(sql, records)`
- `atlas/preflight.py` → `_scalar()` pattern: `conn.execute(text(sql), kwargs).scalar()`

## Key Bug Fixed vs Spec
The spec passes bare strings to `conn.execute()` — SQLAlchemy 2.0 requires `text()` wrapping.
The spec uses `::jsonb` cast inline — replaced with `CAST(:raw_payload AS jsonb)` to avoid param-cast collision.
The spec uses `WHERE symbol = ANY(:syms)` — valid with psycopg2 when passing a list; kept as-is.

## Edge Cases
- NULL/NaN from TV screener: `_label()` handles None and math.isnan explicitly
- Missing instrument_id: stored as NULL (symbol not yet in atlas_universe_stocks)
- Empty batch from TV API: logged as warning, skipped
- API failure on a batch: logged as exception, continues to next batch
- Volume values: cast to int only when pd.notna() — otherwise None

## Expected Runtime on t3.large (2 vCPU, 8GB RAM)
- 750 symbols / 100 per batch = 8 batches
- TV API call: ~1-2s per batch
- DB upsert per batch: <100ms
- Total: ~15-20s per nightly run

## Files Created
- `atlas/tv/screener.py`
- `tests/tv/test_screener.py`
- `atlas/tv/__init__.py` (updated with import)
