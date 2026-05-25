# Chunk B.4a — Matrix Diff Query (Universe-Level) — Approach

## Data scale
- Production DB not accessible from local Mac (psycopg2 binary mismatch; query blocked by auto-classifier). Scale estimates from migration context: atlas_signal_calls is a trigger-only tall event table; volume is bounded by 750-stock universe × 4 tenures × active cells. At launch: likely low thousands of rows. Query is date-bound (2 specific dates) so full-table scan does not apply.
- atlas_drift_event_log: 0 rows at v6.0 launch (no drift-detector cron deployed yet). Query must handle empty table gracefully.

## Schema confirmed (from migration 080 + 088)
- `atlas.atlas_signal_calls`: signal_call_id, instrument_id, scorecard_id, date, cell_id, cap_tier_at_trigger, tenure, action, confidence_unconditional Numeric(5,4), exit_date, ...
- `atlas.atlas_cell_definitions`: cell_id, cap_tier, action, tenure, confidence_unconditional Numeric(5,4), drift_status enum{healthy,drift_warn,deprecated}
- `atlas.atlas_drift_event_log`: event_id, cell_id, ts (timestamptz), status_before, status_after (atlas_drift_status enum), action, ...
- NO `grade` column in either table. Grade must be derived from `confidence_unconditional` via a CASE expression matching the existing front-end convention (AAA..B bands from funds_holding_stock.ts, adapted for 0..1 scale).

## Grade derivation (confidence_unconditional 0..1 → letter grade)
Mirrors the existing funds logic scaled to 0..1:
- >= 0.90 → AAA
- >= 0.80 → AA
- >= 0.70 → A
- >= 0.60 → BBB
- >= 0.50 → BB
- else    → B

## date_changed semantics
The spec type says `date_changed: string` = "ISO date when transition happened". Since `atlas_signal_calls` has `date` (when signal was first inserted) and no explicit "transitioned" timestamp, we use `date` as `date_changed` for new_cells_firing (the date the call was first created), and for went_dormant we use the prior date (D-1) as the last day it was active. This matches what the component needs: "when did this cell change state".

## Prior-day resolution
getLatestSnapshotDate() returns the most recent snapshot across multiple tables but does NOT guarantee atlas_signal_calls is populated for that exact date. We resolve D and D-1 directly from atlas_signal_calls MAX(date) queries to stay self-consistent. This follows the pattern described in the task spec.

## Approach
1. Two sub-queries to get D and D-1 dates directly from atlas_signal_calls (handles weekends/holidays).
2. CTEs in a single SQL query: today_cells, yesterday_cells, new_firing, went_dormant — each joined back to atlas_cell_definitions for metadata.
3. Separate query for atlas_drift_event_log (last 24h, status_after = 'drift_warn') with empty-table guard (LEFT JOIN semantics, returns [] naturally).
4. Three arrays assembled in TypeScript from DB result sets.

## Edge cases handled
- Weekend rollover: D and D-1 computed from MAX(date) subqueries, not wall-clock date arithmetic.
- First-ever snapshot (no D-1): D-1 subquery returns NULL; query returns no "yesterday cells" so cells_dormant is [].
- No signal_calls at all: D and D-1 both NULL; all three arrays empty.
- Empty atlas_drift_event_log: query returns zero rows; new_drift_warns is [].
- NULL confidence_unconditional on cell_definitions: grade CASE falls to 'B'.

## Expected runtime on t3.large
Sub-millisecond for all three queries at launch scale (< 10K signal_calls rows). The date-bound indexed queries hit ix_atlas_signal_calls_cell_date. No performance risk.

## Wiki patterns checked
- Existing snapshot.ts: uses single GREATEST() subquery for latest date — adapted here for signal_calls self-consistency.
- Existing funds_holding_stock.ts: AAA..B grade derivation via CASE on score column — pattern reused.
- Existing snapshot.test.ts + stocks.test.ts: vi.fn() sql mock + tagged-template style — test pattern reused.

## Files
- `frontend/src/lib/queries/v6/matrix_diff.ts` (new)
- `frontend/src/lib/queries/v6/__tests__/matrix_diff.test.ts` (new)
