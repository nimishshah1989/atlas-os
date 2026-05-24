# Chunk: Strategy Lab Task 7 — Layer 2 Decision Engine

## Data scale
No DB access required. Pure numpy computation. All state arrays produced by Layer 1 (perception.py) and consumed here in-memory.

## Chosen approach
Pure numpy functions — no pandas, no DB. Decision engine operates on scalar inputs per-stock-per-day for `compute_conviction`, and numpy arrays for batch `apply_entry_rules` / `apply_exit_rules`. This matches the vectorbt-compatible design in Layer 1.

## Wiki patterns checked
- `atlas/trading/perception.py` — existing Layer 1 pattern: pure numpy, state integer constants, no cross-context imports.
- `atlas/trading/genome.py` — `Layer1Perception` and `RegimePlaybook` dataclasses contain all genome-controlled weights.

## Existing code being reused
- State constants from `atlas.trading.perception`: `RS_LEADER`, `RS_STRONG`, `RS_AVERAGE`, `RS_WEAK`, `RS_LAGGARD`, `MOM_*`, `VOL_*`, `REGIME_*`
- `Layer1Perception` dataclass fields: `conviction_rs_weight`, `conviction_mom_weight`, `conviction_state_weight`, `conviction_velocity_weight`, `synergy_weight`, `penalty_weight`
- `RegimePlaybook` fields: `min_conviction_to_enter`, `dd_halt_entry_pct`, `min_hold_days`, `exit_rs_drop_tiers`

## Conviction formula (spec §6.2)
```
base = (rs_weight * rs_pctile_norm)
     + (mom_weight * mom_norm)
     + (state_weight * rs_state_norm)
     + (velocity_weight * max(0, velocity_bonus))
synergy = rs_pctile_norm * mom_norm
penalty = vol_norm * rs_pctile_norm
conviction = clip(base * (1 + synergy_weight * synergy) * (1 - penalty_weight * penalty), 0, 1)
```
All weights come from `layer1.*_weight` genome fields — no hardcoded constants.

## Edge cases
- `days_in_state=0`: velocity_bonus calculation uses `1.0 - 0/30 = 1.0` — safe
- `direction=-1`: `max(0, velocity_bonus)` clips negative direction to zero
- `vol_state=VOL_HIGH` + `rs_pctile_norm=1.0`: penalty term can push conviction down significantly — clipped to 0
- `regime=REGIME_RISK_OFF`: `apply_entry_rules` returns all-False immediately
- `portfolio_heat >= max_portfolio_heat_pct`: block all entries (20% cap)
- `exit_rs_drop_tiers`: compares `int8` arrays — cast needed to avoid underflow

## Expected runtime
Sub-millisecond per genome per day. Designed for vectorbt batch (thousands of genomes). t3.large: no bottleneck.

## Files
- `atlas/trading/decision.py` (new)
- `tests/trading/test_decision.py` (new)
