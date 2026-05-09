# Chunk M7-T6 (Phase 3, Task 6) Approach: Custom Portfolio API

## Data Scale
No bulk loads. Endpoints touch single-row reads (by portfolio_id) or a small list
of custom portfolios (expected <10 rows per user; total table size <10K rows).
SQL uses parameterized `text()` queries with bound params — never f-strings.

## Chosen Approach
- Sync `def` route handlers (consistent with rest of repo — no async).
- `get_engine` injected as a FastAPI `Depends()` so tests can override via
  `app.dependency_overrides`.
- All DB access via `open_compute_session(engine)` — same pattern as
  `atlas.simulation.custom.portfolio` (the module these endpoints wrap).
- Validation errors from `create_custom_portfolio` (raises `ValueError`) are
  translated to HTTP 422 with the exception's message in `detail`.
- Pydantic v2 `BaseModel` for request bodies; response is a typed `dict[str, Any]`
  envelope as per spec.

## Wiki Patterns Checked
- Decimal Not Float — N/A here; `weight_pct` is a percentage ratio (0-100), not money.
- SQLAlchemy Param-Cast Collision — using `id::text` is OK in these queries because
  there's no `:param` immediately adjacent (just `:pid`). Pattern would only matter
  if we had `column::text = :param`. We avoid that here.

## Existing Code Reused
- `atlas.simulation.custom.portfolio.create_custom_portfolio` — orchestrates
  validate -> save -> background backtest.
- `atlas.simulation.custom.builder.InstrumentWeight` — dataclass for builder API.
- `atlas.compute._session.open_compute_session` — shared connection manager with
  `statement_timeout=0`.
- `atlas.db.get_engine` — shared SQLAlchemy engine factory.

## Edge Cases
- Validation failure (empty portfolio, weights ≠ 100, unknown instrument) → 422.
- Unknown portfolio UUID on status/detail → 404.
- `backtest_id IS NULL` (backtest still running) → status="pending".
- `backtest_id` set but JOIN row has NULL metrics → return `backtest=None` shape only
  when `backtest_id` itself is NULL; otherwise pass nullable floats through.
- Empty list → endpoint returns `[]` (no rows).
- `instruments` JSONB from PG returns as Python dict/list automatically (psycopg2
  registers a JSONB adapter); pass through unchanged.

## Expected Runtime
Single-row queries on UUID-PK and indexed FK; <50ms each on t3.large.
List endpoint: ORDER BY created_at DESC, expected <10 rows; <50ms.

## Files
- atlas/api/__init__.py (new)
- atlas/api/portfolios.py (new)
- tests/unit/api/__init__.py (new, empty)
- tests/unit/api/test_portfolios.py (new)
