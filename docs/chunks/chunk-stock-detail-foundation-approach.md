# Chunk: Stock Detail Page Foundation (Steps 1-3)

**Date:** 2026-05-18
**Branch:** feat/atlas-strategy-lab

## Scope

3 files:
1. `frontend/src/lib/queries/states.ts` — server-side query module for `atlas_stock_state_daily` + `atlas_state_dwell_statistics`
2. `frontend/src/lib/queries/component_validation.ts` — server-side query module for `atlas_component_validation` (5-min memory cache)
3. `frontend/src/components/ui/ValidatedBadge.tsx` — reusable badge with IC-validation status rendering

No touching of `page.tsx` or feature components yet.

## Data scale (not applicable — frontend query module, no Python)

This is a Next.js server-side query file. Queries target:
- `atlas.atlas_stock_state_daily` — latest single row per instrument (LIMIT 1 query); 252-day lookback for history; top-30 peer query
- `atlas.atlas_state_dwell_statistics` — single row per cohort/state
- `atlas.atlas_component_validation` — small reference table (~50 rows), memory-cached 5 min

All queries are bounded and index-targeted. No full-table scans.

## Approach

### SQL helper pattern
Existing repos use `import sql from '@/lib/db'` (the `postgres` template-tag client). Every existing query file follows this exact pattern. The `sql` export is the postgres tagged-template function — queries are `sql\`SELECT ...\`` returning typed arrays.

The `server-only` sentinel is used in all query files — enforced by Next.js to prevent client-side import.

### Type safety
- `NUMERIC` columns from postgres come back as strings in postgres.js. For ratio/IR columns (mean_ic, ic_ir, q5_q1_spread) the spec explicitly casts to `float8` at SELECT time — this is correct for display-only coefficients per the financial guardrail (non-price, non-AUM).
- State columns (enums) come back as strings and are typed as union types.
- `dwell_percentile`, `within_state_rank` etc. are nullable integers — typed as `number | null`.

### Memory cache in component_validation.ts
Module-level variables `_cache` and `_cacheAt` — standard singleton pattern for rarely-changing reference data. TTL 5 min. Safe in Next.js server-component context (single process per dyno).

### ValidatedBadge
Pure server component (no `'use client'`). Receives pre-fetched `ComponentValidation | null`. Native HTML `title` attribute for tooltip (no dependency on `@radix-ui/react-tooltip`) to keep this foundational component simple and dependency-free. Follows existing Tailwind token conventions from `StateBadge.tsx` and `InfoTooltip.tsx`.

### Tests
- Vitest + RTL (confirmed in `vitest.config.ts`, `vitest.setup.ts`)
- `__tests__/states.test.ts` — type-shape tests for `StockState`, `CohortBaseline`, `StateHistoryEntry`, `WithinStatePeer` interfaces + `getStockCohortKey` branching logic (mocked sql)
- `__tests__/ValidatedBadge.test.tsx` — render tests for all 4 status variants (validated, validated_inverse, weak, decorative)

### Wiki patterns checked
- "SQL Window Computation" — relevant; confirms SQL-side aggregation is correct approach for dwell statistics
- "Idempotent Upsert" — not relevant to query layer but confirms pattern for state tables upstream

### Edge cases handled
- `getStockState` returns `null` if no row exists (new instrument not yet classified)
- `getCohortBaseline` returns `null` if cohort not in statistics table
- `getStockCohortKey` returns `'small_cap'` as default when no universe row
- `ValidatedBadge` with `validation=null` renders plain text (no implied action)
- `decorative` status without `decorativeContinuousValue` renders plain text label

### Expected runtime
Query files: no runtime cost at module load. Individual queries at request time:
- `getStockState`: ~2ms (single row, indexed by instrument_id + classifier_version + date)
- `getComponentValidations`: ~1ms on cache hit; ~5ms on cache miss
- `getWithinStatePeers`: ~10ms (JOIN on date+state, up to 30 rows)
- `getStateHistory`: ~5ms (252 rows by instrument_id)
