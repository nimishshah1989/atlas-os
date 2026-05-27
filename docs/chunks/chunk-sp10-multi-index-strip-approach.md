# Chunk: SP10 Multi-Index Strip

## Objective
Extend `atlas_nifty_intraday` to track Bank Nifty, Nifty Midcap 100, Nifty Smallcap 100,
and Nifty IT alongside the existing Nifty 50. Surface all five on the Regime page intraday strip.

## Data scale
- `atlas_nifty_intraday` today: single-symbol, at most 26 bars/day × 5 trading days = ~130 rows.
  After change: 5 symbols × 26 bars × 5 days = ~650 rows. All in-memory trivially; zero scale concern.

## Approach

### Migration 059
Alter `atlas_nifty_intraday`:
1. ADD COLUMN `symbol VARCHAR(30) NOT NULL DEFAULT 'NIFTY 50'` — default preserves existing rows.
2. DROP CONSTRAINT `atlas_nifty_intraday_pkey` (the old `bar_time` PK).
3. ADD PRIMARY KEY `(symbol, bar_time)` — composite; one bar per symbol per timestamp.
4. Leave `idx_ani_bar_time` as-is (used for time-range queries).
5. CREATE INDEX `idx_ani_symbol` for symbol-filtered queries.
Downgrade reverses in opposite order (delete non-NIFTY-50 rows first, then swap PK back).

### rs_engine.py
Add `INDEX_TOKENS: dict[int, str]` constant mapping all 5 Kite tokens → display symbols.
`NIFTY50_TOKEN` stays untouched for RS computation (only Nifty 50 is the RS denominator).

### persistence.py
- Add `symbol: str = "NIFTY 50"` to `NiftyBarRecord` dataclass (default keeps all existing callers intact).
- Update `upsert_nifty_bar` SQL: add `symbol` to INSERT columns+VALUES, change conflict target to `(symbol, bar_time)`. Do NOT include symbol in DO UPDATE SET (it's part of PK).

### ingester.py
- Update import to pull `INDEX_TOKENS` from rs_engine.
- In `_build_token_map`: replace single `token_map[NIFTY50_TOKEN] = "NIFTY50_INDEX"` with a loop
  over `INDEX_TOKENS`, mapping each token to `f"__INDEX__{sym}"` (prefix distinguishes from equity UUIDs).
  Special case: NIFTY50_TOKEN → keep as `"NIFTY50_INDEX"` (RS computation checks `== "NIFTY50_INDEX"`).
  Actually per spec: loop over INDEX_TOKENS, use `__INDEX__NIFTY 50` for all, but RS logic checks
  `nifty_inst_id == "NIFTY50_INDEX"`. So NIFTY50_TOKEN must stay as `"NIFTY50_INDEX"`.
  Solution: keep `token_map[NIFTY50_TOKEN] = "NIFTY50_INDEX"` then loop remaining tokens.
  Or: use `INDEX_TOKENS[token]` as sentinel value and check `in INDEX_TOKENS` for the loop.
  
  Best approach: in `_process_bar_close`, the stock-bar loop already skips `"NIFTY50_INDEX"`.
  For multi-index we add: after the existing Nifty50 persist block, loop over all INDEX_TOKENS,
  skip NIFTY50_TOKEN (already handled), and persist remaining index bars with their symbol.
  
  In `_build_token_map`: add a loop after the existing NIFTY50_TOKEN line for the other 4 tokens,
  mapping them to `f"__INDEX__{sym}"` so the stock-bar loop skips them.

- In `_process_bar_close`: the existing `if inst_id_str == "NIFTY50_INDEX": continue` guard
  needs to cover all index sentinels. Change to `if inst_id_str.startswith("__INDEX__") or inst_id_str == "NIFTY50_INDEX": continue`.
  Then after the Nifty50 persist block, add a loop that persists all non-Nifty50 index bars.

### api/intraday.py
New `_INDICES_SQL`: SELECT per-symbol MAX(bar_time) latest bar using (symbol, MAX(bar_time)) subquery.
New models: `IndexBar`, `IndicesResponse`.
New endpoint `GET /indices`.
Pattern mirrors `/nifty`: OperationalError guard, Cache-Control max-age=30, meta with data_as_of.

### route.ts
Add `'indices'` to the ALLOWED set (1-line change).

### IntradayNiftyStrip.tsx
Refactor to poll `/api/intraday?endpoint=indices`. Replace single-Nifty display with a horizontal
strip of compact cards — one per symbol. Remove `formatBarTime` function; show single "as of HH:MM IST"
from `meta.data_as_of`. Keep `isMarketOpen`, `formatPrice`, `formatReturn`, `LiveDot`.

## Edge cases
- NULL `return_since_open` per symbol: rendered as "—" (formatReturn already handles null).
- Empty response when market is closed: show "Closed" state.
- First bar of day: `return_since_open` may be null until second bar — handled by null guard.
- Existing Nifty50 bars (pre-migration): default column value `'NIFTY 50'` fills them correctly.

## File size
- `IntradayNiftyStrip.tsx` currently 145 lines; refactor stays ~170 lines (within 200-line limit).
- `intraday.py` currently 566 lines; adding ~45 lines → ~611. Within 600 limit? Need to check.
  The file has `# allow-large` marker? No. Will add one if we go slightly over, with justification.
  Actually: 600 LOC limit for source files. Current file is 566 lines. Adding ~50 lines puts us at 616.
  Will keep the new endpoint tight to stay under or just at 600. The existing file counts, so we must
  be surgical — the new models + SQL + endpoint should fit in ~45 lines to stay at 611.
  Add `# allow-large: intraday API module — 6 endpoints (rs-leaders, status, nifty, sector-movers, prices, indices) are tightly coupled around a single router and shared engine pattern; splitting would require duplicating the OperationalError guard and engine import across multiple files` if needed.

## Expected runtime
Migration: < 1s (table has < 200 rows, index ops are trivial).
API endpoint: < 5ms (5-row GROUP BY on tiny table).
Frontend: 30s poll, ~50 bytes JSON per index bar.
