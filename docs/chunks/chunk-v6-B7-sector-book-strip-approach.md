# Chunk B.7 — SectorBookStrip component

## Data scale
No DB queries in this component — it receives `SectorBookExposure[]` as props
(pre-fetched by server component). The query module (B.2) handles DB access.
Max rows: 30 sectors.

## Chosen approach
Pure presentational React component. No data fetching, no hooks beyond `useMemo`
for sort. Two variants: `list` (all rows) and `single` (1 row hero band).

## Wiki patterns checked
- GradeChip.tsx — chip rendering pattern with Tailwind tokens
- SectorLadder.tsx — row-level table pattern, token usage
- decimal.ts (A.10) — formatPct / signedPct helpers

## Key note on formatPct / signedPct
Both helpers expect decimal fractions (0.183 = 18.3%). The query returns values
already in percentage points ("5.50" = 5.50 pp). Must divide by 100 before
passing to formatPct/signedPct. i.e.: `formatPct(String(val / 100))`.

Helper: `ppToDecimal(s: string): string` — divides string value by 100.

## Existing code reused
- `SectorBookExposure` type from `lib/queries/v6/sector_book_exposure`
- `formatPct`, `signedPct` from `lib/v6/decimal`
- Token classes from globals.css (signal-pos, signal-neg, paper-deep, ink-*)

## Sort logic
`useMemo` on exposures prop: sort by `Math.abs(parseFloat(delta_pp))` DESC by
default. `sortBy` prop controls alt sorts by `book_weight` or `benchmark_weight`.

## Delta bar
Stacked horizontal bar 60px wide. Positive delta → green fill from center-right.
Negative delta → red fill from center-left. Max visual delta = ±10pp (capped at
full bar). Simple inline style width calculation.

## Edge cases
- Empty array: renders sr-only a11y div only
- book_weight="0.00" + benchmark_weight="0.00": muted row (text-ink-tertiary)
- delta_pp="+0.00" or "0.00": NEUTRAL chip, no bar fill
- NaN delta (malformed string): treat as 0 (NEUTRAL)

## Expected runtime
Pure React render — <1ms for 30 rows. No async work.
