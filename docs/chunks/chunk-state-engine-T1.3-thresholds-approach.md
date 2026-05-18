# Chunk: State Engine Task 1.3 — thresholds.py

## Data scale

atlas.atlas_state_thresholds: 18 active rows seeded by migration 076.
This is a pure config table — tiny, never bulk-loaded. SQL fetch is trivially fast.

## Chosen approach

Simple synchronous SQLAlchemy `engine.connect()` + `text()` query. No pandas,
no async, no chunking needed. 18 rows returned as a plain Python dict.

The query filters `WHERE active = TRUE`. The partial unique index
`uq_state_thresholds_active` (from migration 074) guarantees at most one row
per `(threshold_name, state_or_gate)` key, so the dict build is unambiguous.

## Wiki patterns checked

- Decimal Not Float — thresholds stored as `Numeric(12,6)` in DB; we convert to
  `float` at the Python boundary (these are classifier inputs, not money). The
  underlying `threshold_value` is never summed or stored back — pure read-only
  comparison input. Float is acceptable here per the computation boundary pattern.
- SQL Window Computation — not applicable (18 rows, no aggregation needed).

## Existing code reused

- `tests/migrations/conftest.py` — `db_engine` fixture pattern (session-scoped
  SQLAlchemy Engine from `ATLAS_DB_URL`). Copied verbatim into
  `tests/intelligence/states/conftest.py`.
- `atlas/intelligence/states/cohorts.py` and `features.py` — module header style.

## Edge cases

- `ic_at_threshold` and `ic_ir_at_threshold` are nullable in the schema (Phase 1
  seeds have no IC data yet). Both handled with `if ... is not None else None`.
- `threshold_value` is `Numeric(12,6)` — `float(r.threshold_value)` converts the
  DB Decimal to Python float explicitly; never rely on implicit cast.
- `get()` helper: `default=None` signals "raise on missing". Sentinel `None` is
  safe because no threshold is legitimately `None` as a return value; callers
  always get a `float`.

## Expected runtime

Single SQL round-trip fetching 18 rows: <5ms on any infrastructure.

## Files

- `atlas/intelligence/states/thresholds.py` (new)
- `tests/intelligence/states/test_thresholds.py` (new)
- `tests/intelligence/states/conftest.py` (extend — add `db_engine` fixture)
