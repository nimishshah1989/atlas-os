# Chunk M7-T3: overlap.py — Jaccard Similarity Math

## Summary
Pure Python math module for portfolio overlap measurement in the M7 Simulation Platform.
No database, no pandas, no external dependencies beyond stdlib.

## Data Scale
Not applicable — pure mathematical functions operating on in-memory sets.

## Chosen Approach
- Pure Python `set` operations for Jaccard similarity: `|intersection| / |union|`
- `itertools`-style double loop for upper triangle pair generation
- Edge case: both-empty sets → return 0.0 (defined behavior, not undefined)
- Canonical ordering enforced via `str(uuid) < str(uuid)` lexicographic comparison
  to match the CHECK constraint on `strategy_overlap_daily`

## Wiki Patterns Checked
- PRD Golden Example Testing: tests encode exact expected values (1/3 for 50% overlap)
- Binary Identity Tests Drive Config: identity tests force correct formula

## Existing Code Being Reused
None — new `atlas/simulation/` package from scratch.

## Edge Cases
- Empty sets: both empty → 0.0. One empty, one non-empty → 0.0 (union is non-empty)
- Single-element sets: works naturally via set operations
- UUID canonical ordering: str() on UUID produces 8-4-4-4-12 hex string; lexicographic sort is stable

## Expected Runtime
Negligible — pure Python set ops on O(50) instruments per strategy. No I/O.

## Files
- `atlas/simulation/core/overlap.py` — implementation
- `tests/unit/simulation/test_overlap.py` — 7 unit tests
- All `__init__.py` files for new packages
