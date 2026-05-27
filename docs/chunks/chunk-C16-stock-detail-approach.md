# Chunk C.16 — /v6/stocks/[iid] detail page approach

## What already exists

- `page.tsx` (55 LOC) — thin RSC fetching `getInstrumentDetail` + `getCellDefinitions`, renders `<StockDetailClient>`. Needs full rework to fetch all C.16 data.
- `StockDetailClient.tsx` (130 LOC) — existing basic ConvictionTape + ReturnTiles. Will be replaced with hero + 3-tab layout.

## Approach

### page.tsx (stays ≤250 LOC)
- RSC fetches all server-side data in parallel: instrument detail, holding state, stock technicals, multi-tenure returns, signal calls (last 20), funds holding stock, audit trail.
- Passes everything to `<StockDetailClient>` as props.
- CrossRuleDepth: query `atlas_cell_rule_candidates` for the firing cell_id. Count how many rule candidates fire today. This is a server-side lookup using the iid's active signal_call cell_id from the audit trail.
- Keep `force-dynamic`.

### StockDetailClient.tsx (≤500 LOC)
- `"use client"` — owns tab state (Overview/Technicals/Audit).
- Renders `<StockHero>` + 3-tab switcher.
- Delegates tab content to: Overview inline section, `StockTechnicalsTab`, and `AuditTrailTab` (lazy import with fallback).

### StockHero.tsx (≤350 LOC)
- Grade chip (from conviction tape dominant direction mapped to a grade), ticker, company name, sector pill.
- ConvictionTape (full-width).
- Action verb from thesis registry.
- 3-5 thesis bullets.
- PortfolioBadge expanded variant (silent when null).
- PositionSizingWidget.
- CrossRuleDepth metric: "Conviction depth: N/5 rules" — color signal-pos (5/5), signal-warn (3-4), signal-neg (0-2).
- 52w-high distance from stock_technicals.pct_from_52w_high.
- Drawdown from peak from stock_technicals.drawdown_from_peak.

### Tab structure (inline in StockDetailClient)
- **Overview**: MultiBenchmarkRSWaterfall + RankDecompositionCards + funds holding stock table.
- **Technicals**: Stock technicals grid (EMA distances, RSI, OBV, ATR, 52w range) + multi-tenure returns table.
- **Audit**: AuditTrailTab component (lazy-loaded; fallback placeholder if E.1 not landed).

### AuditTrailTab handling
Check if `frontend/src/components/v6/AuditTrailTab.tsx` exists. It does not yet — use a lazy-import with a try/catch or a simple fallback div that says "Audit Trail (coming in v6.0 final)".

### CrossRuleDepth query
New server query in `page.tsx`: query `atlas_cell_rule_candidates` for the active cell's rule candidates, then count how many have `fires_today = true` (or similar) for this iid. If the table doesn't exist yet, return null gracefully.

### Data sources
- `getInstrumentDetail` → ScreenStock (existing)
- `getHoldingState` → HoldingState | null (existing B.1)
- `getStockTechnicals` → StockTechnicals | null (existing C.3)
- `getMultiTenureReturns` → MultiTenureReturns | null (existing C.5)
- `getSignalCallsByIid` → SignalCallEvent[] (existing C.6)
- `getFundsHoldingStock` → FundHolding[] (existing B.3)
- `getAuditTrail` → AuditTrail | null (existing C.4)
- CrossRuleDepth → new inline query (atlas_cell_rule_candidates)

### Tests (StockDetailClient.test.tsx, 5 cases)
1. Hero renders with grade chip + ticker + PortfolioBadge expanded when held
2. PortfolioBadge silently absent when holdingState === null
3. CrossRuleDepth shows "N/5 rules" when depth provided; shows "—" when null
4. Tab switching works (Overview → Technicals → Audit)
5. CrossRuleDepth color classes: 5/5=signal-pos, 3-4=signal-warn, 0-2=signal-neg

## Edge cases
- `pct_from_52w_high` NULL → show "—"
- `drawdown_from_peak` NULL → show "—"
- `getFundsHoldingStock` returns [] → show "No funds holding this stock"
- `getAuditTrail` returns null → Audit tab shows skeleton/empty state
- CrossRuleDepth: atlas_cell_rule_candidates query errors → return null gracefully

## LOC budget
- page.tsx: ≤250 LOC
- StockDetailClient.tsx: ≤500 LOC
- StockHero.tsx: ≤350 LOC
- Test file: ≤400 LOC
