# Chunk T2.3 — Policy Module: Effective Policy Resolution + Validation

## Data scale
No table scans needed for unit tests. The `atlas_portfolio_policy` table holds at most
O(portfolios) rows — never more than a few thousand. House default is one row.
DB is accessed only in `effective_policy()`, which is integration-gated.

## Approach

Pure functions for merge + validate — no DB. These are unit-tested with plain dicts.
`effective_policy()` wraps the DB read around the pure `_merge()` call; integration
tests are behind `ATLAS_INTEGRATION_TESTS`.

Storage convention (from seed_house_policy.py + migration 092):
- pct columns: whole-number percent (5 = 5%, 15 = 15%)
- rank columns: fraction in [0,1] (0.60 = 60th percentile)
- All numeric fields: `Decimal` (DB columns are `Numeric`; SQLAlchemy returns Decimal)
- `buy_states`: `list[str]` (DB is ARRAY(Text))
- `respect_regime_cap`: `bool`
- `trailing_stop_pct`: legitimately nullable in house default (None = no trailing stop)

## Dataclass style
Matches the codebase: `@dataclass(frozen=True)` with `from __future__ import annotations`.
Fields exactly match the 17 policy columns from migration 092 (no id/portfolio_id/is_house_default/timestamps).

## Merge logic
For each field: use override value if non-None, else house-default value.
Known limitation: `trailing_stop_pct` is nullable in BOTH house default and overrides.
A portfolio override of `None` cannot be distinguished from "inherit". Documented in code
comment. Practical impact is low — "no trailing stop" is the house default anyway.

## Validate rules (7 checks)
1. min_holdings > max_positions → violation
2. max_per_stock_pct > max_per_sector_pct → violation
3. cash_floor_pct not in [0, 100] → violation
4. min_within_state_rank not in [0, 1] → violation
5. min_rs_rank not in [0, 1] → violation
6. instrument_universe not in allowed set → violation
7. rebalance_cadence not in allowed set → violation
8. hard_stop_pct <= 0 → violation

## Wiki patterns checked
- `atlas.db.get_engine` — process-wide cached engine, use as-is
- `load_thresholds` pattern — engine optional parameter, same pattern for effective_policy

## Existing code reused
- `atlas.db.get_engine` for DB access
- `HOUSE_POLICY_DEFAULTS` from seed_house_policy.py defines the canonical defaults

## Edge cases
- Portfolio has no row in atlas_portfolio_policy → pure house default
- trailing_stop_pct = None in both → result is None (valid, means no trailing stop)
- buy_states override replaces the entire list (no list-merge)

## Expected runtime
Pure merge/validate: microseconds.
DB read: one indexed lookup per portfolio_id + one full-scan for house default row.
Expected <5ms per call on t3.large.

## Files
- `atlas/intelligence/policy/__init__.py`
- `atlas/intelligence/policy/policy.py` (target ≤300 LOC)
- `tests/intelligence/policy/__init__.py`
- `tests/intelligence/policy/test_policy.py` (target ≤800 LOC)
