# Chunk T2.6 — Recommendations read the Policy

## Problem
`/stocks` flow mode should filter candidates using the active portfolio's effective policy (buy_states, min_within_state_rank, min_rs_rank). `/sectors` should show policy-capped targets from `derive_sector_targets`.

## Real column names (from `stocks.ts` query)
- State: `engine_state` (string | null) — the Weinstein state from `atlas_stock_signal_unified`
- Within-state rank: `within_state_rank` (number | null) — fraction [0,1]
- RS rank: `rs_rank_12m` (number | null) — fraction [0,1]

Policy convention: `buy_states` is a string[], `min_within_state_rank` and `min_rs_rank` are Decimal fractions [0,1].

## Active portfolio selection
No existing active-portfolio mechanism exists in the `/stocks` page. Simplest honest approach: `?portfolio=<uuid>` searchParam alongside the existing `?sector=`. The page server component reads it, loads `getEffectivePolicy(portfolioId)`, and passes the resolved entry-rule params down.

## Entry-rule filter placement
Placed in `frontend/src/lib/policy-entry-filter.ts` — a pure TS function. Rationale:
1. The consumer (`StockScreener`) is a frontend component working over already-fetched data.
2. Applying the filter server-side in the page would require re-fetching or a separate query; client-side filtering over an already-fetched array is cheap (screener operates on < 500 stocks).
3. Keeps the function independently testable with no DB/server dependencies.

## Sector targets wiring
`SectorSnapshot` already has `pct_stage_2`. We need `mean_within_state_rank` from `atlas_sector_signal_unified`. Plan:
1. Add `mean_within_state_rank: number | null` to `SectorSnapshot` type and the SQL query in `getSectorsWithMomentum`.
2. Add `getSectorPolicyTargets(portfolioId, regimeCap)` server action in `frontend/src/app/sectors/actions.ts` that calls the backend API or computes inline.
3. Since `derive_sector_targets` is a Python function, expose it via a new server-only TS function that mirrors the formula (Decimal-safe), OR call the existing Python backend. Given no FastAPI endpoint exists yet for this, the clean path is: mirror the pure formula in TS in `frontend/src/lib/sector-targets.ts` (same formula as `targets.py`, all in number arithmetic — acceptable here because these are display-only percentages, not stored money values).
4. Wire `/sectors` page: compute targets in the server component when `?portfolio=` is present; pass to `SectorViews` → `SectorDecisionTable`.

## Edge cases
- NULL `engine_state`: excluded (cannot match any buy_state list)
- NULL `within_state_rank`: excluded if `min_within_state_rank > 0` (honest — rank unknown)
- NULL `rs_rank_12m`: excluded if `min_rs_rank > 0`
- Empty `buy_states` list in policy: no stock passes (policy says "buy nothing" — valid override)
- No active portfolio: show engine view unfiltered; no targets column on sectors

## Expected data scale
~500 stocks in universe. Pure in-memory filter on JS array. Sub-millisecond.

## Tests (TDD)
1. Python: `tests/intelligence/policy/test_entry_filter.py` — `apply_entry_filter` pure function
2. TypeScript: `frontend/src/lib/__tests__/policy-entry-filter.test.ts` — same logic
3. DoD #4: two policies (strict vs loose) over same candidates → different result sets
4. Sector targets: `frontend/src/lib/__tests__/sector-targets.test.ts` — formula mirroring targets.py
