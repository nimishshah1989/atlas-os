# Chunk: v6 Plan 2 Phase 4 — HRP Portfolio Construction

**Date:** 2026-05-19
**Files:** `atlas/trading/v6/portfolio.py`, `tests/trading/v6/test_portfolio.py`

## Actual data scale

This module is purely in-memory math — no DB access. The input `returns_panel`
is a 252-row × N-col DataFrame where N ~ 25-40 (the selected cohort). At that
scale pandas + numpy is the correct choice; no SQL, no chunking needed.
Runtime: < 50ms per allocation call on t3.large.

## Chosen approach

Pure Python/NumPy/pandas/scipy implementation. No DB reads inside `allocate()`.
All three HRP steps follow López de Prado 2016 exactly:

1. **Correlation → distance** — `dist = sqrt(0.5 × (1 - corr))`. Produces
   values in [0, 1]. scipy `squareform()` converts the symmetric matrix to
   condensed form for linkage.

2. **Linkage** — `scipy.cluster.hierarchy.linkage(condensed, method='single')`.
   `method='single'` per spec. `_quasi_diagonalize()` extracts the leaf order
   from the linkage tree by recursively splitting clusters (standard LdP
   leaf-reorder).

3. **Recursive bisection** — inverse-cluster-variance allocation, bisecting
   each cluster list at its midpoint. Weight allocated proportional to
   `1 - v_l / (v_l + v_r)` for the left side. This is the standard LdP
   formulation from the spec pseudocode.

4. **Cap stack** — applied in order: single-name (5%) → sector (25%) →
   issuer-group (5%) → weight floor (0.5% drop + re-normalize). Excess from
   binding cap redistributes WITHIN SAME HRP CLUSTER (not flat spray), per
   spec §6.5.

## Wiki patterns checked

- `Computation Boundary` pattern: numpy internally, Decimal externally — not
  applicable here because weights are coefficients (ratios), not money.
  `float` is correct for weights.
- `PRD Golden Example Testing`: tests use hand-computed 5-name cohort so the
  expected output can be verified mathematically.
- `Decimal Not Float` pattern: weights are fractions (not monetary values),
  so float is appropriate. Confirmed by the spec which shows them as floats.

## Existing code being reused

- `tests/trading/v6/conftest.py` — shared fixture for DB tests (not needed
  here since portfolio.py is pure math, but we import the conftest path).
- Pattern from `atlas/trading/v6/risk.py` — module docstring, structlog
  usage, `__all__` export style.

## Edge cases handled

- **Single instrument cohort** — `_quasi_diagonalize` + bisection handle
  len=1 clusters by returning the single item with weight 1.0.
- **NaN in returns** — `corr()` produces NaN for columns with zero variance
  (constant returns). Guard: fill NaN in distance matrix with 1.0 (max
  distance = fully uncorrelated).
- **Zero cluster variance** — `_cluster_variance` guards division by zero:
  if all weights are zero (shouldn't happen but safe), returns 0.0.
- **Cap excess > remaining uncapped** — iterative redistribution loop with
  convergence check (max 10 iterations) to prevent infinite loop when all
  names in cluster are at cap.
- **`dropped_below_floor`** — collected as list of UUIDs; re-normalize after
  dropping.
- **`caps_binding`** — collected as list of strings indicating which caps
  bound at least one name.

## Expected runtime

<1 ms for 30-name cohort. Well within t3.large budget.

## Deviations from spec

None. Implements exactly the three steps + cap stack from §6.5. The
`HrpResult` dataclass adds `cluster_assignment` (C1/C2/...) and
`dropped_below_floor` as specified in the chunk task API.
