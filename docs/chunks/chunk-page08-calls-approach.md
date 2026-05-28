# Chunk: Page 08 — Calls Performance
**Date:** 2026-05-27
**Status:** planning

## Data scale

- `atlas_signal_calls`: 587 rows (backfilled 2026-05-27; all open positions)
- `atlas_ledger`: 0 rows (ledger empty; no closed calls yet)
- `mv_calls_performance`: 587 rows — all open, no realized exits
- `atlas_cell_definitions`: 21 rows
- `atlas_universe_stocks`: 750 rows

## Key constraint

The mockup shows 1,847 calls with 77% closed and win-rate stats. Reality: 587 rows, all open (exit_date IS NULL), no realized_excess. The page must be built to work with this data while being honest about it.

Approach: 
- Hero stats show real counts from signal_calls
- Win-rate matrix: show predicted_excess distribution by cell (what we CAN compute from open book)
- Realized excess charts: show as "open book only" with note
- Ledger: show all 587 rows (open only, no realized data columns)
- Cell trajectories: use confidence_unconditional and predicted_excess as proxy for IC
- "Six cells" section: aggregate from mv_calls_performance grouped by (cap_tier × tenure × action)

## MV columns (inferred from signal_calls source + migration 096)

From `atlas_signal_calls`:
- `signal_call_id` UUID
- `instrument_id` UUID  
- `date` DATE (entry date)
- `cap_tier_at_trigger` text (Large/Mid/Small)
- `tenure` enum (1m/3m/6m/12m)
- `action` enum (POSITIVE/NEGATIVE — no NEUTRAL per backfill)
- `confidence_unconditional` Numeric
- `predicted_excess` Numeric (friction_adjusted_excess)
- `exit_date` DATE (NULL — all open)
- `exit_reason` text (NULL)

Joined:
- `ticker` via atlas_universe_stocks (symbol)
- `sector` via atlas_universe_stocks

MV likely adds computed columns:
- `realized_excess` (NULL — from ledger)
- `days_held` computed from CURRENT_DATE - date
- `cell_label` e.g. "L 6m POS"
- `is_open` boolean

## Chosen approach

**Query layer** (server-only, `@/lib/db` postgres client):
- `getCallsHero()` — aggregate counts from mv_calls_performance
- `getCallsLedger(limit)` — paginated rows for the ledger table
- `getWinRateMatrix()` — group by (cap_tier × tenure × action), compute avg predicted_excess + count
- `getTopSixCells()` — top 6 by count + predicted_excess
- `getCallsSummaryByCell()` — for trajectories section (using predicted_excess as IC proxy)

**Architecture:**
- `calls/page.tsx` — RSC shell, fetches data server-side, passes to client
- `calls/CallsClient.tsx` — client component with all interactive sections

**Charts (Recharts only):**
- Win-rate matrix: rendered as HTML table with color-coded cells (no chart needed)
- Trajectories: LineChart per cell showing predicted_excess over days_held distribution
- Scatter: ScatterChart (predicted_excess vs days_held for open book)
- Cell cards: inline LineChart or AreaChart

## Edge cases

- All exits NULL: show "Open book" banner, disable win-rate coloring, show predicted not realized
- NULL predicted_excess: show "—" not 0
- NULL ticker: fallback to instrument_id[:8]
- Empty mv_calls_performance: show empty state banner
- action enum: POSITIVE → BUY display, NEGATIVE → AVOID display (per CONTEXT.md note)

## Expected runtime (t3.large)

Queries are all small (587 rows max). Runtime < 200ms. Page server render < 500ms.

## Wiki patterns checked

- existing: `recent_signal_calls.ts` for signal_calls query pattern
- existing: `markets_rs.ts` for RSC → client pass pattern
- existing: `MarketsRsClient.tsx` for client component structure
- existing: `FundsList.tsx` for column-chooser + filter pattern
