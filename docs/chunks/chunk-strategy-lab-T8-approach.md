---
chunk: strategy-lab-T8
project: atlas-os
date: 2026-05-15
status: in-progress
---

# Task 8: vectorbt Simulation Harness — Approach

## Data Scale
- Synthetic test data: 5 stocks x 120 days = 600 rows (well under 1K threshold)
- Production: ~500 stocks x ~5000 trading days = 2.5M rows (would need SQL pivot)
- Test scope is in-memory numpy only — no DB calls

## Chosen Approach
Pure numpy matrix operations + vectorbt v1.0.0 Portfolio.from_signals.

Key findings from vbt API probe:
- `pf.sortino_ratio()`, `pf.calmar_ratio()`, `pf.max_drawdown()` all return `numpy.float64` scalars (not arrays) when `group_by=True, cash_sharing=True`
- `size_type` only supports 'Amount', 'Value', 'Percent' — NOT 'targetpercent' or 'TargetPercent'
- Using `size_type='Percent'` with `size=eff_pos` sizes each position as % of portfolio value

## Wiki Patterns Checked
- Decimal Not Float: All PortfolioConfig fields are Decimal; cast to float only at the computation boundary when passing to numpy/vbt
- Computation Boundary pattern: float↔Decimal conversion at the storage edge; numpy internally

## Existing Code Reused
- `atlas/trading/perception.py`: `compute_blended_rs_pctile`, `derive_rs_state`, `derive_regime_state`, `derive_vol_state`, `derive_momentum_state`, `compute_rs_velocity` (2-arg legacy call)
- `atlas/trading/decision.py`: `compute_conviction`, `apply_entry_rules`, `apply_exit_rules`
- `atlas/trading/genome.py`: `Genome`, `GenomeFactory`
- `atlas/trading/config.py`: `PortfolioConfig`

## Edge Cases
- Window < 20 trading days: return None, skip window
- Empty oos_sortinos list (all windows failed): default 0.0
- NaN from vbt stats: _scalar() collapses NaN → 0.0
- Risk-Off regime: `exits[d, :] = True`, total_trades remains 0 for test
- NaN in blended_rs: skip conviction computation for that cell
- `size_type='Percent'`: in vbt 1.0.0, Percent means percent of current portfolio value

## Risk-Off Test Logic
When `regime_risk_on_breadth_pct=97`, `constructive=96`, `cautious=95`, the synthetic breadth array (uniform 30-80) never reaches 95. All days are REGIME_RISK_OFF (0). The loop sets `exits[d, :] = True` on every day and skips entry. vbt sees zero entries → zero trades.

## Expected Runtime
- 2 tests with 5 stocks × 120 days: < 5 seconds on any machine
- conviction loop is O(n_stocks × n_days) = 600 iterations: negligible

## Files Modified (chunk spec scope)
- `atlas/trading/simulator.py` (new)
- `tests/trading/test_simulator.py` (new)
