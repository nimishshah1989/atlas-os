# Chunk Sprint-4 Phase-4 + 5.1 — Fund Deep Dive Page

## Scope
Build `/funds/[mstar_id]` deep dive: page shell, header, 3 lens panels,
decision history table, plus add `/funds` to TopNav (Task 5.1 — already
present, no-op verified).

## Data scale
- This is a frontend RSC chunk; no DB writes. The 4 RSC queries exist already
  in `frontend/src/lib/queries/funds.ts` and are scoped:
  - `getFundMaster(mstar_id)` — single row
  - `getFundMetricHistory(mstar_id, 90)` — at most ~90 daily rows
  - `getFundLens(mstar_id)` — single row (LIMIT 1)
  - `getFundDecisionHistory(mstar_id)` — LIMIT 52
- Each query is bounded; no full-table scans, no Python compute path.

## Approach
- Page is a thin server-side shell (RSC) with `Promise.all` over 4 bounded
  queries. Mirrors the existing ETF deep-dive shape at
  `frontend/src/app/etfs/[ticker]/page.tsx`.
- `FundLens1` is a `'use client'` component (period toggle via `useState`),
  uses Recharts (already a dep). Lens 2/3 are pure server components.
- Reuses `LensBar`, `CommentaryBlock`, `NavStateChip`,
  `RecommendationChip`, `formatWeeksInState` — no new shared primitives.
- Task 5.1 (Funds nav link) is already present in `TopNav.tsx` line 11 —
  verified. No edit needed.

## Wiki patterns checked
- `young-instrument-partial-metrics` — informs the "Insufficient history"
  fallback in FundLens1 (chartData < 10 points).
- `decimal-not-float` — values arrive from Postgres as `::text` strings;
  `parseFloat` only at the visualization edge (no money math performed).

## Existing code reused
- `LensBar` (handles nullish disclosure + as-of-date + clamped segments)
- `CommentaryBlock` (renders narrative + context cards)
- `NavStateChip`, `RecommendationChip`, `formatWeeksInState`
  from `lib/fund-formatters.tsx`
- `buildSingleFundCommentary` from `lib/commentary/funds.ts`
- ETF deep-dive page pattern (Promise.all + notFound)

## Edge cases
- `getFundMaster` returns null → `notFound()` → renders
  `frontend/src/app/funds/[mstar_id]/not-found.tsx`
- `metricHistory` empty / < 10 rows → "Insufficient history" panel
- `lens` is null → `LensBar` renders `nullish` greyed bar with N/A
- `aligned_aum_pct` / `strong_aum_pct` null → also nullish → no segments
- Decision history empty → "No decision history available" copy
- Gates can be true / false / null — Gate component shows ✓ / ✗ / ?
- `weeks_in_current_state` null → em-dash via `formatWeeksInState` helper
- Recharts SSR safety: FundLens1 marked `'use client'`

## Expected runtime
- Page renders < 200ms cold on t3.large (4 small queries to indexed
  Supabase tables; each returns ≤ 90 rows). No compute work in Python.

## Files created (within chunk scope)
- `frontend/src/app/funds/[mstar_id]/page.tsx`
- `frontend/src/app/funds/[mstar_id]/not-found.tsx`
- `frontend/src/components/funds/FundDeepDiveHeader.tsx`
- `frontend/src/components/funds/FundLens1.tsx`
- `frontend/src/components/funds/FundLens2.tsx`
- `frontend/src/components/funds/FundLens3.tsx`
- `frontend/src/components/funds/FundDecisionHistory.tsx`

Tests:
- `frontend/src/components/funds/__tests__/FundDeepDiveHeader.test.tsx`
- `frontend/src/components/funds/__tests__/FundLens2.test.tsx`
- `frontend/src/components/funds/__tests__/FundLens3.test.tsx`
- `frontend/src/components/funds/__tests__/FundDecisionHistory.test.tsx`

(FundLens1 chart not unit-tested — Recharts requires jsdom canvas;
covered by visual QA against the deep-dive page.)
