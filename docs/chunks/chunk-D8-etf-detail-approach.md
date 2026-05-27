# Chunk D.8 Approach — /v6/etfs/[iid] detail page

## Data scale
Frontend-only: queries run via postgres-js against Supabase (same pattern as all v6 pages).
ETF scorecard: ~100 rows. Portfolio: typically 0 rows (v6.0 launch state).

## Chosen approach

Three files: thin RSC page shell (≤250 LOC) + ETFDetailClient.tsx (≤450 LOC) + ETFHero.tsx (≤280 LOC).

Pattern mirrors C.16 (stock detail) exactly:
- page.tsx: fetch data server-side → pass to ETFDetailClient
- ETFDetailClient: tab state + hero + 3 tab panels
- ETFHero: metric tiles (TE, expense, AUM, bid-ask, premium-to-NAV) + PortfolioBadge expanded + thesis bullets

## Wiki patterns checked
- StockHero.tsx / StockDetailClient.tsx → directly lifted for ETF structure
- PortfolioBadge: `variant="expanded"` + `state={holdingState}` (null → silent absence)
- AuditTrailTab: direct consumer, pass `auditTrail={null}` for ETFs (no stock-specific audit)
- GradeChip: maps composite_score to grade

## Existing code reused
- `getEtfsForDate` in `etfs.ts` for single ETF lookup (filter by iid)
- `getHoldingState` from `portfolio_holdings.ts`
- `getAuditTrail` from `audit_trail.ts`
- `getLatestSnapshotDate` from `snapshot.ts`
- All component imports: GradeChip, PortfolioBadge, AuditTrailTab, RankDecompositionCards, MultiBenchmarkRSWaterfall, DataSourceBanner

## Edge cases
- TE/expense/AUM/spread/premium all nullable → render "—" explicitly
- Bid-ask spread: not in current etfs.ts schema → render "—" (v6.1 data)
- Premium-to-NAV: not in current schema → render "—" with "when applicable" note
- Holdings: pulled from `sub_metrics` JSONB if available, else empty state
- AuditTrailTab: pass null (ETF audit trail is v6.1 scope); renders graceful empty state

## Expected runtime
Page load: <400ms (single SQL join, ~100 row table, indexed on snapshot_date + ticker)

## Status: approved for implementation
