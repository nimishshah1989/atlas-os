---
chunk: sp09-task5
project: atlas-os
date: 2026-05-13
status: in-progress
---

# Approach: SP09 Task 5 — Sector CTS API + IC Engine v2

## Sub-task 5A: GET /api/v1/cts/sectors

### Data scale
- `atlas_cts_sector_pivot_daily` — sector-level aggregation; ~20-30 sectors x N days.
  Query uses WHERE date = MAX(date), so returns ~20-30 rows. Trivial load.

### Approach
- New router file `atlas/api/cts_sectors.py` following exact pattern from `atlas/api/cts_brief.py`
- Uses `open_compute_session` + `asyncio.to_thread` (same pattern as cts_brief.py)
- `_derive_momentum`: pivot_balance >= 0.10 -> Bullish, <= -0.10 -> Bearish, else Neutral
- NULLs: stage2_pct, avg_ppc_conviction, pivot_balance all handled explicitly with `is not None`
- Register in `atlas/api/__init__.py` after cts_brief_router import/include

### Wiki patterns checked
- Idempotent Upsert: not needed here (read-only endpoint)
- SQL Window Computation: single MAX(date) subquery - appropriate for this scale

### Existing code reused
- `open_compute_session` from `atlas.compute._session`
- `get_engine` from `atlas.db`
- Same router prefix convention as cts_brief.py

### Edge cases
- Empty table -> 404 (explicit check on `not rows`)
- NULL pivot_balance -> momentum = "Neutral"
- NULL stage2_pct, avg_ppc_conviction -> None in response (Optional fields)
- No data for latest date -> 404

### Expected runtime
- ~5ms for 20-30 row query on Supabase pooler

## Sub-task 5B: IC Engine v2

### What changes from v1
- Primary horizon: 5d (was 20d primary) — PPC is short-term signal
- Window: 365 days (was 90 days) — more statistical power
- Stage filter: adds Stage 2-only segments for quality-filter lift measurement
- New signal: `cts_conviction_score` vs fwd_ret_5d (full + stage2)
- SQL now fetches `stage` and `cts_conviction_score` columns
- SIGNAL_CONFIGS is list of 3-tuples: (signal_col, fwd_col, stage_filter: int|None)
- MIN_OBS raised from 20 to 30

### Edge cases
- Missing columns (cts_conviction_score may not exist in older data) -> `if signal_col not in df.columns` guard
- Stage filter produces empty sub -> `< MIN_OBS` guard skips
- ic_engine unchanged - same `compute_ic_over_window` API

### Expected runtime
- 365-day window, ~500-1500 stocks: ~50K-100K rows loaded from DB
- pandas pivot + Spearman: <10s per config on t3.large
- 7 configs x <10s = <70s total
