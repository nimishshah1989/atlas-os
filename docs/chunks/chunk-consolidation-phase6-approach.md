# Phase 6 — ValidatedBadge + WithinStateRankCell Rewire

## Approach

Frontend-only. No backend changes. Three tasks:

1. **Task 6.1** — Rename ConvictionCell → WithinStateRankCell. New component has Props `{value: number | null}`, renders a progress bar and 2-decimal value from within_state_rank (0..1). Old component consumed `ConvictionMapRow` with conviction_score + tier; new component takes a simple float. Consumer: StockScreener. Shell: StocksClientShell → convictionMap prop replaced with validations. page.tsx: getConvictionMap() replaced with getComponentValidations().

2. **Task 6.2** — RS state chips route through ValidatedBadge. component_name='rs', badge=row.rs_state. Applied in both StockScreener and ETFScreener.

3. **Task 6.3** — Risk state chips route through ValidatedBadge. component_name='risk', badge=row.risk_state. Applied in both StockScreener and ETFScreener.

## Edge cases handled
- validations array defaults to [] when not provided (prop has default)
- ValidatedBadge receives undefined (not null) when no match — matches the component's `null | undefined` signature
- rs_state and risk_state may be null; label renders '—' in that case

## Pre-existing failures
9 tests in FundDecisionHistory + FundDeepDiveHeader were already failing before this phase. Not ours to fix.

## Build status
TypeScript compiles clean. ATLAS_DB_URL error at page-data collection stage is pre-existing infrastructure issue.
