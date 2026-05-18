# Chunk: State Engine T1.10 — Wire dwell_percentile + urgency_score + within_state_rank

## Data scale (from migration 073 table, live DB not checked — EC2 only)
- `atlas_stock_state_daily`: populated by T1.9 classify runs. Rows scale is
  ~500 stocks × N trading days per classifier_version run.
- `atlas_state_dwell_statistics`: new table (migration 073). Starts empty;
  this task populates it via `baselines-refresh`.
- `atlas_universe_stocks`: metadata table, ~500 rows. Full-load is fine.

## Chosen approach

### Why split into cli_states.py
`cli.py` is 476 LOC after T1.9. Adding the `_apply_dwell_and_urgency` helper
(~60 LOC) + `_states_baselines_refresh_cmd` (~50 LOC) would push it to ~590,
approaching the 600-LOC hook limit. The spec explicitly says to split into
`atlas/trading/cli_states.py` if needed. Splitting keeps both files well under
their limits and separates concerns cleanly.

### baselines-refresh subcommand
- Load all classified rows + universe metadata in one SQL join (SQL-side
  aggregation is cheaper than Python-side for this moderate-scale data).
- Apply `cohort_for_stock` in Python (only 500 rows of metadata — fine).
- Call `compute_cohort_dwell_baselines` from `atlas.intelligence.states.dwell`.
- Upsert into `atlas_state_dwell_statistics` with DELETE-for-today + INSERT
  (idempotent; table has PK on cohort_key, state, as_of_date).

### _apply_dwell_and_urgency helper
- Runs AFTER classify, reads baselines from DB (latest as_of_date).
- Iterates panel rows to assign per-stock urgency (panel is small: <= ~2500
  rows for a 5-day window). iterrows is acceptable here (per-row logic
  requires conditional branching that can't be vectorized without masking
  complexity, and panel size is well under 1K per day window).
- `dwell_percentile`: linear interpolation in (p25, p95) range, clamped [0,1].
- `within_state_rank`: mean of (freshness, rs_rank_12m) where freshness =
  1 - dwell_percentile.

### Edge cases handled
- `atlas_state_dwell_statistics` empty → fill with None/'n/a' (baselines not
  yet computed). classify still succeeds.
- Stock not in `atlas_universe_stocks` → cohort lookup fails → None/n/a fill.
- NULL `in_nifty_100` / `in_nifty_500` → `bool(None)` = False → treated as
  small_cap (conservative).
- `rs_rank_12m` NULL → defaults to 0.5 (neutral percentile).
- `dwell_percentile` None → freshness = 0.5 (neutral).
- `p25 == p95` (degenerate distribution) → `denom = max(p95-p25, 1)` guards
  zero-divide.

## Wiki patterns checked
- Idempotent Upsert: DELETE for today's as_of_date + INSERT (simpler than ON
  CONFLICT given composite PK with date).
- SQLAlchemy Dialect Prefix bug: strip `postgresql+psycopg2://` before
  `create_engine`.

## Existing code reused
- `atlas.intelligence.states.dwell.compute_cohort_dwell_baselines`
- `atlas.intelligence.states.dwell.derive_urgency`
- `atlas.intelligence.states.cohorts.cohort_for_stock`
- `atlas.intelligence.states.persistence.persist_state_panel`
- `_load_data` from cli.py (already loads metrics)
- `_states_classify_cmd` extended to call `_apply_dwell_and_urgency`

## Files
- New: `atlas/trading/cli_states.py` (~130 LOC)
- Modify: `atlas/trading/cli.py` (import from cli_states, replace placeholders)
- Modify: `tests/cli/test_states_classify.py` (2 new integration tests)

## Expected runtime
- baselines-refresh on 500 stocks × 30 trading days: ~2s (SQL join + Python
  group-by on ~15K rows).
- classify with urgency on 5-day window (~2500 rows): < 1s extra overhead.
