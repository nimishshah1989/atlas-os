# v6 Stocks page — backend MVs design

**Date:** 2026-05-26
**Scope:** 3 materialized views that drive the v6 Stocks surface (page 05 + 05a deep-dive)
**Branches:** one PR per MV, stacked off `main` in order list → landscape → deepdive
**Status:** spec draft, awaiting PR1 start

---

## Goal

Power the v6 Stocks page (mockups `05-stocks.html` + `05a-stock-reliance.html`) with three
materialised views over the existing v6 schema. No new base tables; no new persisted columns;
all derived values are computed in MV bodies and refreshed nightly via `pg_cron`.

## Source tables (verified against live migrations 080 → 096)

| Table | Used for |
|---|---|
| `atlas.atlas_scorecard_daily` (mig 080) | per-(iid, date) 5-family states + methodology features (rs_residual_6m, realized_vol_60d, listing_age_days, log_price, features JSONB) |
| `atlas.atlas_signal_calls` (mig 080) | open/closed signal calls — drives action, cross-cell depth, tenure tape, predicted_excess, confidence_regime_conditional |
| `atlas.atlas_cell_definitions` (mig 080) | per-cell IC, friction_adjusted_excess, walk_forward_TP, rule_dsl |
| `atlas.atlas_cell_walkforward_runs` (mig 080) | per-(cell, oos window) IC + TP for the matrix |
| `atlas.atlas_stock_conviction_daily` (mig 039) | conviction_score [0,1], confidence_label, backing_ic, tier — lifted as composite/confidence source |
| `atlas.atlas_universe_stocks` | symbol, company_name, sector, tier (M1 universe) |
| `atlas.atlas_stock_metrics_daily` | ret_1m, ret_3m, ret_12m, rs_3m_nifty500, vol_60d, % > EMA20, % > EMA200 |
| `atlas.atlas_instruments` | mcap (lakh cr), face-value, listing date |

## Composite-score mapping (locked decision)

The v6 redesign mockups specify composite ∈ [-10, +10]. The live system writes
`atlas_stock_conviction_daily.conviction_score` ∈ [0, 1] (mid 039, written by
`atlas.intelligence.conviction.persistence`).

**Lift mapping (no new column):**
```
composite_score = ROUND((conviction_score - 0.5) * 20, 2)  -- [-10, +10]
```

`conviction_score = 0.5` (no edge) → composite = 0.0
`conviction_score = 1.0` (max BUY conviction) → composite = +10.0
`conviction_score = 0.0` (max AVOID conviction) → composite = −10.0

Confidence band lift:

| `confidence_label` | UI band |
|---|---|
| `industry_grade` | **HIGH** |
| `baseline` | **MED** |
| `descriptive_only` | **LOW** |

Both translations live in the MV SELECT only — no schema change.

## Action label rule

Per CONTEXT.md §"Cell display name", list pages use the intrinsic cell direction
(BUY/WATCH/AVOID), not the ownership-aware ACCUMULATE/HOLD/SELL. That rendering is the
API layer's responsibility for per-user surfaces. The MVs emit only:

- `action = 'BUY'` when there is ≥1 open signal_call for the iid with `action='POSITIVE'`
- `action = 'AVOID'` when there is ≥1 open signal_call with `action='NEGATIVE'` AND zero open POSITIVE
- `action = 'WATCH'` otherwise (composite in [−4, +4] band per mockup; or NEUTRAL-only fires)

## Conviction tape (4 segments per iid)

For each `tenure ∈ {'1m','3m','6m','12m'}`:

```
tape_seg = MAX(action over open signal_calls for this (iid, tenure))
         where the order is POSITIVE > NEUTRAL > NEGATIVE > 'dormant'
```

If no open call at that tenure → `dormant`. Stored on `mv_stock_list_v6` as four
columns: `tape_1m`, `tape_3m`, `tape_6m`, `tape_12m`.

## Cross-cell depth

Per CONTEXT.md §"Cross-cell depth":
```
cross_cell_depth = COUNT(DISTINCT (cap_tier_at_trigger, tenure, action))
                   FILTER (WHERE exit_date IS NULL)
```

Range 0..5 (matrix max is 24 but a single iid never spans all 24 — same cap×tenure
combinations are mutually exclusive). The mockup uses /5 to indicate the maximum
that any individual stock could realistically light up.

---

## MV1 — `mv_stock_list_v6` (~80 LOC SQL)

**Purpose:** drives the all-instruments table at the bottom of 05-stocks.html
(750 rows × 15+ columns) and the hero-stats strip totals.

**Grain:** one row per (iid, latest_date).

**Columns:**
- `instrument_id UUID PK`, `date DATE`, `symbol TEXT`, `company_name TEXT`, `sector TEXT`, `cap_tier TEXT`
- `action TEXT` (BUY / WATCH / AVOID) — per rule above
- `composite_score NUMERIC(4,2)` — from atlas_stock_conviction_daily (mapped)
- `confidence_band TEXT` — H/M/L
- `cross_cell_depth SMALLINT`
- `tape_1m TEXT`, `tape_3m TEXT`, `tape_6m TEXT`, `tape_12m TEXT`
- `ret_1m NUMERIC`, `ret_3m NUMERIC`, `ret_12m NUMERIC`, `rs_3m_nifty500 NUMERIC`
- `vol_60d NUMERIC`, `pct_above_ema20 BOOLEAN`, `pct_above_ema200 BOOLEAN`
- `predicted_excess NUMERIC` (from the best open cell for this iid)
- `cell_ic NUMERIC` (IC of the open cell that drove `action`)
- `last_fire_date DATE`, `is_fresh_today BOOLEAN`, `mcap_lakh_cr NUMERIC`

**Unique index:** `(instrument_id)` — supports concurrent refresh.

**Refresh:** `REFRESH MATERIALIZED VIEW CONCURRENTLY` after EOD scorecard write
(piggybacks on the existing nightly cron that already writes
`atlas_stock_conviction_daily`).

---

## MV2 — `mv_stock_landscape` (~60 LOC SQL)

**Purpose:** drives the conviction-landscape section of 05-stocks.html — bubble
chart data + 24-cell matrix tallies.

**Two output blocks unified by a TYPE column** (so both fit in one MV with
predictable shape):

### Block A — bubble points (one row per iid)
```
type='bubble', instrument_id, symbol, sector, cap_tier,
rs_3m_nifty500, composite_score, mcap_lakh_cr, action, confidence_band
```

### Block B — matrix tallies (24 rows)
```
type='matrix', cap_tier, tenure, action_direction (POS/NEG),
firing_count, walk_forward_ic, walk_forward_tp
```

Walk-forward IC + TP are pulled from `atlas_cell_walkforward_runs` keyed by
(cap_tier, tenure, direction) — most recent OOS window per cell, joined on the
cell_definition that maps to that bucket.

**Unique index:** `(type, instrument_id, cap_tier, tenure, action_direction)` —
covers both blocks for concurrent refresh.

---

## MV3 — `mv_stock_deepdive` (~180 LOC SQL)

**Purpose:** drives the per-stock detail page (05a-stock-reliance.html). One row
per iid; multiple JSONB sub-objects keyed by section.

**Grain:** one row per `instrument_id`.

**Columns:**
- `instrument_id UUID PK`, `symbol`, `company_name`, `sector`, `cap_tier`, `mcap_lakh_cr`
- Hero verdict strip (composite, RS_3M, confidence_band, active_cell_count, predicted_excess, sector_rank)
- `composite_30d_trajectory NUMERIC[30]` — computed via window function over the trailing 30 EOD rows of `atlas_stock_conviction_daily`, mapped to [-10,+10]; NULL-padded for newer listings
- `active_cells JSONB` — array of `{cell_id, cell_label, tenure, ic, tp, days_open, predicted_excess}` from open signal_calls
- `dormant_cells JSONB` — array of cells the iid is eligible for but not firing (with the failing predicate(s) and current value)
- `cell_fire_timeline JSONB` — last 365d signal_call rows: `{cell_label, fire_date, exit_date, exit_reason, realized_excess, won}`
- `cross_cell_viz JSONB` — array of 5 pip definitions with state (FIRING_POS / FIRING_NEG / DORMANT)
- `rs_grid JSONB` — 9 baselines × 6 windows; sources `atlas_stock_metrics_daily` + the index price series
- `peer_set JSONB` — top 10 same-sector + same-tier peers ranked by composite (includes current iid flag)
- `fundamentals JSONB` — pe / pb / opm / roce / d_e / sales_growth / pat_growth (latest published)
- `open_calls JSONB`, `closed_history_30d JSONB` — from atlas_signal_calls + atlas_ledger
- `macro_overlays JSONB` — 3 series determined by `atlas_stock_macro_overlay_map` (sector,business_mix_tag)
- `news_events_30d JSONB` — last 30d from `de_news_events` filtered to this iid

**Unique index:** `(instrument_id)`.

**Refresh:** CONCURRENTLY, post nightly scorecard.

---

## Per-PR TDD checklist

Each PR follows the same loop:

1. `git checkout main && git pull && git checkout -b feat/v6-mv-<name>`
2. Invoke `superpowers:test-driven-development`
3. Red: write failing tests at `tests/v6/test_mv_<name>.py`:
   - schema test: column names + types match spec
   - row-count test: count(*) on a known-date fixture matches expectation
   - sample-row test: 3-5 pinned iids return the expected values
   - performance test: query latency < 200ms on 50k-row fixture
4. Green: write `migrations/versions/097..099_v6_mv_<name>.py` (`CREATE MATERIALIZED VIEW … WITH NO DATA` + unique index + concurrent refresh hook)
5. Hook into `atlas/v6/refresh.py` (extend `refresh_all()` to include the new MV)
6. Refactor: simplify SQL; extract repeated CTEs
7. `/codex review` — adversarial pass on the SQL
8. `coderabbit:code-review` — line-by-line on the migration + tests
9. `/review` — pre-landing diff review
10. `/ship` → squash to `main` per `feedback_can_merge_to_main`
11. `/land-and-deploy` → verify with canary against `atlas.jslwealth.in`

## Refresh cadence

All 3 MVs added to `atlas/v6/refresh.py:refresh_all()` in dependency order
(list → landscape → deepdive). pg_cron schedule: 21:00 IST (after the
20:00 IST scorecard / conviction write).

## Performance budget

| MV | First refresh | Concurrent refresh |
|---|---|---|
| `mv_stock_list_v6` | < 15 s | < 5 s |
| `mv_stock_landscape` | < 10 s | < 3 s |
| `mv_stock_deepdive` | < 60 s | < 25 s |

Baseline measured against the 747-row Supabase atlas-os scorecard set.

## Open items (deferred from spec, captured for tracking)

- T-MV1: `confidence_band_cutoffs` is currently `industry_grade/baseline/descriptive_only`. If methodology locks H/M/L numeric cutoffs (per CONTEXT.md §"HIGH-confidence stack"), the MV mapping flips to those cutoffs at that PR.
- T-MV3: `atlas_stock_macro_overlay_map` is not yet seeded. MV3 will emit `macro_overlays: []` until that table is populated; seeding tracked separately.
- T-MV3: `de_news_events` ingestion for v6 is per-(iid, date) — confirm enrichment with ticker FK before MV3 lands; if not, emit empty array gracefully.
