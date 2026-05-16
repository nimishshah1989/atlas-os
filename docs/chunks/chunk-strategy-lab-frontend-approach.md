---
chunk: strategy-lab-frontend-tasks-15-19
project: atlas-os
date: 2026-05-16
status: in_progress
---

# Strategy Lab Frontend — Tasks 15–19 Approach

## Scope
Tasks 15a (query types), 19 (StrategyConfigurator), 17 (TaxHarvestingAlert + ReplicationGuide), 15b (MorningBrief + lab/page.tsx), 18 (EngineRoom), 16 (StrategyLeaderboard + charts + [id]/page.tsx).

## Existing patterns reused
- `sql` tagged template from `@/lib/db` (default export) — same as all other query files
- Recharts import pattern from `frontend/src/components/charts/DrawdownChart.tsx` and `EquityCurveChart.tsx`
- Design tokens: `font-sans`, `font-serif`, `font-mono`, `text-ink-primary/secondary/tertiary`, `border-paper-rule`, teal accent #1D9E75
- `'use client'` for interactive components, no directive for RSC
- `export const dynamic = 'force-dynamic'` on all data pages
- `async params: Promise<{...}>` pattern for Next.js 15 RSC pages

## Data scale
Strategy Lab tables are new — expected low row counts (<1K). SQL queries are correct approach at this scale.

## Edge cases
- `sortino_oos`, `calmar_oos`, `alpha_30d` may be NULL for new genomes — handled with `?? null` and `??` fallbacks in display
- `positions` may be empty — handled with empty-state message
- `insights` may be null — conditional rendering
- NUMERIC columns kept as strings, parsed with `Number()` at display time (never `parseFloat()` on financial fields per project rules)
- `params` in Next.js 15 is a Promise — must be `await`ed

## File size compliance
All components target <400 LOC. StrategyConfigurator is ~200 LOC (long but specified). ReplicationGuide ~130 LOC. EngineRoom ~150 LOC.

## Design gate
`.design-approved.json` updated to include `frontend/src/components/trading/` and `frontend/src/app/strategies/lab/` paths before any frontend file creation.

## Chosen approach
- Query helpers: server-only, typed rows, NUMERIC as strings
- Components: 'use client' where state/interaction needed, RSC otherwise
- Charts: Recharts (RadarChart, AreaChart, LineChart, BarChart) — matching existing chart patterns
- No `iterrows`, no `pd.apply` (Python-side already done; this is pure frontend)
