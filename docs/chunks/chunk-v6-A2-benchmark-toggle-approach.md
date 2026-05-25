# Chunk A.2 — Gold availability query + BenchmarkToggle

## Data scale
Not a heavy query — `de_index_prices` is an index-prices table. A `SELECT EXISTS` with `WHERE benchmark_code = 'GOLD' LIMIT 1` is O(1) with an index on `benchmark_code`. No row count scan needed.

## Chosen approach
- **gold_availability.ts**: `import 'server-only'` + postgres-js tagged template + `React.cache()` for per-request memoization. Follows identical pattern to all other `lib/queries/v6/*.ts` modules.
- **persistence.ts**: `useBenchmarkPreference` was already fully implemented in A.1 (not a stub). No modification needed — the function already follows the URL+LS pattern with correct defaults (`nifty500`), LS key format (`v6.benchmark.<pageKey>`), and URL param key (`benchmark`).
- **BenchmarkToggle.tsx**: Mirror of TenureToggle exactly — same `role="radiogroup"` + `role="radio"` ARIA, same roving-tabindex pattern, same controlled/uncontrolled prop split. Adds `goldAvailable: boolean` prop to conditionally render the third pill.

## Wiki patterns checked
- Checked `lib/queries/v6/sectors.ts` for postgres-js tagged template usage — matched.
- Checked `lib/db.ts` for pool config — `import sql from '@/lib/db'` is the correct pattern.
- Checked `TenureToggle.tsx` for ARIA + keyboard pattern — mirrored exactly.

## Existing code reused
- `useBenchmarkPreference` from `persistence.ts` (A.1 — already complete).
- `readLS`/`writeLS` helpers from `persistence.ts` (shared, no duplication).
- Tailwind class strings mirrored from `TenureToggle.tsx`.

## Edge cases
- **Gold unavailable + URL has `benchmark=gold`**: `activeBenchmark` falls back to `DEFAULT_BENCHMARK` (`nifty500`) since the gold pill is not rendered.
- **Gold unavailable + LS has `gold`**: same fallback — `useBenchmarkPreference` returns `'gold'` but the component overrides it to `nifty500` before rendering.
- **React.cache() wrapping**: mocked in tests by replacing `cache` with identity function `(fn) => fn`.
- **`rows[0]?.exists ?? false`**: handles empty result (no rows) safely.

## Architecture call differing from A.1
None. The `goldAvailable` prop is passed from a server parent (layout/page) — the client component does not call `isGoldAvailable()` directly, enforcing the server-only boundary.

## Expected runtime on t3.large
The `SELECT EXISTS` query with an indexed `benchmark_code` column will complete in <5ms. React.cache() ensures it runs at most once per server render.

## Files
- `frontend/src/lib/queries/v6/gold_availability.ts` (31 LOC)
- `frontend/src/lib/queries/v6/__tests__/gold_availability.test.ts` (40 LOC)
- `frontend/src/components/v6/BenchmarkToggle.tsx` (142 LOC)
- `frontend/src/components/v6/__tests__/BenchmarkToggle.test.tsx` (167 LOC)
- `frontend/src/lib/v6/persistence.ts` — no modification needed (147 LOC, already complete)
