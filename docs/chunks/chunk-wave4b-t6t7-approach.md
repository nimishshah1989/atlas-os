# Wave 4B Tasks 6 & 7 — Methodology + Health Page Rewrite Approach

**Date:** 2026-05-20
**Branch:** feat/atlas-consolidation
**Tasks:** T6 (methodology page), T7 (health page)

## Files in scope

- `frontend/src/components/methodology/MethodologyTabs.tsx` (primary content rewrite)
- `frontend/src/app/methodology/page.tsx` (footer date update only)
- `frontend/src/app/health/page.tsx` (add KnownGapsPanel below existing components)
- `frontend/src/components/health/KnownGapsPanel.tsx` (new static component)
- `frontend/src/__tests__/methodology/MethodologyTabs.test.tsx` (new)
- `frontend/src/__tests__/health/KnownGapsPanel.test.tsx` (new)

## Approach

### Task 6 — Methodology

The existing MethodologyTabs has 6 tabs: overview | states | regime | sectors | conviction | admin.
Content is accurate for the earlier phase but predates the v2 decision engine spec.

Strategy: **rewrite the overview tab** and **update the sectors tab** in place; the other four tabs have accurate, still-current content for their specific areas (stock states, regime breadth, conviction/IC, admin).

#### Overview tab changes
Replace the current "What is Atlas / Morning workflow / four pillars" content with:
1. **Layered targets** — sector targets (WHAT) filled by instrument picks (WHICH)
2. **Policy rails** — `recommendation = engine_signal ∩ policy_constraint`; per-portfolio Policy mandate
3. **The 6-step decision flow** — Regime → Sector rotation → Fill target → Conviction check → Act → Deterioration loop
4. **4-signal scorecard** — Trend / Breadth / Momentum / Participation (bottom-up from stock states)

Keep the "four measurement pillars" grid as a navigation aid; update its text to reflect v2 framing.

#### Sectors tab changes
Add a new sub-section **"Hybrid rank + absolute floor"** explaining:
- Cross-sectional ranking (sectors scored daily; percentile bands assign labels)
- Absolute floor: a sector can hold Overweight only if its absolute breadth clears the floor
- Same pattern applies to fund classifier (Recommended / Hold / Reduce / Exit)
- Weinstein state engine aggregation: sector view is bottom-up from `pct_stage_2/3/4`

### Task 7 — Health page

The health page already has live data components (HealthHeader, HealthSummaryCards, PipelineRunsTable, FreshnessTable, JipSyncPanel, AnomaliesPanel, ValidatorScorecard). These all stay.

Add a **KnownGapsPanel** — a static, honest note with no live query needed:
- Holdings ingestion stale: `de_mf_holdings` / `de_etf_holdings` stuck ~2026-05-04 (JIP shareholding_pattern job failed)
- Adjustment factors stale: `de_adjustment_factors_daily` ~26 days stale
- Engine coverage: v2 state engine classifies the universe daily; T-1 current
- Validator role: 6 issue classes; runs nightly + pre-milestone
- "Last reviewed 2026-05-20" timestamp

The panel renders AFTER the existing component chain — no structural change to the page.

## Size check

MethodologyTabs is currently 556 LOC. Rewriting overview + sectors sections will keep it under 600 (the file has `// allow-large` already). No split needed.
KnownGapsPanel will be ~80 LOC. health/page.tsx stays ~60 LOC.

## Edge cases

- The MethodologyTabs `allow-large` comment already exists — no new escape valve needed.
- KnownGapsPanel is purely static (no server query) — no async/DB dependency.
- Tests: render tests using @testing-library/react with jsdom; no DB calls.

## Expected runtime

Build: ~30s. Tests: <5s.
