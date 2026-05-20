# Chunk 1.8 — Honest Data Provenance Labelling

## Actual data scale
N/A — frontend-only change. No DB rows processed. Query layer adds a constant literal column.

## Chosen approach

### Provenance signal (fund and ETF)
**Signal: constant literal `'legacy'::text AS data_source` in SQL queries.**

The `atlas_fund_signal_unified` and `atlas_etf_signal_unified` views (migration 087) are pure pass-throughs from `atlas_fund_states_daily` and `atlas_etf_states_daily` respectively. There is NO bottom-up engine path in these views — no `data_source` discriminator column exists. Provenance IS derivable without a view change because every row from these views is by definition legacy-sourced. The query layer adds `'legacy'::text AS data_source` as a constant — this is the honest signal, not a guess.

When a future migration adds the v2 bottom-up aggregator path, the constant becomes a CASE expression based on which underlying table the row came from.

### Commodity ETF discriminator
**Signal: `atlas_universe_etfs.theme IN ('Gold', 'Silver')`.**

Confirmed by `atlas/intelligence/aggregations/etf.py`:
```python
_COMMODITY_THEMES: frozenset[str] = frozenset({"Gold", "Silver"})
```
The `ETFRow` type already exposes `theme: string`. Component-level check: `theme === 'Gold' || theme === 'Silver'`.

### UI approach
- `ProvenanceMarker` component: renders `LEGACY` badge (amber) with a Radix Tooltip explaining the legacy vs bottom-up distinction. `data-testid="provenance-legacy-{id}"` for testability.
- `EngineStateCell` function in `ETFScreener`: renders `n/a — commodity ETF` with `data-testid="commodity-etf-na-{ticker}"` for commodity ETFs, `StageBadge` for equity ETFs.
- `FundScreener`: `ProvenanceMarker` inline in the fund name cell.

## Wiki patterns checked
- Existing `InfoTooltip` / `MetricTooltip` pattern used as the basis for `ProvenanceMarker`.
- Radix Tooltip portals don't render in JSDOM (no `ResizeObserver`) — test adapted to verify `aria-label` instead of tooltip content.

## Existing code reused
- `@radix-ui/react-tooltip` (already installed, used by `InfoTooltip`)
- `ProvenanceMarker` is a standalone component, importable in both `ETFScreener` and `FundScreener`

## Edge cases handled
- `data_source` added to `ETFRow`, `FundRow`, `FundMasterRow` TypeScript types
- `USPulseShell.adaptUSETF` adapter updated to include `data_source: 'legacy'` (US ETFs also use the ticker-level legacy path)
- Test factories in existing test files don't include `data_source` — they use `Partial<ETFRow>` spread so this is safe; test files excluded from `tsc` strict compilation

## Expected runtime
No DB impact (constant column). Frontend render: negligible.

## Files modified
- `frontend/src/lib/queries/etfs.ts` — ETFRow type + 3 SQL queries
- `frontend/src/lib/queries/funds.ts` — FundRow/FundMasterRow types + 2 SQL queries
- `frontend/src/components/ui/ProvenanceMarker.tsx` — NEW component
- `frontend/src/components/etfs/ETFScreener.tsx` — isCommodityETF + EngineStateCell + ProvenanceMarker
- `frontend/src/components/funds/FundScreener.tsx` — ProvenanceMarker in fund name cell
- `frontend/src/components/us/USPulseShell.tsx` — adaptUSETF data_source field
- `frontend/src/components/etfs/__tests__/ProvenanceLabel.test.tsx` — NEW 8 tests
