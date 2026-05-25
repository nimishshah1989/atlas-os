# Chunk B.4b — Book Diff Query (portfolio-level)

## Actual data scale
- atlas_paper_portfolio: EMPTY at v6.0 launch (paper-portfolio writer cron out of scope)
- atlas_conviction_daily: populated via conviction_tape backfill (migration 092)
- atlas_drift_event_log: EMPTY at v6.0 (no drift-detector cron deployed)
- Scale: handful of rows in paper_portfolio at most; edge-case handling for empty is primary concern

## Chosen approach
- TypeScript query module mirroring matrix_diff.ts structure
- Two separate SQL queries run in parallel via Promise.all
- Date resolution: MAX(snapshot_date) and MAX(snapshot_date) WHERE < MAX from atlas_conviction_daily
  (NOT atlas_signal_calls — per migration 092, atlas_conviction_daily is the verdict carrier)
- held_iids_flipped: join atlas_conviction_daily D vs D-1 filtered to held instrument_ids
- held_drift_warns: join atlas_drift_event_log (last 24h, status_after='drift_warn') → 
  atlas_signal_calls (open, no exit_date) → filter to held instrument_ids
- Empty book shortcut: if held set is empty, return both empty arrays immediately (0 DB round-trips)

## Verdict table: atlas_conviction_daily
- Migration 092 confirms: atlas_conviction_daily.verdict column (POSITIVE/NEUTRAL/NEGATIVE)
- Date column: snapshot_date (NOT "date")
- atlas_scorecard_daily stores 5-family R/A/G states; conviction_daily is the verdict aggregator

## Wiki patterns checked
- Same mock pattern as matrix_diff.ts and portfolio_holdings.test.ts
- server-only mock, react cache mock, @/lib/db mock via vi.mock

## Existing code reused
- getHeldIidSet() from B.1 (portfolio_holdings.ts)
- sql template from @/lib/db
- Mock pattern from matrix_diff.test.ts

## Edge cases
- Empty book (atlas_paper_portfolio empty): getHeldIidSet() returns empty Set → early return
- No prior date (first snapshot): yesterday CTE returns 0 rows → all today rows have yesterday_action=null
- atlas_drift_event_log empty: held_drift_warns = []
- NULL handling: verdict is NOT NULL per migration 092 CHECK constraint; still handled defensively

## Expected runtime
- 2 parallel SQL queries, each indexed via idx_conviction_daily_iid_date and
  ix_atlas_signal_calls_open; on empty tables at v6.0 <5ms total

## Files
- frontend/src/lib/queries/v6/book_diff.ts (~130 LOC)
- frontend/src/lib/queries/v6/__tests__/book_diff.test.ts (~230 LOC)
