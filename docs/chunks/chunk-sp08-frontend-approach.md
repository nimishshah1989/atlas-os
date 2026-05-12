# Chunk SP08-Frontend — Intraday RS Leaders Panel

## Scope
Three files:
1. `frontend/src/app/api/intraday/route.ts` — Next.js proxy (GET)
2. `frontend/src/components/stocks/IntradayRSLeaders.tsx` — client component
3. `frontend/src/components/stocks/StocksClientShell.tsx` — mount point (modify)

## Actual data scale
- API returns up to 50 rows (backend cap `_MAX_LEADERS`), default 20
- Poll interval: 30 seconds
- No heavy computation in the component — display-only transform

## Backend API confirmed (from atlas/api/intraday.py)
- `GET /api/v1/intraday/rs-leaders?n=20&sector=...`
- Response: `{ data: IntradayLeader[], meta: { data_as_of?, fetched_at, source, row_count? } }`
- `close`, `ema_20`, `ema_50`, `rs_vs_nifty`, `rs_pctile_intraday` are Decimal (serialised as strings or numbers via Pydantic)
- `bar_time` is ISO datetime string
- Empty market state: `data=[]` with `meta.note = "Market closed or no intraday data yet"`
- Cache-Control: `public, max-age=30` on backend

## Proxy route design
- Pattern matches `frontend/src/app/api/agents/[action]/route.ts` exactly
- `export const dynamic = 'force-dynamic'` — no page-level cache
- Allowlist: `['rs-leaders', 'status']`
- Forwards all non-`endpoint` query params upstream
- `next: { revalidate: 30 }` on fetch — aligns with backend Cache-Control
- Auth: `Authorization: Bearer ${ATLAS_INTERNAL_SECRET}` header

## Component design
- `'use client'` — polls via useEffect + setInterval
- Market hours gate: 09:15–15:35 IST. IST = UTC+5:30 = UTC+330min.
  Check: `(utcMinutes - 0) + 330` within [555, 935] minutes from midnight UTC-equivalent
  Concrete: utcH*60+utcM + 330 → compare to 9*60+15=555 and 15*60+35=935
- Only start interval during market hours, show static state otherwise
- Cleanup: clearInterval in useEffect return
- Loading: 3 skeleton rows with animate-pulse
- RSPctileBar: rs_pctile_intraday is 0–1 (Decimal fraction) from DB — same as existing RSPctileBar which expects 0-1 string. Pass as string via `.toString()`.
- RS vs Nifty: field is Decimal fraction (e.g. 0.023 = 2.3%). Multiply by 100 for display.
- Number() used for display-only float conversion, not parseFloat()

## Table styling — exact match to RSLeadersPanel.tsx
- `border-b border-paper-rule` on thead row
- `font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary` for th
- `hover:bg-paper-rule/10` on tr
- `font-mono text-xs tabular-nums` for number cells

## StocksClientShell.tsx modification
- Add `import { IntradayRSLeaders } from './IntradayRSLeaders'`
- Insert `<IntradayRSLeaders />` before `<StockBreadthPanel>` (top of layout)
- No props — component is self-contained

## Edge cases
- `rs_pctile_intraday` null: RSPctileBar handles null already (renders "—")
- `ema_20` null: render "—"
- `bar_time` formatting: extract HH:MM from ISO string, show as "HH:MM IST"
- Empty data array with meta.note: show note text
- Network error: show error banner, keep last data if available
- Outside market hours: skip polling entirely (no wasted requests)

## File size check
- route.ts: ~40 LOC (well under 600)
- IntradayRSLeaders.tsx: ~160 LOC estimate (under 600)
- StocksClientShell.tsx: ~50 LOC after modification (under 600)

## TypeScript strictness
- No `any` — all interfaces defined
- `Number()` not `parseFloat()` for display conversions
- Optional chaining on all nullable fields
