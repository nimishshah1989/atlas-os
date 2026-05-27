# Chunk C.12 — SignatureMatrix approach

## Scope
Pure UI component: `SignatureMatrix.tsx` + test. No data fetching; caller provides `cells[]`.

## Data scale
N/A — client-side presentational component. No DB queries.

## Chosen approach

The task prompt defines the canonical spec: a factor-exposure grid (SignatureCell with
POSITIVE/NEUTRAL/NEGATIVE/null exposures) for funds/ETFs, NOT the Grade×Category matrix
described in the plan's acceptance lines. The task prompt is the authoritative chunk spec.

- 2×3 or 2×4 CSS grid of factor tiles
- Color mapped by exposure using existing signal-* tokens (matches GradeChip pattern)
- InfoTooltip from `frontend/src/components/ui/InfoTooltip.tsx` — no registry needed,
  inline tooltip content per factor
- signedPct from `lib/v6/decimal.ts` for raw_score display
- null exposure: bg-paper-deep + "—" placeholder

## Wiki patterns checked
- GradeChip.tsx — token usage (bg-signal-pos, bg-signal-neg, bg-signal-warn, bg-paper-deep)
- InfoTooltip.tsx — Radix Tooltip wrapper, Info icon
- ELI5Tooltip.tsx — alternative but uses registry; InfoTooltip is simpler for inline copy
- decimal.ts — signedPct utility already exported

## Existing code being reused
- `GradeChip` token patterns
- `InfoTooltip` component (A.6 reference)
- `signedPct` from decimal.ts

## Edge cases
- `null` exposure: renders grey tile with "—", aria still describes "not enough data"
- `null` raw_score: shows "—" via signedPct null handling
- `null` rank_in_category: omit rank chip entirely
- Empty cells array: renders empty grid (no crash)
- 6 cells → 2×3 grid; 8 cells → 2×4 grid; odd counts → last row may be shorter

## LOC budget
- Component: ~120 LOC (≤200 limit)
- Tests: ~180 LOC (≤250 limit)

## Expected runtime
Pure client render — negligible. No DB / network.
