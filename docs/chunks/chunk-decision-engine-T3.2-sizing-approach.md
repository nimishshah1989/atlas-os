# Approach: Task 3.2 — Position-Sizing Formula

## Data scale
Pure formula — no DB access, no table reads. No row counts required.

## Chosen approach
Pure Python function with a frozen dataclass result. All arithmetic in Decimal.
No SQL, no pandas, no DB dependency.

## Wiki patterns checked
- `patterns/decimal-not-float.md` — all financial values as Decimal; `Decimal("x")` literals, never float literals
- `patterns/prd-golden-example-testing.md` — hand-compute every golden case in the test, assert exact Decimal values

## Existing code being reused / matched
- `policy.py` — frozen `@dataclass(frozen=True)`, structlog, whole-number percent as Decimal
- `targets.py` — same frozen dataclass style, `_ZERO = Decimal("0")`, `from __future__ import annotations`
- `test_targets.py` — `HOUSE_DEFAULTS_KWARGS` fixture + `_make_policy` helper pattern; per-class test groups with `@pytest.fixture`

## Module design

### `sizing.py`
```
PositionSizeResult(frozen=True)
    suggested_pct: Decimal        # >= 0, whole-number pct
    binding_constraint: str       # 'target_gap' | 'max_per_stock' | 'regime_cap' | 'none'

suggest_position_size(
    target_gap: Decimal,
    max_per_stock: Decimal,
    regime_cap: Decimal,
    current_invested: Decimal,
) -> PositionSizeResult
```

### Formula
```
regime_room = regime_cap - current_invested
raw = min(target_gap, max_per_stock, regime_room)
suggested = max(raw, Decimal("0"))
```

Binding constraint logic:
1. If raw <= 0 (suggested clamped to 0):
   - The argument that drove raw to <= 0 determines the binding term.
   - If target_gap <= 0 → binding = 'target_gap'  (gap is non-positive regardless of others)
   - Elif regime_room <= 0 → binding = 'regime_cap'  (room exhausted/over-invested)
   - Else: target_gap > 0 AND regime_room > 0 but min still <= 0 — impossible because
     max_per_stock is always > 0 (policy invariant: max_per_stock_pct > 0 via validate_policy).
     In practice, only target_gap <= 0 or regime_room <= 0 cause the clamp.
   - Fallback: 'none' (should not be reachable with valid inputs, but safe default)

2. If raw > 0 (not clamped):
   - Identify which of the three terms equals raw (the minimum). First match wins.
   - target_gap == raw → 'target_gap'
   - max_per_stock == raw → 'max_per_stock'
   - regime_room == raw → 'regime_cap'

## Edge cases handled
- target_gap <= 0 (sector already at/above target): clamp to 0, binding = 'target_gap'
- current_invested >= regime_cap: regime_room <= 0, clamp to 0, binding = 'regime_cap'
- All three equal (rare tie): first-match wins per the order above

## Expected runtime
Sub-microsecond — pure arithmetic, 3 Decimal comparisons. No I/O.

## Test cases (hand-computed)
1. Gap-bound: min(2.5, 5, 10) = 2.5 → binding 'target_gap'
2. Stock-cap-bound: min(8, 5, 20) = 5 → binding 'max_per_stock'
3. Regime-cap-bound: min(8, 5, 3) = 3 → binding 'regime_cap'
4. Clamped (at-cap): regime_room = 40-40 = 0 → raw = min(8,5,0) = 0 → suggested 0, binding 'regime_cap'
5. Clamped (over-cap): regime_room = 40-45 = -5 → raw = min(8,5,-5) = -5 → clamp to 0, binding 'regime_cap'
6. Negative gap: target_gap=-1 → raw = min(-1,5,10) = -1 → clamp to 0, binding 'target_gap'
