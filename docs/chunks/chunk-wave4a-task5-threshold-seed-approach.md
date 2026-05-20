# Wave 4A Task 5 — Seed Hybrid-Classifier Band + Floor Thresholds

## Research findings

### Seed mechanism
`atlas.atlas_thresholds` is seeded via Alembic migrations, not scripts.
Pattern established in migrations 022, 043, 044, 065. Each migration:
- Has `SEEDS` tuple or inline VALUES with (key, value, category, description, min, max, default)
- Uses `INSERT ... ON CONFLICT (threshold_key) DO NOTHING` for idempotency
- `downgrade()` deletes by key

### Table schema (migration 007)
```
threshold_key       VARCHAR(64)  PK
threshold_value     NUMERIC(18,6)
category            VARCHAR(32)
description         TEXT
methodology_section VARCHAR(16)  nullable
units               VARCHAR(16)  nullable
min_allowed         NUMERIC(18,6)
max_allowed         NUMERIC(18,6)
default_value       NUMERIC(18,6)
is_active           BOOLEAN DEFAULT TRUE
```

### Exact 8 keys and their inline fallback defaults (from code)

**sector.py** (`_sector_rank_config`):
- `sector_band_p20` → `_DEFAULT_BAND_P20 = Decimal("0.20")`
- `sector_band_p50` → `_DEFAULT_BAND_P50 = Decimal("0.50")`
- `sector_band_p80` → `_DEFAULT_BAND_P80 = Decimal("0.80")`
- `sector_overweight_floor` → `_DEFAULT_OVERWEIGHT_FLOOR = Decimal("0.10")`
  (stored as proportion 0–1, not whole-number percent; docstring says "10%")

**fund.py** (`_fund_rank_config`):
- `fund_band_p20` → `_DEFAULT_FUND_BAND_P20 = Decimal("0.20")`
- `fund_band_p50` → `_DEFAULT_FUND_BAND_P50 = Decimal("0.50")`
- `fund_band_p80` → `_DEFAULT_FUND_BAND_P80 = Decimal("0.80")`
- `fund_recommended_floor` → `_DEFAULT_FUND_RECOMMENDED_FLOOR = Decimal("0.20")`

### Reconciliation vs spec
The spec said `sector_overweight_floor = 10` (whole-number percent). Code uses
`0.10` (proportion). Code wins — the `_sector_rank_config` comment says
"pct_stage_2 ≥ 10% to hold Overweight" but the actual comparison is against
`pct_stage_2` which is a 0–1 proportion in the DataFrame. So `0.10` is correct.

### Current migration head
`094_sector_state_from_computed` — next migration is 095.

## Approach
- New migration `095_seed_hybrid_classifier_thresholds.py`
- `down_revision = "094_sector_state_from_computed"`
- Insert 8 rows, ON CONFLICT DO NOTHING (idempotent)
- Category: `"sector_rank"` for sector keys, `"fund_rank"` for fund keys
- After migration: update TODO comments in sector.py/fund.py to note seeded location

## Test
- `tests/migrations/test_095_hybrid_thresholds.py` — structural unit test
  that imports the migration module's SEEDS constant and verifies all 8 keys
  are present, values are correct, no DB required.
- Follows precedent from tests/migrations/test_076_seed.py (integration tests
  also added, skipped unless ATLAS_INTEGRATION_TESTS=1).

## EC2 step (deferred)
`alembic upgrade 095_seed_hybrid_classifier_thresholds` after pushing to EC2.
