# Chunk: Consolidation Phase 5 — Legacy Chip Deletion

## Summary
Pure frontend deletion pass. No DB changes, no backend changes.
Removes three families of legacy UI chips that the IC-validated state engine has made redundant.

## Tasks
- Task 5.1: Drop `StateTuple4` from `stock-formatters.tsx` and its import in `StockDeepDiveHeader.tsx`
- Task 5.2: Drop `StateJourneyCompact`, `FundStateJourneyCompact`, and their API routes
- Task 5.3: Drop `SignalCell`, all CTS components, `StockHistoryTab`, and CTS API routes

## Consumer map (from grep)

### Task 5.1 — StateTuple4
- `frontend/src/lib/stock-formatters.tsx` — define and delete here
- `frontend/src/components/stocks/StockDeepDiveHeader.tsx` — import + JSX, remove both

### Task 5.2 — StateJourneyCompact / FundStateJourneyCompact
- `frontend/src/components/ui/StateJourneyCompact.tsx` — DELETE file
- `frontend/src/components/funds/FundStateJourneyCompact.tsx` — DELETE file
- `frontend/src/app/api/states-compact/route.ts` — DELETE file
- `frontend/src/app/api/fund-states-compact/route.ts` — DELETE file
- Consumers to rewire:
  - `StockDeepDiveBody.tsx` — imports StateJourneyCompact + StateHeatmap from StockHistoryTab (remove both)
  - `StockScreener.tsx` — StateJourneyCompact in expanded row (remove import + JSX)
  - `ETFScreener.tsx` — StateJourneyCompact in expanded row (remove import + JSX)
  - `FundDeepDiveHeader.tsx` — FundStateJourneyCompact in state history section (remove import + JSX + section)

### Task 5.3 — SignalCell + CTS + StockHistoryTab
- Files to git rm: SignalCell.tsx, CTSDeepDiveCard.tsx, CTSGradeSummaryCards.tsx, CTSIndexTimingPanel.tsx,
  CTSSectorPanel.tsx, CTSSignalBadge.tsx, CTSTimingCell.tsx, StockHistoryTab.tsx,
  app/api/cts/ dir, app/api/stocks/[symbol]/cts-brief/ dir
- Consumers:
  - `StockDeepDiveBody.tsx` — StateHeatmap import from StockHistoryTab (remove)
  - `StockOverviewTab.tsx` — CTSDeepDiveCard import + JSX block (remove)
  - `StockScreener.tsx` — SignalCell import, CTSTimingCell import, CTSSignalBadge imports (StageBadge/SignalBadge),
    cts_timing/cts_stage/cts_signal/signal columns from header and rows
  - `StocksClientShell.tsx` — CTSGradeSummaryCards, CTSIndexTimingPanel, CTSSectorPanel imports + JSX
  - `screener-utils.tsx` — cts_timing, cts_stage, cts_signal entries from OPTIONAL_COLS + COL_TOOLTIPS

## Approach
- Each task is its own commit
- After each task: `npm run build` must pass clean, then `npx vitest run`
- FundDeepDiveHeader.test.tsx will need mstar_id field removed from BASE_MASTER if FundStateJourneyCompact removal affects it — check carefully
- StateHeatmap is exported from StockHistoryTab, used in StockDeepDiveBody — both get removed together in task 5.3

## Edge cases
- `StateHeatmap` is imported in `StockDeepDiveBody.tsx` from `StockHistoryTab` — needs to be removed as part of task 5.3 (or task 5.2 if it's the StateJourneyCompact section)
- `CTSSignalBadge.tsx` exports `StageBadge` and `SignalBadge` — both used in StockScreener; must remove those columns
- `screener-utils.tsx` has CTS entries in OPTIONAL_COLS and COL_TOOLTIPS — both need trimming
- Keep `signal` column in screener-utils OPTIONAL_COLS? No — spec says drop SignalCell; `signal` col uses SignalCell
- ALWAYS_VISIBLE_COL_COUNT is 11 — removing signal/cts cols reduces optional count, not the constant

## Files NOT modified
- MasterStateCard, ComponentScorecard, ComponentValidationRow, OBVContinuousChart, ATRContractionGauge, WithinStatePeers, DwellTimeline, ValidatedBadge
- SectorBadge, IntradayStockBadge
