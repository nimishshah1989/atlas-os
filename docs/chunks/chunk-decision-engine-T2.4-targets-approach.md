# Chunk: Decision Engine Task 2.4 — Sector-Target Derivation

**Date:** 2026-05-20
**Status:** approach

## Data scale

This is a PURE function — zero DB access. Inputs are plain Python data structures
(sector signal dicts + Policy dataclass + regime cap). No table scan needed.
Runtime on t3.large: < 1ms per call (arithmetic on ~10-20 sectors).

## Chosen approach

Pure functional derivation in `atlas/intelligence/policy/targets.py`.

### Input dataclass: `SectorSignal`
- `sector: str` — sector name (matches atlas_universe_stocks.sector)
- `pct_stage_2: Decimal` — fraction [0,1] of sector's stocks in Stage 2 (from `aggregate_sector_states`)
- `mean_within_state_rank: Decimal` — mean within_state_rank for the sector, fraction [0,1]

Both fields come from `atlas.intelligence.aggregations.sector.aggregate_sector_states`:
- `pct_stage_2` = sum of stage_2a + stage_2b + stage_2c shares (line 98 in sector.py)
- `mean_within_state_rank` = column "mean_within_state_rank" (line 113 in sector.py)

### Output dataclass: `SectorTarget`
- `sector: str`
- `current: Decimal` — current portfolio weight (whole-number %)
- `target: Decimal` — derived target weight (whole-number %)
- `gap: Decimal` — target − current (negative = trim signal)

### Formula (C6)

Step 1: raw score per sector = pct_stage_2 × mean_within_state_rank

Step 2: total_raw = sum(all raw scores). If total_raw == 0 → degenerate case:
        all targets = 0, gaps = 0 - current. Return immediately.

Step 3: normalized_share[i] = raw[i] / total_raw  (sums to 1)

Step 4: pre_cap_target[i] = normalized_share[i] × regime_cap

Step 5: capped_target[i] = min(pre_cap_target[i], policy.max_per_sector_pct)

Step 6: gap[i] = capped_target[i] − current[i]

Invariants guaranteed:
- sum(capped_target) ≤ regime_cap  (capping only reduces, never increases)
- every capped_target[i] ≤ max_per_sector_pct
- gap can be negative (trim signal) — NOT clamped to 0

### Rounding policy
All intermediate arithmetic stays Decimal. Final target is rounded to 2 decimal
places (Decimal("0.01")) via ROUND_HALF_UP to avoid infinite decimals. Gap is
derived from the rounded target so sum(target) + rounding drift stays honest.

## Wiki patterns used
- [Decimal Not Float](patterns/decimal-not-float.md) — all financial values Decimal, never float
- [PRD Golden Example Testing](patterns/prd-golden-example-testing.md) — hand-compute golden examples as test fixtures

## Existing code reused
- `atlas.intelligence.policy.Policy` (frozen dataclass, `max_per_sector_pct`)
- `atlas.intelligence.aggregations.sector.aggregate_sector_states` — defines real field names
  (`pct_stage_2`, `mean_within_state_rank`)

## Edge cases handled
- All raw scores = 0: degenerate path, all targets = 0, no division
- Single sector: gets full regime_cap (capped by max_per_sector_pct)
- mean_within_state_rank = None (new sector, no data): treated as Decimal("0") → no allocation
- current > target: gap is negative, surfaced honestly
- pre_cap_target exactly equals max_per_sector_pct: treated as capped (min picks it correctly)

## LOC budget
- targets.py: budgeted ≤ 250 LOC (formula is simple; most lines are docstrings + type stubs)
- test_targets.py: budgeted ≤ 200 LOC
