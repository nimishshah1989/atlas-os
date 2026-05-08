# Chunk M7-T9 Approach: runner.py — Nightly Paper Trading Orchestrator

## Data Scale
- strategy_configs: 15 rows (trivial)
- decisions tables: ~500 stocks, ~100 ETFs, ~150 funds per day (all < 1K; in-memory is fine)
- trades per run: ~15 strategies × ~5-20 trades = max ~300 rows/day
- overlap pairs: C(15,2) = 105 pairs/day
- holdings table: max 15 × 20 positions = 300 rows

All under 1K rows per operation. Pandas in-memory is acceptable. No chunking needed.

## Approach
- Sync psycopg2 path throughout (no asyncio)
- Fetch decisions ONCE per tier (3 DB calls), not per strategy (15 calls)
- `open_compute_session(engine)` yields a SQLAlchemy Connection; `pd.read_sql` works on it
- `get_engine` is in `atlas/db.py`, already imported by `atlas/compute/_session.py`; runner imports from `_session` only
- `fetch_decisions` signature: `(conn: Connection, tier, today)` — must be called inside `open_compute_session` context
- Overlap matrix uses `upper_triangle_pairs` which enforces canonical order (str(a) < str(b)) per CHECK constraint

## Wiki Patterns Checked
- Idempotent Upsert: ON CONFLICT DO UPDATE used in write_trades, record_daily_performance, overlap matrix
- Pipeline ABC Orchestration: runner.py is the orchestrator; sub-functions are the sub-pipelines
- Per-Day Query Loop (bug): avoided by fetching all 3 tiers once outside strategy loop

## Existing Code Reused
- `atlas/compute/_session.py`: `open_compute_session`, `bulk_upsert`
- `atlas/simulation/core/paper_trader.py`: all 7 functions imported directly
- `atlas/simulation/core/overlap.py`: `jaccard_similarity`, `upper_triangle_pairs`
- `atlas/simulation/strategies/loader.py`: `load_all_configs`, `StrategyConfig`

## Edge Cases
- strategy_id not in DB: log warning and skip (don't crash the run)
- tier with no decisions: check_decisions_exist logs warning but doesn't raise (guard is informational)
- empty holdings: `_compute_total_value` returns base_value (10M)
- blend tier: concat stocks + etf DataFrames; del + gc.collect() after each to avoid OOM
- regime = None in DB: fallback to "Constructive"
- `daily_return=0.0`: intentional placeholder; metrics.py (Task 10) backfills from consecutive total_value

## Expected Runtime on t3.large
- 3 DB fetches (decisions): ~200ms
- 15 × (load_holdings + write_trades + update_holdings + reload_holdings + record_perf): ~2s
- Overlap matrix: 105 upserts in one session: ~300ms
- Total: ~3-4 seconds per nightly run

## Import Note
`get_engine` is in `atlas/db.py`. `open_compute_session` (from `atlas/compute/_session.py`) already imports and re-exports it internally. runner.py only needs `from atlas.compute._session import open_compute_session` — no direct `get_engine` import required since engine is passed in by the caller (`scripts/m7_daily.py`).
