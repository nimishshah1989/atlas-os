# Chunk: Task 10 — DEAP-inspired Genome Evolver

## Data scale
No DB queries needed. This is a pure in-memory evolutionary operator acting on
Genome dataclasses. No table access at runtime; only genome.to_dict() /
from_dict() round-trips.

## Approach
Two files: `atlas/trading/evolver.py` + `tests/trading/test_evolver.py`.

### crossover()
Blend crossover (arithmetic average ± small noise) for all float/int params.
Boolean fields (require_stage2_for_entry, npc_overrides_min_hold) are chosen
randomly from either parent. stage3_blocks_entry is always True (per invariant).

After blending, enforce all invariants before constructing Layer1Perception:
- RS cutoff cascade: leader > strong > average > weak (floor each step)
- Breadth cascade: risk_on > constructive > cautious (floor each step)
- Vol cascade: vol_high > vol_elevated (floor vol_high = vol_elevated + 0.05)
- Exit thresholds < entry cutoffs with 2-point gap
- Drawdown cascade: halt < tighten < liquidate

conviction weights (conviction_rs_weight, conviction_mom_weight, etc.) are
in Layer1Perception but not in the spec's example. Include them in crossover
as simple blends. No normalization needed — decision.py uses relative scale.

### mutate()
Use to_dict() → perturb → from_dict() pattern to avoid constructing ALL 27
Layer1 fields manually. Perturb float keys with Gaussian noise scaled by sigma
* (max - min). Int keys: round(float perturbation). Flip bools with 20% prob.
Then re-enforce invariants in the dict before calling from_dict().

### select_survivors()
Sort by sortino + calmar combined score (sum of the two float metrics passed in),
return top N. Simple, no Pareto front needed at this stage — the spec's test
just asserts len==6, not that it's a true Pareto front.

## Wiki patterns consulted
- Decimal Not Float (N/A here — pure float domain for search space bounds)
- PRD Golden Example Testing — spec test cases drive implementation

## Existing code reused
- GenomeFactory.random() — used in tests
- genome.to_dict() / from_dict() — used in mutate()
- Layer1Perception.__post_init__ invariants — enforced before construction

## Edge cases
- All float blends must clamp to bounds before clamping cascade constraints
- vol_high could become <= vol_elevated after blend+noise; clamp to elevated + 0.05
- DD cascades can violate after mutation; re-enforce with offset additions
- sigma=0 should produce no effective change (handled by Gaussian with 0 std)
- empty pool → return []

## Expected runtime
All in-memory operations. Under 1ms per call on t3.large.

## File size target
Under 350 LOC (well under 400 hook limit).
