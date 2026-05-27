# Chunk: Strategy Lab Task 14 — FastAPI /api/trading/* endpoints

## Data scale
No query needed — these are read-only GET endpoints against leaderboard, genome,
position, insight, gene-pool, and config tables. All tables are written by the
nightly incubator and expected to hold O(100s) of genomes and O(1K) position rows
at most. SQL is the right engine; no Python aggregation needed.

## Chosen approach
Sync SQLAlchemy Engine pattern (same as atlas/api/strategies.py). No async session.
`engine.connect()` for reads, `engine.begin()` is available for writes but the
spec uses `engine.connect() + conn.commit()` pattern for save_config.

## Wiki patterns checked
- **SQLAlchemy Param-Cast Collision** (4x sighting): `::jsonb` in a `text()` SQL
  string next to `:param` will cause SyntaxError. The spec's `save_config` has
  `VALUES (:cfg::jsonb, ...)` — must use `CAST(:cfg AS jsonb)` instead.
- **Decimal in JSONB Persist**: PortfolioConfig.to_json() already converts Decimal
  to str, so json.dumps() is safe. No extra sanitization needed.

## Existing code reused
- `atlas/api/strategies.py` — exact router + Depends(get_engine) pattern
- `atlas/trading/config.py` — `PortfolioConfig.from_json()` / `to_json()` already exist
- `atlas/db.get_engine()` — returns sync Engine

## Edge cases
- `get_genome`: 404 if genome_id not found — explicit check on `.first()` result
- `get_latest_insights`: empty table → return `{"bullets": [], "parameter_importance": {}}`
- `get_config`: no active config → return `PortfolioConfig()` defaults via `to_json()`
- `save_config`: invalid body → 422 from `PortfolioConfig.from_json()` exception

## Key fix vs spec
The spec's `save_config` SQL contains:
  `VALUES (:cfg::jsonb, TRUE, :label)`
This triggers SQLAlchemy Param-Cast Collision (`:cfg::jsonb` parsed as two params).
Fix: use `CAST(:cfg AS jsonb)`.

## Expected runtime
All queries are PK/index lookups or single-row aggregates on small tables.
Each endpoint < 10ms on t3.large.

## Files modified
1. CREATE: `atlas/api/trading.py` (< 200 LOC)
2. MODIFY: `atlas/api/__init__.py` (add 2 lines)
