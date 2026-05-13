# Chunk SP10-Task8 Approach: IntradaySectorMovers Component

## Task
Build `IntradaySectorMovers` — a client-side React component showing sectors ranked by intraday return-since-open, with live 30s auto-refresh.

## Data scale
- No new DB query — component fetches from `/api/intraday?endpoint=sector-movers` (Next.js proxy to backend)
- Response has ~10 sector rows (one per NSE sector)
- No server-side data loading needed

## Chosen approach
Pure client component pattern — mirrors IntradayRSLeaders.tsx exactly:
- `'use client'` directive
- `useState` + `useEffect` + `useRef` for polling
- Same `isMarketOpen()` helper (copy verbatim from spec)
- Same `LiveDot` component pattern
- Fetch from `/api/intraday?endpoint=sector-movers` every 30s when market open

## Wiki patterns checked
- `Dashboard-Backend Name Drift` — no hardcoded counts; using API response's `sector_count`
- `Decimal Not Float` — `avg_return_since_open` arrives as string, converted to `Number()` only at display time (multiply by 100 for %, `toFixed(2)` for display). Never stored as float.

## Existing code being reused
- `IntradayRSLeaders.tsx` — identical pattern for `LiveDot`, `isMarketOpen`, fetch+interval, state management
- Same Tailwind design tokens: `border-paper-rule`, `text-ink-primary/secondary/tertiary`, `bg-signal-pos/neg`, `text-signal-pos/neg`

## Files to create/modify
- **CREATE**: `frontend/src/components/sectors/IntradaySectorMovers.tsx`
- **MODIFY**: `frontend/src/app/sectors/page.tsx` (add import + panel above SectorViews)

## Edge cases
- `data: []` with market open → show `meta.note ?? 'Waiting for first bar...'`
- `!marketOpen` → single-line closed message, no padding waste
- `error` state → graceful error message
- `avg_return_since_open` as string → `Number(str) * 100`, never `parseFloat`
- Progress bar capped at 100% via `Math.min(Math.abs(pct) / 2 * 100, 100)`

## Display math
- `avg_return_since_open` is raw ratio (0.008542 → 0.85%)
- `pct = Number(row.avg_return_since_open) * 100`
- `barWidth = Math.min(Math.abs(pct) / 2 * 100, 100)` — ±2% fills bar, capped at 100%

## Constraint: 200 line max
Component is compact by design. Progress bar rows are inline JSX, header is ~10 lines, loading skeleton ~8 lines.

## Expected runtime
Frontend-only change, no backend computation. Render time negligible.

## No new tests needed for this chunk
The component is pure UI/fetch logic. The sectors `__tests__/` only has RRGChart (D3 chart). The fetch logic mirrors an already-committed pattern. TypeScript strict mode (`npx tsc --noEmit`) is the primary verification gate.
