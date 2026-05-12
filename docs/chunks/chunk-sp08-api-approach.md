# Chunk SP08 — KiteConnect API Layer (kite_auth + intraday endpoints)

## Actual data scale
- `atlas_kite_session`: O(1) — single active row; query is trivial
- `atlas_stock_metrics_intraday`: ~97,500 rows at full capacity; RS-leaders query hits
  `mv_rs_intraday` (materialized view), not the raw table — fast
- `mv_rs_intraday`: materialized view refreshed every ~15 min; row count ≤ 750

## Chosen approach

### kite_auth.py
- `/api/kite/login`: reads KITE_API_KEY, builds redirect URL, returns 302.
  Raises 503 if env var missing. No DB touch.
- `/api/kite/callback`: calls `atlas.intraday.auth.exchange_request_token` +
  `store_access_token`, fires Telegram notify, redirects to /admin.
  Exception → HTTPException(500). No JWT required.

### JWT exemption
- `atlas/api/auth.py` uses `_EXEMPT_PREFIXES` tuple. The middleware checks
  `any(path.startswith(p) for p in _EXEMPT_PREFIXES)`.
- Add `/api/kite/login` and `/api/kite/callback` to `_EXEMPT_PREFIXES`.
  This is the existing pattern — no middleware subclass needed.

### intraday.py
- `/api/v1/intraday/rs-leaders`: queries `atlas.mv_rs_intraday` via SQLAlchemy
  `text()` with explicit column list. n capped at 50. Optional sector substring
  filter via LIKE. Returns 30s cache header. Empty MV → empty data with note.
- `/api/v1/intraday/status`: two sequential queries against `atlas_kite_session`
  and `atlas_stock_metrics_intraday`. All Decimal columns from DB become Decimal
  via row mapping.

### DB access
- Uses synchronous `get_engine()` from `atlas.db` (existing pattern, matches all
  other API routes).
- `engine.connect()` context manager with `conn.execute(text(...))`.

## Wiki patterns applied
- Decimal Not Float: all price/RS columns typed as `Optional[Decimal]`
- Idempotent queries — no writes in intraday.py
- SQLAlchemy Param-Cast Collision: avoided by using CAST() syntax in SQL, not
  `::type` casts next to `:param` bindvars

## Existing code being reused
- `atlas.intraday.auth.exchange_request_token` + `store_access_token`
- `atlas.intraday.notify.send_message_sync`
- `atlas.db.get_engine`
- `atlas.api.auth._EXEMPT_PREFIXES` — extend in place

## Edge cases
- KITE_API_KEY not set: 503 on /login
- Token exchange fails: log error, return 500 (never expose raw exception to client)
- MV empty (market closed): return `{"data": [], "meta": {"note": "..."}}`
- n > 50: clamp to 50 silently
- sector filter: case-insensitive LOWER() + LIKE
- NULL rs_pctile_intraday: ORDER BY ... NULLS LAST handles gracefully

## Expected runtime on t3.large
- `/api/kite/login`: <1ms (env var read + string format)
- `/api/kite/callback`: ~200ms (KiteConnect HTTPS + 2 DB writes + Telegram)
- `/api/v1/intraday/rs-leaders`: <50ms (MV scan, ≤750 rows, LIMIT 20)
- `/api/v1/intraday/status`: <20ms (two single-row queries)
