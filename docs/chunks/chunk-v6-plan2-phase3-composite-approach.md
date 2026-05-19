# Approach: v6 Plan 2 Phase 3 — Composite Scorer + Selection + Buffer Zones

## Chunk reference
Plan: `docs/superpowers/plans/2026-05-19-v6-plan-2-backend-trading-engine.md` Phase 3
Spec: `docs/superpowers/specs/2026-05-18-v6-rs-trading-model-design.md` §6

## Data scale
No DB access needed. `compute_composite` and `select` operate purely on in-memory pandas
DataFrames / Series. Expected universe size: ~350 rows at rebalance time. Well under 1K
threshold — pandas operations throughout are fine. No SQL needed.

## Approach

### Composite scorer — `compute_composite`
1. Accept `signals_panel: pd.DataFrame` with rows = instrument_id, columns = signal names + 'sector'.
2. For each signal column (not 'sector'):
   a. Compute sector-demeaned mean and std using groupby('sector') on that column.
   b. Map each row's sector stats back and compute z = (signal - sector_mean) / sector_std.
   c. Handle edge case: sectors with 1 member → std = 0 → z = 0 (not NaN).
   d. Winsorize by clipping at ±winsorize_z (default ±3.0).
   e. Multiply by the signal's weight.
3. Sum all weighted z-scores to produce composite per instrument.
4. Return pd.Series indexed by instrument_id.

### Selection — `select`
Per spec §6.4:
1. Start with composite pd.Series indexed by instrument_id.
2. Set composite[governance_excluded] = -inf (removes from ranking).
3. Rank descending (rank 1 = highest composite).
4. Apply buffer zones:
   - rank ≤ enter_rank_cutoff (30) → enter if not held yesterday
   - rank ≤ stay_rank_cutoff (50) AND held yesterday → held
   - rank > stay_rank_cutoff AND held yesterday → exit
   - rank ≤ stay_rank_cutoff AND NOT held AND NOT in trend_gate_pass → bench_hold
5. Forced exit: any held name in governance_excluded → exit (regardless of rank).
6. Return `SelectionResult(entered, held, exited, bench_hold)`.

Entry requires trend gate to pass. Held names are NOT re-gated on trend (they stay until
rank > 50 or governance hit).

## Wiki patterns checked
- `prd-golden-example-testing`: test fixtures mirror spec §6.3-6.4 logic with hand-computed
  expected values.
- `computation-boundary-pattern`: all internal math uses float (z-score arithmetic), no Decimal
  needed since composite is not stored as money. No DB writes in this module.

## Existing code reused
- `atlas/trading/v6/governance.py` shows the dataclass + frozen dataclass patterns used in v6.
- `atlas/trading/v6/universe.py` for structlog usage pattern.
- `tests/trading/v6/conftest.py` for test structure (no DB fixture needed here since these
  tests are fully in-memory).

## Edge cases
- NULL/NaN in signal column: treated as NaN in z-score computation (sector stats skip NaN).
  Rows with NaN composite get composite = NaN → treated as -inf in selection (safe).
- Sector with only 1 member: std = 0 → z = 0 for that row (not excluded, just neutral).
- Empty governance_excluded / trend_gate_pass / held_yesterday sets: safe (empty set membership
  checks return False).
- All names governance-excluded: composite all -inf → empty entered/held → full exit.
- Weights sum != 1.0: normalized internally in SignalWeights.as_dict() via property.
  The spec notes sum=0.99 ≈ 1.0; internal normalization makes this exact.

## File layout
- Source: `atlas/trading/v6/composite.py` — target ~200 LOC (≤ 600 limit)
- Tests: `tests/trading/v6/test_composite.py` — target ~300 LOC (≤ 800 limit)

## Expected runtime
Pure pandas on ≤ 350 rows: < 10ms per call. No DB. No concern on t3.large.

## TDD sequence
1. Write all 8 tests with asserts that will fail (composite.py does not exist).
2. Run pytest — confirm all fail with ImportError or AssertionError.
3. Implement composite.py.
4. Run pytest — all 8 pass.
5. ruff check.
6. Single commit: "forge: chunk-v6-plan2-phase3 — composite scorer + selection + buffer zones".
