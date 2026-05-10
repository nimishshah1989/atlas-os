# Sectors Sub-project B: Dual Chart Reading Guide + Event Playbook

**Approved for implementation — 2026-05-10**

---

## Goal

Two additions to the Sectors page that turn raw chart data into actionable fund-manager intelligence:
1. **Dual Chart Reading Guide** — a cross-reference panel between the Positioning Matrix and RRG showing exactly how to combine signals from both charts, with a live today-example using real sector positions.
2. **Event Playbook Panel** — a new section that auto-matches the current market regime to 2–3 similar historical events and shows which sectors led and lagged during each, flagging current Overweight sectors that historically underperformed in analogous environments.

---

## Architecture

### Section 1: Dual Chart Reading Guide

**Location:** Between the Positioning Matrix section and the RRG section in `SectorViews.tsx`.

**Rendering:** Pure client-side; reads `visible` and `rrgHistory` props already available in `SectorViews`.

**Component:** `SectorDualChartGuide.tsx` — a thin presentational component receiving:
- `sectors: SectorWithDecision[]` — current positions with bubble-chart quadrant computable from existing fields
- `rrgHistory: RRGHistoryRow[]` — for computing current RRG quadrant per sector

**Logic:**
- Compute Positioning Matrix quadrant per sector from `bottomup_rs_3m_nifty500` (mean-centered) and `participation_50` (vs 50% threshold).
- Compute RRG quadrant per sector from `bottomup_rs_3m_nifty500` (vs mean = X) and `rs_momentum` (vs 0 = Y).
- Build a 4-combination cross-reference table: Matrix quadrant × RRG quadrant → signal + action.

**Cross-reference table (4 canonical pairings):**

| Matrix | RRG | Combined Signal | Action |
|---|---|---|---|
| Leaders (top-right) | Leading (top-right) | **Confirmed strength** — RS + broad participation + accelerating momentum | Core overweight; size up on dips |
| Narrowing (bottom-right) | Weakening (top-right→bottom-right) | **Fragile leadership** — price strength without participation; momentum fading | Trim; this correction punishes early |
| Recovering (top-left) | Improving (bottom-left→top-right) | **Early rotation** — breadth recovering before RS confirms | Scale in; tight stop below entry |
| Laggards (bottom-left) | Lagging (bottom-left) | **Confirmed avoid** — weak on both timeframes | No new exposure; hold cash |

**Live example block:** below the table, show 2–3 of today's actual sectors as concrete examples of the above pairings, pulling from `visible`. Format: "e.g. [SectorName] is currently [Matrix quadrant] + [RRG quadrant] → [action phrase]."

---

### Section 2: Event Playbook Panel

**Location:** New section below the Breadth Waterfall, before the Sector State Heatmap.

**Data flow:**
```
sectors/page.tsx  →  getSectorPlaybook(regimeState)  →  SectorViews props
                  →  SectorEventPlaybook.tsx (client component)
```

**New server function:** `getSectorPlaybook(regimeState: string): Promise<PlaybookEntry[]>` in `sectors.ts`.

```typescript
export type PlaybookEntry = {
  event_id: string
  event_label: string
  event_description: string
  start_date: string
  end_date: string
  leaders: Array<{ sector_name: string; avg_rs: number }>   // top 3 by avg RS
  laggards: Array<{ sector_name: string; avg_rs: number }>  // bottom 3 by avg RS
}
```

**Matching logic (SQL + TypeScript):**
1. Filter `MARKET_EVENTS` to those with a regime affinity matching `regimeState`:
   - `Risk-Off` / `Cautious` → match COVID crash, Rate hike cycle, Adani crisis
   - `Constructive` / `Risk-On` → match Election (recovery phase)
   - Fallback: show the 2 most recent events regardless
2. For each matched event (up to 3), query `atlas_sector_metrics_daily` for that date range and compute `AVG(bottomup_rs_3m_nifty500)` per sector, ordered DESC (leaders) and ASC (laggards), limit 3 each.
3. Return `PlaybookEntry[]` — max 3 entries.

**SQL pattern per event:**
```sql
SELECT sector_name, AVG(bottomup_rs_3m_nifty500::float) AS avg_rs
FROM atlas.atlas_sector_metrics_daily
WHERE date BETWEEN ${startDate} AND ${endDate}
GROUP BY sector_name
ORDER BY avg_rs DESC  -- flip to ASC for laggards
LIMIT 3
```

**New client component:** `SectorEventPlaybook.tsx`

Props:
```typescript
type Props = {
  entries: PlaybookEntry[]
  currentOverweightSectors: string[]
}
```

Renders:
- Section header: "Historical Event Playbook — how sectors behaved in similar regimes"
- Short intro sentence (1 line)
- One card per `PlaybookEntry`:
  - Event label + date range
  - Two columns: Leaders (green) | Laggards (red), top 3 each
  - Warning chip for each current Overweight sector that appears in Laggards list
- If `entries.length === 0`: "No historical events matched the current regime. Data will appear once regime state is classified."

**Overweight-at-risk warning:** computed in `SectorEventPlaybook.tsx`:
```typescript
const atRisk = currentOverweightSectors.filter(s =>
  entries.some(e => e.laggards.some(l => l.sector_name === s))
)
```
If any, show banner: "⚠ [Sector] was a laggard in [Event]. Review position sizing."

---

## Data Dependencies

- `getSectorPlaybook` reuses `atlas.atlas_sector_metrics_daily` — no new tables needed.
- `MARKET_EVENTS` already in `event-library.ts` — no changes to that file's shape.
- `SectorWithDecision` already carries `bottomup_rs_3m_nifty500`, `participation_50`, `rs_momentum`, `bottomup_momentum_state` — no new fields needed in `SectorSnapshot`.
- `sectors/page.tsx` needs a 6th parallel query: `getSectorPlaybook(regime?.regime_state ?? 'Unknown')`.
- `getCurrentRegime()` is already used in other page imports — add to sectors page.

---

## Files Created / Modified

| File | Action | Responsibility |
|---|---|---|
| `frontend/src/components/sectors/SectorDualChartGuide.tsx` | Create | Dual chart cross-reference table + live example |
| `frontend/src/components/sectors/SectorEventPlaybook.tsx` | Create | Event playbook cards with overweight-at-risk warnings |
| `frontend/src/lib/queries/sectors.ts` | Modify | Add `getSectorPlaybook` + `PlaybookEntry` type |
| `frontend/src/app/sectors/page.tsx` | Modify | Add `getCurrentRegime` import + 6th parallel query + pass `playbook` + `regime` props |
| `frontend/src/components/sectors/SectorViews.tsx` | Modify | Accept + render `SectorDualChartGuide` between sections 1+2; accept + render `SectorEventPlaybook` between breadth and heatmap |

**LOC estimates:** all files stay under 600 LOC limit. SectorViews.tsx currently ~410 LOC — adding ~30 LOC for two component insertions stays well within limit.

---

## Error Handling

- `getSectorPlaybook` wrapped in `.catch(() => [])` in `Promise.all` — degraded silently to empty array.
- `SectorEventPlaybook` renders a soft "no data" state when `entries.length === 0`.
- `SectorDualChartGuide` requires no server data — pure computation from props already fetched.

---

## Testing Criteria

- Dual Chart Guide shows for any non-empty `actionable` list.
- Live examples only appear when at least 1 sector maps to a known pairing.
- Playbook cards render for each matched event; empty state renders when `entries` is empty.
- Overweight-at-risk warning appears when a current Overweight sector matches a historical laggard.
- No layout breakage on viewports < 1280px (xl breakpoint); falls back to single-column stacking.
