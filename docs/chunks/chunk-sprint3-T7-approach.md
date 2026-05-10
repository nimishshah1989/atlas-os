# Chunk: Sprint-3 T7 — RRGChart D3 component

**Date:** 2026-05-10
**Branch:** feat/sprint-3-sectors-upgrade
**File scope:** `frontend/src/components/sectors/RRGChart.tsx` (new)
**Test scope:** `frontend/src/components/sectors/__tests__/RRGChart.test.tsx` (new)

## Problem

A Relative Rotation Graph (RRG) plots each sector's relative-strength (RS) on
the X axis vs RS momentum (T vs T-20) on the Y axis, with **trailing dots**
showing each sector's recent path. Both axes must be **mean-centered** so the
chart is stable regardless of the absolute RS levels for the day.

Consumers will dynamically import this with `dynamic({ ssr: false })`, so the
file must be `'use client'` and rely on D3 inside `useEffect`.

## Data scale

This is a **client-side** chart over a single day's snapshot (~25 sectors) plus
30 days of history per sector (~750 rows). No DB queries here — data comes in
as props. Rendering cost is trivial; no scale concerns.

| Input          | Rows                                  |
|----------------|---------------------------------------|
| `current`      | ~25 SectorSnapshot rows (latest day)  |
| `history`      | ~25 sectors × 30 days = ~750 RRGRows |
| Trailing dots  | last 5 per sector = ~125 circles      |

## Approach

Single React component, single `useEffect` that rebuilds the SVG on prop change.
Pattern mirrors the existing `SectorBubbleChart.tsx` (see lines 47–260). Specifics:

1. **Mean-center both axes** — compute `meanX` from `bottomup_rs_3m_nifty500`
   and `meanY` from `rs_momentum` of the `current` array. Each plotted point's
   coordinates are `(rs - meanX, momentum - meanY)`. Trail points use the SAME
   `meanX`/`meanY` so trails align with current dots.

2. **NULL filter for history** — `history.filter(r => r.rs !== null && r.momentum !== null)`
   before any rendering. Sectors with <20 trading days return NULL momentum
   (LAG window unfilled) — those points must be dropped, not zeroed.

3. **Trailing dots** — `d3.group(validHistory, r => r.sector_name)`, take last 5,
   render circles with opacity ramp `[0.20, 0.35, 0.55, 0.75, 1.0]` (oldest → newest).
   `pointer-events: none` so they don't intercept clicks.

4. **Click navigation** — main dots get `cursor: pointer`, `role="button"`, keyboard
   handler on Enter/Space, all calling `onSelect(sector_name)`. First dot has
   `tabindex=0`, others `tabindex=-1` — standard a11y for D3 charts.

5. **Quadrant watermarks** — 4 large serif labels at fractional offsets from the
   crosshair center. `aria-hidden="true"`, opacity 0.12.

6. **Color** — momentum-state colors from `CHART_COLORS` (verified keys:
   `momAccelerating`, `momImproving`, `momFlat`, `momDeteriorating`, `momCollapsing`).
   Fallback to `#8C8278` (inkTertiary) for unknown states.

## Wiki patterns checked

- `~/.forge/knowledge/wiki/index.md` reviewed; closest pattern is **Decimal Not Float**
  (parsing string NUMERICs before display). The `bottomup_rs_3m_nifty500` field on
  `SectorSnapshot` is `string | null` (Postgres NUMERIC streamed as text); we use
  `parseFloat` for *display-only* math (axis position), which is the documented
  computation-boundary practice. No money values are at stake here.
- No D3-specific wiki entry exists; `SectorBubbleChart.tsx` is the in-repo precedent.

## Existing code being reused

- `CHART_COLORS` in `@/lib/chart-colors.ts` (verified keys exist).
- `SectorSnapshot`, `RRGHistoryRow` types from `@/lib/queries/sectors`.
- Pattern: `SectorBubbleChart.tsx` (D3 inside `useEffect`, ref pattern, mount/teardown).

## Edge cases

| Case | Handling |
|---|---|
| `current.length === 0` | Render placeholder div, skip D3 entirely |
| `bottomup_rs_3m_nifty500 === null` | Drop from chart; do not zero |
| `rs_momentum === null` (young sector) | Drop from chart |
| History row with `rs` or `momentum` NULL | Filtered out before grouping |
| Sector in history but missing from `current` | Trail color falls back to `#8C8278` |
| Unknown momentum state | Color falls back to `#8C8278` |
| `xExtent` collapses to a point | `xPad = (max-min)*0.15 || 0.1` (the `|| 0.1` guards zero-range) |

## Acceptance criteria (re-verified after build)

- [ ] `'use client'` directive at top of file
- [ ] Named export `RRGChart`, no default export
- [ ] Mean-centering applied identically to `current` and `history`
- [ ] NULL filter before history rendering
- [ ] Trail opacities `[0.20, 0.35, 0.55, 0.75, 1.0]`, last-5-per-sector
- [ ] Click and Enter/Space both call `onSelect(sector_name)`
- [ ] 4 quadrant labels, `aria-hidden="true"`
- [ ] TypeScript strict passes (`tsc --noEmit`)
- [ ] At least one Vitest unit test (mean-centering correctness, smoke render)

## Expected runtime

t3.large irrelevant — this is browser-rendered. ~25 dots + ~125 trail circles in
one `useEffect`; <16ms on any modern browser. Re-renders on prop change only.

## Outside scope (do not modify)

- `SectorViews.tsx` — consumer changes are a separate task
- `sectors.ts` queries — already exist
- Anything outside `frontend/src/components/sectors/RRGChart.tsx` and its test
