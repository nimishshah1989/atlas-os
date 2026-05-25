# Chunk C.4 — Audit Trail Query Approach

## Data scale
- atlas_scorecard_daily: ~750 rows × ~30 features (small per iid/date)
- atlas_signal_calls: ~100-500 rows (event table, sparse)
- atlas_conviction_daily: ~750 rows/day × 4 tenures = ~3K/day
- atlas_provenance_log: 0 rows at v6 launch (writer not deployed)
- Scale: all under 1K for a single iid lookup — SQL lookup, no Python needed

## Chosen approach: Promise.all over 5 parallel queries (NOT a single mega-CTE)

Reason: Each section targets a different table/index. A single CTE with 6
sub-CTEs would force serial evaluation inside Postgres. With Promise.all we
get 5 concurrent round-trips each hitting its own index. Given the small per-
iid data volume, 5 × ~5ms < 250ms p95 easily.

## Wiki patterns checked
- cells.ts — sql template tag pattern with typed rows + mappers
- recent_signal_calls.ts — atlas_universe_stocks join for universe membership
- regime.ts — Promise.all for parallel queries
- instrument.ts — atlas_universe_stocks columns (symbol, company_name, sector, tier)

## Existing code reused
- `atlas_universe_stocks` JOIN for universe membership + sector + cap_tier
- `atlas_signal_calls` for signal call provenance + entry_date + predicted_excess
- `atlas_cell_definitions.rule_dsl` JSONB for predicates
- `atlas_scorecard_daily.features` JSONB for actual feature values
- `atlas_regime_daily` for regime state + days_in_regime (window fn)
- `atlas_provenance_log` for Section 7 (empty at launch — returns [])
- `atlas_conviction_daily` for cell_matches (cell_definition_id + verdict)

## translatePredicate source
No `translatePredicate` function exists in lib/eli5/. Design-application.md §7.1
shows plain text ELI5 lines per predicate (e.g. "Daily turnover is well above
the mega-liquid floor."). Source: `atlas_conviction_daily.eli5` text column
OR `atlas_cell_rule_candidates.eli5`. For v6.0 we derive predicates from
`atlas_conviction_daily.fired_predicates` JSONB + a local `translateFeatureName`
lookup map (canonical 12-feature vocabulary from CONTEXT.md). No external lib.

## Edge cases handled
- iid not in universe: returns in_universe=false; query still completes
- atlas_provenance_log empty: returns []
- atlas_signal_calls no active call: signal_call=null
- atlas_regime_daily empty: regime=null
- features JSONB key missing: actual_value='—', satisfied=false
- fired_predicates null: predicates_met=[]

## Expected runtime on t3.large
- 5 parallel queries × ~5ms each = ~25ms total well under 250ms p95
- No Seq Scan: all queries use indexed lookups (instrument_id+date index,
  computed_at DESC index on provenance_log)

## Files
1. `frontend/src/lib/queries/v6/audit_trail.ts`
2. `frontend/src/lib/queries/v6/__tests__/audit_trail.test.ts`
