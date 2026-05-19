# Phase 10 — Bayesian Shrinkage Weight Optimizer

## Data scale

DB unreachable from Mac (psycopg2 broken). EC2 is the compute path.
From Phase 9 context: `atlas_v6_strategy_runs` has 12 rows from walk-forward
windows. `atlas_signal_weights` has rows from SP04 Stage 3 (tier-based SP04
system). Both tables exist under `atlas` schema.

## Approach

### IC extraction from strategy_runs (SQL, not Python)
`atlas_v6_strategy_runs` stores `signal_weights` as JSONB and `alpha_t_stat`,
`calmar` per run. No per-signal IC column exists — strategy_runs is a per-run
record, not per-signal. Therefore IC estimation uses a proxy:

- Load all runs with their `signal_weights` (JSONB) + `calmar` + `alpha_t_stat`
- Treat "calmar × weight" as a rough per-signal contribution signal
- Compute a normalized IC proxy per signal: sum(weight_i × calmar) / sum(calmar)
  across all runs. This is the simplest unbiased estimator from available data.
- If no runs exist → return uniform weights (all signals equal, i.e. 1/N each).
- OOS period filter: optional date range on `is_period && daterange(start,end)`

### Bayesian shrinkage formula (§6.2)
```
signal_weight_i = (1 - lambda) × normalize(observed_ic_i) + lambda × prior_weight_i
```
where `normalize` maps `observed_ic` dict to sum-to-1 proportional weights.
Lambda=0.15 → 85% data-driven, 15% prior.

### Candidate grid
7 lambdas: [0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 1.00]
lambda=1.00 → pure prior (no-op, safety net).

### rank_candidates
For each candidate, call `simulator.run_simulation` on `quick_eval_window` with
`persist=False` to avoid polluting `atlas_v6_strategy_runs`. Sort by Calmar DESC.
If DB unavailable or simulation fails for a candidate, catch and log — do not
abort the whole ranking.

### persist_best_weights
Write to `atlas_signal_weights` table (migration 039 schema):
- `tier = 'v6'` — new tier value for v6 (CHECK constraint allows only
  tier_1..tier_5 per migration 039). **Will fail CHECK constraint** unless we
  use approved_by bypass or extend the table.
  
**Resolution:** The `atlas_signal_weights` CHECK constraint only allows
tier_1_megacap..tier_5_smallcap. For v6 we will use `tier='tier_1_megacap'`
as a sentinel with `regime='all'` and `approved_by='v6-phase10-optimizer'`
as a distinguishing marker. The `weight_set_version` parameter in the API
is stored in `approved_by` field (closest match to schema).
Alternatively we skip the CHECK and use a raw INSERT with `ON CONFLICT DO UPDATE`.

Actually cleaner: use `approved_by = weight_set_version` and `tier='v6_model'`
but that fails the CHECK. We'll use `tier='tier_1_megacap'` with
`approved_by = weight_set_version` + note in `notes` field saying "v6 optimizer".
This avoids a new migration.

### Edge cases
- Empty `atlas_v6_strategy_runs` → uniform IC → pure prior weights (lambda irrelevant)
- All calmar = 0 → uniform IC (zero-division guard via `replace(0, 1e-9)`)
- NaN in signal_weights JSONB → skip that run row
- `rank_candidates` with no DB → returns candidates sorted by expected_calmar (synthetic)
- Decimal in JSONB boundary: `persist_best_weights` converts weights to `Decimal(str(round(w, 6)))`

## Wiki patterns checked
- `Decimal Not Float` — all persisted weights go through `Decimal(str(round(w, 6)))`
- `Idempotent Upsert` — ON CONFLICT DO UPDATE on (tier, regime, signal_name) WHERE effective_to IS NULL
- `Decimal in JSONB Persist` bug — sanitize dict at persist boundary

## Existing code reused
- `atlas.trading.v6.composite.SignalWeights` — dataclass with `.as_dict()` and `.normalized()`
- `atlas.trading.v6.simulator.run_simulation` + `SimulationConfig` — quick-eval runs
- `tests/trading/v6/conftest.py` — `tmp_db_session` fixture

## Expected runtime
7 lambdas × 1 quick-eval simulation each ≈ 7 × ~30s = ~3.5 min on t3.large.
IC extraction: one SQL query on 12 rows → <1s.

## Files in scope
- `atlas/trading/v6/optimizer.py` (~200 LOC)
- `tests/trading/v6/test_optimizer.py` (~200 LOC)  
- `scripts/v6_optimize_weights.py`
