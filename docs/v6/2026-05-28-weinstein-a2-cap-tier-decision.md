# Stream A2 — cap_tier point-in-time decision

**Date:** 2026-05-28
**Task:** Stream A2 Task 1 (gate check on `atlas_scorecard_daily.cap_tier` history depth)

## Check

```sql
SELECT MIN(date), MAX(date), COUNT(DISTINCT date) AS n_days
FROM atlas.atlas_scorecard_daily
WHERE cap_tier IS NOT NULL;
```

| min_date   | max_date   | n_days |
|------------|------------|--------|
| 2026-05-22 | 2026-05-27 | 3      |

## Verdict

**n_days = 3, well below the 1800-day (~8-year) threshold.** The PIT
`atlas_scorecard_daily.cap_tier` is freshly seeded and has no history
covering the 2018-2026 research window.

## Decision

Per Task 1 Step 2 of the Stream A2 plan, fall back to
`atlas.atlas_universe_stocks.tier` (static, current snapshot, post-2026-05
universe membership).

All event rows produced by Stream A2 are flagged
`cap_tier_source = 'STATIC_2026'` and carry the implicit caveat
`INVALID_FOR_PRE_2026` survivor bias: stocks delisted before today are not
in `atlas_universe_stocks`, and stocks that moved cap-tier (e.g. graduated
from Small → Mid in 2022) are tagged with their 2026 tier, not their
historical tier.

Re-run Stream A2 once the PIT backfill workstream lands. Stream B's
Megacap/Microcap separation depends on the same PIT source — coordinate.

## Limitation surfaced downstream

The output CSVs (`weinstein-a2-ic-results.csv`, `weinstein-a2-walk-forward.csv`)
and the final report (`weinstein-a2-report.md`) MUST document this
limitation under "Limitations" so any locked rule from this run is
treated as provisional pending PIT re-validation.
