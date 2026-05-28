# Chunk: ETFs Page 07 + 07a Extension
**Date:** 2026-05-27
**Status:** planning

## Data Scale
- mv_etf_list_v6: ~34 rows (latest-only snapshot, one per active ETF)
- mv_etf_deepdive: ~34 rows + JSONB (price_180d: 180 elements/row, peer_set: 5 elements/row)
- Scale: under 1K rows — all processing works (Python/JS, no SQL aggregation needed)

## MV Schemas (from migration files 107 + 108)

### mv_etf_list_v6 columns (relevant subset)
- ticker, etf_name, fund_house, asset_class, etf_category, underlying_sector
- composite_score, is_atlas_leader, premium_bps, te_60d, adv_20d_inr
- ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m
- rs_state, momentum_state, action (BUY/AVOID/WATCH derived)
- scatter_zone (clean_buy / discount_outlier / premium_outlier / low_adv / premium_unknown)
- adv_monthly_cr (proxy AUM in Cr)
- signal_action, signal_fire_date, signal_confidence

### mv_etf_deepdive columns
- All of the above (denormalized) plus:
- price_180d: JSONB array [{date, open, high, low, close, volume}] × 180 elements
- peer_set: JSONB array [{ticker, composite_score, adv_20d_inr, ...}] × ~5 elements

## Approach

### Query Layer: frontend/src/lib/queries/v6/etfs.ts
ADD new exports to existing file (do NOT rewrite it):
1. `getEtfsList()` — query atlas.mv_etf_list_v6 (replaces direct table queries)
2. `getEtfDeepdive(ticker)` — query atlas.mv_etf_deepdive WHERE ticker = $1
3. `getAmcAggregates(rows)` — pure JS GROUP BY fund_house on the 34-row set (no SQL needed at this scale)

### List Page: frontend/src/app/etfs/page.tsx
Strategy: ADD new sections ABOVE the existing screener. Do NOT break existing ETFMetricTiles/ETFScreener/ETFBubbleChart/ETFIntelligencePanel.

New sections (in order):
1. Hero stats bar (6 tiles) — universe/AUM/BUY/premium-outliers/TE-median/ADV-total
2. HeroStories.tsx — 4 columns: Cleanest BUYs / Tightest TE / Liquidity warnings / Premium outliers
3. CategoryBands.tsx — 4 cards (Index/Sector/SmartBeta/Commodity+Intl) with count, action mix, top names
4. AmcTileRow.tsx — 9 AMC tiles sorted by AUM, colored by action mix
5. PremiumDiscountScatter.tsx — Recharts ScatterChart: x=premium_bps, y=log(adv_20d_inr), color=scatter_zone
6. [existing screener preserved as-is]

### Detail Page: frontend/src/app/etfs/[ticker]/page.tsx
Strategy: ADD v6 sections BELOW existing deep-dive tabs. Fetch mv_etf_deepdive in parallel with existing queries.

New sections:
1. EtfHeroStrip.tsx — verdict strip (6 tiles: 12M return, TE, premium, ADV, AUM, TER)
2. PriceMultidim180d.tsx — Recharts ComposedChart from price_180d JSONB (line + bar volume + 20D-MA line)
3. NavVsMarketPrice.tsx — premium_bps single value + ±25bps context (no time series yet)
4. TrackingError12m.tsx — te_60d snapshot bar with TE quality zones
5. PeerSetTable.tsx — table from peer_set JSONB array

### Component Namespace: frontend/src/components/v6/etfs/
All new components go here. Existing components in v6/ are READ ONLY.

## Wiki patterns checked
- SQL Window Computation — not needed (34 rows, JS GROUP BY is fine)
- Idempotent Upsert — N/A (read-only frontend)
- Young-Instrument Partial Metrics — handle NULL premium_bps gracefully (migration 108 notes iNAV may not be backfilled)

## Existing code reused
- ETFsList, ETFDetailClient, ETFHero — preserved untouched
- GradeChip, DataSourceBanner — available for import
- BubbleRiskReturnChart — existing; PremiumDiscountScatter is different (Recharts ScatterChart with zone tints)
- signedPct, toNumber from @/lib/v6/decimal

## Edge cases
- premium_bps: may be NULL (iNAV not yet backfilled) — render "—" or "N/A"; scatter still plots at x=0 with grey color
- price_180d: may be NULL (ETF OHLCV not in de_etf_ohlcv) — render empty state "Price history not yet available"
- peer_set: may be NULL (ETF has no category peers) — render "No peer data"
- adv_20d_inr: may be NULL — log(0) guard; use 0 for y-axis
- fund_house grouping: multiple aliases for same AMC (e.g., "Nippon" vs "NIPPON INDIA") — normalize to uppercase display

## Expected runtime
- Query (34 rows): <100ms
- JS aggregations (34 rows): <1ms
- Recharts render: <200ms
- Total page load: <500ms on t3.large

## Files to create/modify
1. frontend/src/lib/queries/v6/etfs.ts — ADD getEtfsList, getEtfDeepdive exports
2. frontend/src/app/etfs/page.tsx — ADD new sections
3. frontend/src/app/etfs/[ticker]/page.tsx — ADD v6 deepdive sections
4. frontend/src/components/v6/etfs/HeroStories.tsx
5. frontend/src/components/v6/etfs/AmcTileRow.tsx
6. frontend/src/components/v6/etfs/PremiumDiscountScatter.tsx
7. frontend/src/components/v6/etfs/CategoryBands.tsx
8. frontend/src/components/v6/etfs/EtfHeroStrip.tsx
9. frontend/src/components/v6/etfs/PriceMultidim180d.tsx
10. frontend/src/components/v6/etfs/NavVsMarketPrice.tsx
11. frontend/src/components/v6/etfs/TrackingError12m.tsx
12. frontend/src/components/v6/etfs/PeerSetTable.tsx
13. frontend/src/components/v6/etfs/__tests__/etfs-page07.test.tsx
