# Chunk C.14 — /matrix page + CellMatrix extend

## Data scale
- atlas_cell_definitions: 21 rows (production confirmed; 3 missing: Small/NEG/1m, Small/NEG/12m, Large/POS/1m)
- atlas_cell_rule_candidates: ~89 rows (top-5 per cell, 18 populated cells × 5 = 90)
- atlas_paper_portfolio: 0 rows at v6.0 launch

## Approach

### Data sources
- `getMatrixCells()` — cells.ts (already shipped C.1) — returns MatrixCell[] with confidence_unconditional, friction_adjusted_excess, predicted_excess, drift_status, n_firing_today
- `getHeldIidSet()` — portfolio_holdings.ts (already shipped B.1) — returns Set<string> of held iids
- For n_gate_pass/n_candidates: extend MatrixCell type + getMatrixCells() query with LEFT JOIN to atlas_cell_rule_candidates COUNT. This is a minimal, safe extension.

### Failed-gate microcopy derivation
Three input combos derived from atlas_cell_rule_candidates:
- `(n_gate_pass=0, n_candidates>0)` → "No rule survived"
- `(n_gate_pass=0, n_candidates=0)` → "No candidates tested"
- `(n_candidates IS NULL OR universe_n < 20)` → "Insufficient data"
  - universe_n not in schema; use null check on confidence_unconditional + n_candidates=null as proxy

### Held-count overlay
For a tile to show "N held", we need to count held iids that are currently ACTIVE (exit_date IS NULL) in atlas_signal_calls for that cell. Since atlas_paper_portfolio is empty at v6.0, this will always show 0/nothing at launch — but the logic must be wired.

The cell's "currently-firing iids" come from n_firing_today count, but not individual iids in getMatrixCells(). For the overlay we need a per-cell held count. Two options:
1. Add a `n_held_firing` column to getMatrixCells() via SQL (join atlas_signal_calls → atlas_paper_portfolio)
2. Pass the full held Set to CellMatrix and compute 0 (since portfolio is empty, fast-path)

Option 2 is correct for v6.0: pass `heldIidSet` to CellMatrix; since the set is empty, all tiles show no overlay. When portfolio is populated, the page will need per-cell iid lists which isn't currently in the query. For v6.0, the overlay shows count from SQL join in the query — I'll add `n_held_firing` to getMatrixCells().

### Files modified
1. `frontend/src/lib/queries/v6/cells.ts` — extend MatrixCell + getMatrixCells() with n_gate_pass + n_candidates + n_held_firing (3 new columns via LEFT JOINs)
2. `frontend/src/app/matrix/page.tsx` — switch from getCellDefinitions() to getMatrixCells() + getHeldIidSet(); thin RSC shell
3. `frontend/src/components/v6/CellMatrix.tsx` — client component with GradeChip, drift chip, held overlay, microcopy, ARIA, click nav
4. `frontend/src/components/v6/__tests__/CellMatrix.test.tsx` — 5+ test cases

### Edge cases
- 21 cells returned (not 24): render only what's returned; empty grid slot rendered as dash tile
- Empty heldIidSet (v6.0 launch): no overlay shown; handled silently
- NULL confidence_unconditional: "Insufficient data" path
- drift_status='healthy': chip hidden (not rendered)
- Deprecated drift_status: signal-neg chip

## Expected runtime
- getMatrixCells: ~5ms (21 rows + 2 small LEFT JOINs on indexed columns)
- Page render: <50ms server-side
