# Chunk D.9 Approach — /regime hero with deployment_multiplier

## Data scale
- `atlas_market_regime_daily`: ~500–700 rows (daily since ~2023). Latest: 2026-05-22 per existing test fixture.
- Deployment multiplier values: {1.0, 0.7, 0.4, 0.0} per migration 004 CHECK constraint.
- Regime states: 'Risk-On', 'Constructive', 'Cautious', 'Risk-Off', 'DISLOCATION_SUSPENDED' per migration 004 + 'Neutral' as fallback.
- Input columns for sparklines: smallcap_rs_z, breadth_pct_above_200dma, vix_percentile, cross_sectional_dispersion — all exist on `atlas_market_regime_daily` per migration 004 + they also appear in `atlas_regime_daily` (migration 080, table `state` not `regime_state` column).
- `atlas_regime_daily` (migration 080) — uses column `state` and is empty per backend audit. Using `atlas_market_regime_daily` as source.
- `flip_probability_5d` — NOT a column on either table. Return null; UI shows "—".
- `days_in_regime` — derive from contiguous streak in Python-free SQL: count consecutive rows with same regime_state ordered by date DESC.

## Chosen approach
- New `getRegimeDetail()` function in `regime.ts` returns `RegimeDetail` type.
- Single SQL query with a lateral streak CTE for days_in_regime.
- 12-week journey: last 84 days (12×7) from `atlas_market_regime_daily`, ordered oldest→newest.
- Input sparklines: read from `atlas_market_regime_daily` for last 84 days.
- flip_probability_5d: null (column absent from table) — UI shows "—".

## Files
1. `frontend/src/lib/queries/v6/regime.ts` — extend with `getRegimeDetail()`
2. `frontend/src/app/regime/page.tsx` — replace with hero layout (thin RSC ≤250 LOC)
3. `frontend/src/components/v6/RegimeHero.tsx` — hero card ≤300 LOC
4. `frontend/src/components/v6/RegimeInputPanel.tsx` — 4 sparklines ≤200 LOC
5. `frontend/src/components/v6/__tests__/RegimeHero.test.tsx` — 5 tests
6. `frontend/src/lib/queries/v6/__tests__/regime.test.ts` — extend with 2-3 cases

## Edge cases
- NULL deployment_multiplier: show "—"
- Cautious regime: pass through as-is, map to warn color
- Empty history: journey strip renders empty segments gracefully
- NULL input sparkline columns: sparkline renders empty span
- Single-row DB: days_in_regime = 1

## Expected runtime
- Query: <5ms (PK date index)
- Page render: <50ms on t3.large
