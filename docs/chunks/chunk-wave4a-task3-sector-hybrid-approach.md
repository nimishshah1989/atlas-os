---
chunk: wave4a-task3
project: atlas-os-consolidation
date: 2026-05-20
status: success
---

## Task: Wave 4A Task 3 — Hybrid Sector Classifier + Migration 094

### Problem

The old `atlas_sector_signal_unified` view derived `sector_state` via a CASE:
`pct_stage_2 >= 0.50 → Overweight`, else `Neutral`. In a thin-breadth market
(all sectors below 50% breadth), every sector classified as Neutral — useless
for portfolio construction.

### Approach

**Cross-sectional hybrid rank + absolute breadth floor.**

Score per sector = `pct_stage_2 × mean_within_state_rank × mean_rs_rank_12m`
(all from the existing `atlas_sector_state_v2` row after aggregation).
NULL components treated as 0 (penalises missing data honestly, no fabrication).

Labels: `["Avoid", "Underweight", "Neutral", "Overweight"]` ordered worst→best.
Band percentile cuts: p20/p50/p80 (defaults 0.20/0.50/0.80 from inline constants;
TODO Task 5: move to atlas_thresholds for runtime tuning).
Floor: `pct_stage_2 >= 0.10` required to hold Overweight.

Guarantees: always produces a spread across 4 labels with ≥25 sectors.
The `hybrid_rank_labels()` function (Task 2, `atlas.intelligence.ranking`) is
the pure implementation; this task wires it into the sector aggregation.

### Real column names found

- `pct_stage_2` — combined stage_2a+2b+2c breadth (float, 0–1)
- `mean_within_state_rank` — mean stock-level rank within their state (float, nullable)
- `mean_rs_rank_12m` — NEW column computed per-sector from the stock panel's `rs_rank_12m`
- `sector_state` — NEW column added to `atlas_sector_state_v2` by migration 094

### Migration 094

- `down_revision = "093_portfolio_targets_holdings"`
- `upgrade()`: adds `sector_state VARCHAR(12) NULLABLE` to `atlas_sector_state_v2`;
  recreates `atlas_sector_signal_unified` reading `COALESCE(s.sector_state, 'Neutral')`
- `downgrade()`: removes column, restores migration 084 CASE expression

### What was tricky

- pyright didn't accept `pd.isna()` on `object` values — widened return type
  `bool | NDArray | NDFrame` is not usable in a boolean context. Used a helper
  `_to_decimal(value)` with `isinstance(value, float) and math.isnan(value)`.
- pyright doesn't accept `pd.DataFrame(columns=[...])` with a list — switched
  to `pd.DataFrame({c: pd.Series([], dtype=object) for c in cols})`.
- pyright types groupby key as `Hashable` (can't unpack) — used `cast(tuple, key)`.
- Original file had all 3 pyright issues pre-existing; fixed all as part of the
  0-errors requirement.

### Anti-patterns avoided

- No float for financial scores — Decimal throughout
- No hardcoded thresholds — inline defaults with TODO marker for Task 5
- iterrows avoided in the agg loop (uses `to_dict("records")` + plain for-loop
  over dict list, which is the correct approach for small O(N_sectors) data)

### Files modified

- `atlas/intelligence/aggregations/sector.py` — hybrid sector_state computation
- `atlas/intelligence/aggregations/persistence.py` — sector_state in UPSERT
- `migrations/versions/094_sector_state_from_computed.py` — column + view
- `tests/intelligence/aggregations/test_sector.py` — 3 new spread/floor tests

### EC2 deploy note

`alembic upgrade 094_sector_state_from_computed` is deferred to EC2.
Mac has no DB. The migration is written and tested for correctness.
