# Chunk: Stock Detail Page — Steps 4-5 (MasterStateCard + ComponentValidationRow + ComponentScorecard)

## Context

Building three React server components for the stock detail page redesign (spec: 2026-05-18-stock-detail-page-redesign.md).
Foundational queries (getStockState, getCohortBaseline) and ValidatedBadge already shipped in commit 0cba48d.

## Data scale

This is purely frontend — no DB queries in these components. All data is passed as props from server-side query calls.
StockState row: ~30 columns, 1 row per render. CohortBaseline: 1 row. ComponentValidation: ~20 rows total (cached).
No scale concerns.

## Types consumed (already exist)

- `StockState` from `@/lib/queries/states`
- `CohortBaseline` from `@/lib/queries/states`
- `ComponentValidation` from `@/lib/queries/component_validation`
- `ValidatedBadge` from `@/components/ui/ValidatedBadge`

## Approach

### MasterStateCard.tsx (~150 LOC)

Pure server component (no `'use client'`). Sticky via CSS `position: sticky; top: 0; z-index: 30`.
Uses `bg-paper` token so it doesn't go transparent on scroll.

Key logic:
- State-to-label + state-to-color mapping: hardcoded object lookup
- Urgency icon: Lucide AlertTriangle (urgent) / Clock (late) / none (normal/n/a)
- Action text: hardcoded `(state, urgency) → string` table
- Dwell line: "Day X of Y (cohort, p75=Z)" or "Day X · no cohort baseline yet" when null
- within_state_rank breakdown: freshness = `1 - (dwell_days / p75_dwell_days)` clamped [0,1]; RS from state.rs_rank_12m; vol = "n/a" with tooltip

### ComponentValidationRow.tsx (~100 LOC)

Pure server component. CSS grid `grid-cols-[160px_1fr_auto] items-center gap-4`.
Renders: label (left, uppercase, ink-secondary) | ValidatedBadge (middle) | IC stats (right, font-mono, text-xs, ink-tertiary).
Skips IC stats when validation is null or status is 'decorative'.

### ComponentScorecard.tsx (~80 LOC)

Pure server component. Section with "Signal scorecard" header.
Phase 1: renders RS row + state row + dwell row.
OBV / ATR / realized-vol-tier rows deferred to step 6 — explicit TODO comments.

Derives RS tier from `state.rs_rank_12m`:
- >= 0.8 → "Leader"
- >= 0.6 → "Strong"
- >= 0.4 → "Average"
- >= 0.2 → "Weak"
- < 0.2 → "Laggard"

## Wiki patterns checked

- Javeri DESIGN.md: warm ivory paper, teal #1D9E75, sentence-case copy, ALL CAPS for tier labels
- Existing sticky: `sticky top-14 bg-paper border-b border-paper-rule z-30` from StockDeepDiveHeader
- Tailwind tokens used: bg-paper, border-paper-rule, text-ink-primary/secondary/tertiary, text-signal-pos/warn/neg, font-mono, tracking-[0.22em]
- Test pattern: Vitest + RTL with `describe/it/expect`, fixture `makeValidation()` factory, `toBeInTheDocument()`, class assertions

## Edge cases

- cohortBaseline is null: render "Day X · no cohort baseline yet"
- p75_dwell_days is null: skip freshness computation, show "freshness n/a"
- rs_rank_12m is null: show "rs n/a"
- within_state_rank is null: show "—"
- peerRank is null: show "—" instead of "#N of M"
- All (state, urgency) combos not in table: fallback to empty string (no action shown)

## Existing code reused

- `ValidatedBadge` (commit 0cba48d) — no changes
- `StockState`, `CohortBaseline`, `ComponentValidation` types — no changes
- Tailwind tokens from `StockSnapshotTiles.tsx`, `StockDeepDiveHeader.tsx`

## Expected runtime

Render-time only: O(1) JS. No DB calls in these components.

## File size

- MasterStateCard.tsx: ~145 LOC (under 600 limit)
- ComponentValidationRow.tsx: ~90 LOC (under 600 limit)
- ComponentScorecard.tsx: ~75 LOC (under 600 limit)
- Test files: ~200 LOC each (under 800 limit)
