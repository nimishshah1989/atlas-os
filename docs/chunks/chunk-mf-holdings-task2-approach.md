# Chunk: MF Holdings History — Task 2 (lens_decisions.py)
## Date: 2026-05-14

## Data scale
- `de_mf_holdings`: disclosure-level holdings, ~few thousand rows per disclosure date
- `atlas_stock_states_daily`: large historical table; scoped by instrument_id + date
- `atlas_fund_decision_scores`: new table (migration 065), currently empty
- `atlas_fund_holdings_changes`: new table (migration 065), currently empty
- Scale is well under 100K per fund per diff — pandas vectorized is fine

## Chosen approach
- Pure pandas vectorized diff (np.select, .map()) — no iterrows, no apply(lambda)
- Per-fund loop: load latest two snapshots only, not full history
- `_load_computed_set` called once before loop (idempotent skip pattern)
- `bulk_upsert` with ON CONFLICT for both changes and decision scores tables
- Weights are floats in source (not money) — float arithmetic acceptable per spec

## Wiki patterns checked
- Idempotent Upsert pattern: ON CONFLICT DO UPDATE on natural keys (uq_afds_mstar_period)
- Load All Then Compute anti-pattern: avoided — loading only the two most recent snapshots per fund
- Per-Day Query Loop bug-pattern: avoided — using _load_computed_set once

## Existing code reused
- `open_compute_session`, `bulk_upsert`, `df_to_pg_rows` from `atlas/compute/_session.py`
- `get_engine`, `load_thresholds` from `atlas/db.py`
- DISTINCT ON pattern for latest-state lookup from `lens_holdings.load_stock_states_at_date`

## Edge cases
- First disclosure (no prior snapshot): `from_df` is empty DataFrame — merge still works, all rows become "entry"
- NULL rs_state / momentum_state: `.map()` returns NaN for unmapped keys; np.select conditions handle via isin() which is NaN-safe
- Zero rows after diff (no material changes): compute_decision_score handles empty diff_df
- Fund with 0 or 1 disclosure date: skip fund (no diff possible with 0 dates)
- `(mstar_id, to_date)` already in computed_set: idempotent skip

## Tables written
- `atlas.atlas_fund_holdings_changes` — one row per changed holding
- `atlas.atlas_fund_decision_scores` — one row per fund per period (upsert on mstar_id, period_date)

## Expected runtime
- Typical fund has ~50-100 holdings, diff produces <50 changed rows
- Per-fund: ~3 SQL queries + in-memory vectorized ops = <1s per fund
- 500 funds total: ~5-10 minutes on t3.large
