# Chunk SP08 — KiteConnect Intraday Live State Engine

## Actual data scale
- `atlas_stock_metrics_daily`: ~750 stocks × ~2,500 trading days ≈ 1.875M rows
- `atlas_stock_metrics_intraday`: new table (7-day retention); ~750 stocks × 26 bars/day × 5 days = ~97,500 rows at full capacity
- `atlas_kite_session`: O(1) — one active row at a time
- `atlas_universe_stocks`: ~750 rows (one per active stock)

## EMA column names confirmed
After reading `atlas/compute/stocks.py` METRICS_COLUMNS and `atlas/compute/primitives.py`:
- Daily table stores: `ema_20_stock`, `ema_50_stock` (NOT `ema_20`, `ema_50`)
- Intraday table (migration 042) stores: `ema_20`, `ema_50` (short names, no `_stock` suffix)
- Bootstrap query must SELECT `ema_20_stock`, `ema_50_stock` from `atlas_stock_metrics_daily`
- Store result in EMAState(ema_20=..., ema_50=...) for intraday use

## Chosen approach

### notify.py
- `python-telegram-bot` async Bot.send_message
- Graceful no-op if env vars missing — Telegram is optional infrastructure
- `send_message_sync` wrapper with `asyncio.run()` for use in synchronous contexts

### auth.py
- psycopg2 direct connection (not SQLAlchemy) for pgcrypto calls (pgp_sym_encrypt/decrypt)
- Raises ValueError for missing env vars (caught at startup, not silently)
- expires_at = midnight IST of current day (23:59:59+05:30)
- No PII in logs — never log access_token

### ema_engine.py
- Pure Python Decimal arithmetic, no numpy/pandas
- NamedTuple EMAState for immutable state passing
- bootstrap_ema_state: single SQL query with MAX(date) subquery
- If columns not found (new DB): log warning, return empty dict — ingester handles gracefully

### rs_engine.py
- Pure Decimal math with explicit None guards
- Zero division returns None (not 0, not inf) — per financial domain rules
- NIFTY50_TOKEN = 256265 as module constant

### persistence.py
- psycopg2 execute_values for batch UPSERT (faster than executemany for bulk)
- ON CONFLICT (instrument_id, bar_time) DO UPDATE — idempotent per wiki pattern
- dataclass BarRecord keeps type safety without ORM overhead in hot path

### ingester.py
- KiteTicker threaded=True with queue.Queue for tick → bar-close decoupling
- Wall-clock IST alignment for bar boundaries (:00/:15/:30/:45)
- Token map cached to ~/.kite_token_map.json, refreshed every 24h
- EMA state in-memory dict, bootstrapped from nightly; updated each bar close
- Open prices reset at 09:15 IST

## Wiki patterns applied
- Idempotent Upsert: ON CONFLICT DO UPDATE on (instrument_id, bar_time)
- Decimal Not Float: all prices/returns as Decimal
- SQLAlchemy Dialect Prefix bug: strip postgresql+psycopg2:// for raw psycopg2 calls

## Existing code being reused
- `atlas/compute/_session.py` pattern: direct psycopg2 for bulk ops
- `atlas/compute/primitives.py`: EMA formula reference (k = 2/(n+1))
- `migrations/versions/042_create_intraday_tables.py`: confirms table schema

## Edge cases
- Missing env vars: raise ValueError at function boundary (not KeyError)
- Nifty return == 0: rs_engine returns None (not ZeroDivisionError)
- No valid Kite session: get_valid_access_token raises RuntimeError with login URL
- EMA columns missing in daily table: warn + return empty dict; ingester bootstraps from first bar
- Tick queue draining: drain ALL items before bar-close write (not just current)
- Reconnection mid-bar: ON CONFLICT ensures reconnect backfill overwrites with better data

## Expected runtime on t3.large
- Bootstrap (750 stocks EMA query): <100ms (single SQL, 750 rows)
- Per-bar-close processing (750 stocks × Decimal EMA + RS): <50ms in Python
- Upsert 750 bars: <200ms with execute_values batching
- Total per 15-min bar: <500ms wall clock
