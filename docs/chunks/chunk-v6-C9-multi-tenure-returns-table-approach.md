# Chunk C.9 — MultiTenureReturnsTable approach

## Task
Build `MultiTenureReturnsTable.tsx` — a compact 6-tenure returns table and its
Vitest test suite.

## Data scale
Frontend-only component. No DB queries in this chunk. Consumes
`MultiTenureReturns[]` already fetched by the caller via
`getMultiTenureReturnsBatch()` (C.5).

## Type consumed
`MultiTenureReturns` from `@/lib/queries/v6/multi_tenure_returns` —
iid + date + ret_1d|1w|1m|3m|6m|12m as `string | null`.

## Display utilities
- `signedPct(s)` for display of each return cell
- `toNumber(s)` ONLY at the threshold-check site (> 0 / < 0 guard)
- Null → em-dash `—` with `text-ink-tertiary`

## Design tokens
- Positive: `text-signal-pos`
- Negative: `text-signal-neg`
- Null/zero: `text-ink-tertiary`
- Highlighted row: `bg-paper-deep ring-2 ring-signal-pos`
- Header: sticky via `sticky top-0 z-10`

## Approach
Pure client component. No data fetching. Props-driven.
Table structure:
- Columns: Ticker | 1d | 1w | 1m | 3m | 6m | 12m (or subset via showColumns)
- Sticky header
- ARIA: role="table", role="columnheader", role="row", role="cell"
- Each cell: `aria-label="{ticker} {tenure}: {value}"`

## Edge cases
- Empty rows → render "No return data available" in a colspan cell
- Null return values → em-dash, text-ink-tertiary
- highlightIid → bg-paper-deep + ring-2 ring-signal-pos on matching row
- showColumns prop default: all 6 tenures

## Expected LOC
- Component: ~130-150 LOC (well under 200 cap)
- Tests: ~180-200 LOC (under 250 cap)

## Existing patterns used
- Token usage mirrors GradeChip.tsx and PortfolioBadge.tsx
- Test style mirrors PortfolioBadge.test.tsx (describe/it/expect, no mocks)
