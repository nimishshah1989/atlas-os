---
chunk: sp10-task7
project: atlas-os
date: 2026-05-13
---

# SP10 Task 7 — IntradayNiftyStrip: Approach

## Scope
- New file: `frontend/src/components/regime/IntradayNiftyStrip.tsx`
- Modified file: `frontend/src/app/page.tsx`

## Data
- No database queries — purely client-side fetch to `/api/intraday?endpoint=nifty`
- API proxy already exists at `frontend/src/app/api/intraday/route.ts`
- `nifty` is already in the ALLOWED set (line 6)
- Data shape: NiftyBar object with string decimal fields (open/high/low/close) plus meta envelope

## Chosen approach
Pure React client component following the IntradayRSLeaders.tsx pattern exactly:
- Same `isMarketOpen()` implementation (copy, not import — spec requires no refactor of existing files)
- Same `formatBarTime()` implementation (copy)
- Same `LiveDot` 3-state pattern (live/waiting/closed)
- Same 30s polling interval with cleanup
- Horizontal strip layout instead of table — fits between RegimeHeadline and chart

## Wiki patterns checked
- `Decimal Not Float` — financial values from API are strings, formatted via `Number(str).toLocaleString()` at display time only
- `Dashboard-Backend Name Drift` — component reads API response envelope, no hardcoded counts

## Existing code reused
- `isMarketOpen()` — copied verbatim from IntradayRSLeaders.tsx (lines 41-57)
- `formatBarTime()` — copied verbatim (lines 85-95)
- `LiveDot` — same 3-state pattern, same CSS classes
- CSS class names: `text-teal`, `text-signal-pos`, `text-signal-neg`, `text-ink-primary/secondary/tertiary`, `border-paper-rule`, `animate-pulse`, `animate-ping`

## Edge cases
- `data: null` — API returns this when table is empty; show `meta.note ?? 'Waiting for first bar...'`
- Market closed — show minimal closed row, do not poll
- Loading skeleton — 3 animated rectangles, matches existing pattern
- Error — show error message without crashing
- Negative return — red (`text-signal-neg`), positive — teal (`text-signal-pos`)
- NULL pct_change_since_open — formatReturn returns `{ text: '—', cls: 'text-ink-tertiary' }`

## File size constraint
Spec says 150 lines. Page shells are 250. Component files are 600 max. Targeting ~140 lines to stay under 150.

## Expected runtime
No computation — pure HTTP fetch, client-side only. Zero backend load.
