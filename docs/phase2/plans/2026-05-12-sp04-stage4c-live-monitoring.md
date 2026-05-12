# SP04 Stage 4c — Live Monitoring, Auto-Revert & Hit-Rate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Review gates:** `/plan-eng-review` and `/plan-design-review` completed inline in this file's preface. After execution, `/review` on diff and `/qa` on production.

**Goal:** Add the safety net on top of Stage 4a's auto-optimization loop. Track realized IC of every active weight set vs its predicted IC; auto-revert when realized drops below 50% of predicted for 60 days; show per-stock hit-rate on the deep-dive so FMs see whether high-conviction names actually played out.

**Architecture:** Three new audit tables (`atlas_signal_weights_live_perf`, `atlas_stock_hit_rate_daily`, `atlas_weight_revert_log`). One new sub-package `atlas.intelligence.conviction.monitoring` with three pure modules: `live_ic_tracker`, `hit_rate_engine`, `drift_detector`. Two CLIs chained into the nightly. Frontend additions on the existing breakdown panel + a new `/admin/weight-performance` page.

**Tech Stack:** Same as Stage 4a — Python 3.12, Pandas, SQLAlchemy 2.0, FastAPI, Next.js 15. Reuses SP01 `compute_ic_over_window`.

**Out-of-scope (Stage 4d or later):**
- Daily-brief drift alerts (one-line generator integration deferred)
- Slack webhook
- Per-tier hit-rate rollups on `/intelligence`
- ML-tuned smoothing lambda

---

## File Structure

**Database (new):**
- `migrations/versions/041_create_monitoring_tables.py` — 3 tables

**Backend (new sub-package `atlas.intelligence.conviction.monitoring`):**
- `monitoring/__init__.py`
- `monitoring/live_ic_tracker.py` — compute realized IC of an active composite over its most recent forward window
- `monitoring/hit_rate_engine.py` — per-stock hit-rate primitive
- `monitoring/drift_detector.py` — check whether any active weight set is in revert territory, optionally execute revert
- `scripts/track_live_ic.py` — nightly CLI
- `scripts/compute_hit_rates.py` — nightly CLI
- `scripts/check_weight_drift.py` — nightly CLI; emits revert proposals OR auto-reverts based on `--apply` flag

**Backend (modify):**
- `atlas/api/admin/proposals.py` — add `GET /api/admin/weight-performance` endpoint
- `atlas/intelligence/conviction/optimization/persistence.py` — add `auto_revert_proposal` helper used by drift detector

**Frontend (new):**
- `frontend/src/lib/queries/weight_performance.ts` — server-only queries against the new tables
- `frontend/src/components/admin/RealizedICSparkline.tsx` — 30-day realized vs predicted IC chart
- `frontend/src/components/admin/RevertBanner.tsx` — top-of-page alert when any auto-revert fired today
- `frontend/src/components/stocks/HitRateRow.tsx` — single-line hit-rate summary on deep-dive
- `frontend/src/app/admin/weight-performance/page.tsx`

**Frontend (modify — surgical):**
- `frontend/src/components/stocks/ConvictionBreakdownPanel.tsx` — slot `<HitRateRow />` in
- `frontend/src/app/admin/composite-proposals/page.tsx` — show `<RevertBanner />` + per-active-set realized IC sparkline

**Tests (new):**
- `tests/intelligence/conviction/monitoring/__init__.py`
- `tests/intelligence/conviction/monitoring/test_live_ic_tracker.py` — 3 tests
- `tests/intelligence/conviction/monitoring/test_hit_rate_engine.py` — 4 tests
- `tests/intelligence/conviction/monitoring/test_drift_detector.py` — 4 tests
- `tests/api/admin/test_weight_performance.py` — 2 endpoint tests

---

## Task 0: Pre-flight

- [ ] Verify Stage 4a tables present + populated (`atlas_signal_ic_rolling`, `atlas_weight_proposals`)
- [ ] Verify SP01 forward-return + IC primitives still importable

---

## Task 1: Migration 041 — three monitoring tables

```python
"""SP04 Stage 4c: live performance tracking, hit rate, revert audit.

- atlas_signal_weights_live_perf: per (weight_set_version, as_of_date)
  realized IC of the composite over the most recent 21-day forward window.
- atlas_stock_hit_rate_daily: per (instrument_id, date, lookback_window)
  hit-rate of past high-conviction days for this stock.
- atlas_weight_revert_log: audit row per auto-revert (weight_set_version
  reverted-from, weight_set_version restored, reason, days_below_threshold).

Revision: 041 / Revises: 040
"""
```

Tables — keys, indices, check constraints — laid out the same way as 039/040 (audit-first, no float for money-adjacent, partial unique indices where there's a "current" semantic).

`atlas_signal_weights_live_perf`:
- `(weight_set_version VARCHAR(96), as_of_date DATE)` composite PK
- `predicted_holdout_ic NUMERIC(8,6)` — what Stage 4a said this set would deliver
- `realized_ic NUMERIC(8,6)` — what compute_ic_over_window gave on the last 21-day window
- `n_observations INTEGER`, `ic_ratio NUMERIC(8,4)` — realized/predicted; null if predicted is 0
- `regime VARCHAR(16)` — captured at as_of_date for later 4b conditioning

`atlas_stock_hit_rate_daily`:
- `(instrument_id UUID, date DATE)` composite PK
- `lookback_window INTEGER NOT NULL DEFAULT 20`
- `n_high_conviction_days INTEGER` — days in window where conviction ≥ tier-median
- `n_positive_outcomes INTEGER` — those days where realized forward return > tier-median forward return
- `hit_rate NUMERIC(6,4) NULL` — null if n_high_conviction_days = 0

`atlas_weight_revert_log`:
- `id UUID PK`
- `reverted_from_version VARCHAR(96)`, `restored_to_version VARCHAR(96)`
- `tier VARCHAR(32)`, `regime VARCHAR(16)`
- `days_below_threshold INTEGER`, `realized_ic_avg NUMERIC(8,6)`, `predicted_holdout_ic NUMERIC(8,6)`
- `triggered_by VARCHAR(32) NOT NULL` — `'auto-detector'` or `'manual-admin'`
- `applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

---

## Task 2: `live_ic_tracker.py`

Pure function `measure_live_composite_ic(engine, *, weight_set_version, as_of)` returns a single `LiveICMeasurement` dataclass:
- Loads the weight rows for that version from `atlas_signal_weights`
- Loads tier members on `as_of` from `atlas_tier_membership_daily`
- Computes the composite score per (instrument, date) over the window
- Loads forward returns from price matrix (reuse SP01 `load_price_matrix` + `compute_forward_returns`)
- Calls `compute_ic_over_window`
- Returns (predicted_ic_from_seed_metadata, realized_ic, n_observations)

`measure_all_active_versions(engine, as_of)` — iterates over every currently-active `weight_set_version` and yields a `LiveICMeasurement`. Persistence writes them via `upsert_live_perf_batch`.

Tests: synthetic factor with known IC → measured matches; missing prices → returns None.

---

## Task 3: `hit_rate_engine.py`

Pure function `compute_hit_rate_for_stock(engine, *, instrument_id, as_of, lookback=20)`:
- Loads conviction scores for the stock for the past `lookback` trading days
- For each day where conviction ≥ that day's tier-median conviction, fetch the realized 21-day forward return
- Count days where forward return > tier-median forward return → that's `n_positive_outcomes`
- Return (`n_high_conviction_days`, `n_positive_outcomes`, `hit_rate = n_pos / n_high`)
- Return None if n_high < 5 (insufficient observations)

`compute_hit_rates_batch(engine, as_of)` — loops over every instrument with at least 1 conviction row in the lookback window.

Tests: stock with all high-conviction days positive → hit_rate=1.0; mixed → arithmetic correct; low n → None.

---

## Task 4: `drift_detector.py`

`detect_drift(engine, as_of, *, ratio_threshold=0.5, n_days_threshold=60)`:
- For each currently-active `weight_set_version`, load the last `n_days_threshold` rows from `atlas_signal_weights_live_perf`
- Count days where `ic_ratio < ratio_threshold`
- If count == `n_days_threshold` (every single day under), the set is in revert territory
- Return list of `DriftFinding(tier, current_version, days_below, avg_realized_ic, avg_predicted_ic)` candidates for revert

`execute_revert(engine, finding, *, triggered_by='auto-detector')`:
- Atomic transaction:
  - Find the most recent superseded/approved version for this (tier, regime) — that's the restore target
  - Bookend the current active set
  - Insert the restore-target weights as a new active set with `approved_by=auto-revert`
  - Write a `atlas_weight_revert_log` row
- Returns the revert-log id

Tests: 60 days all under threshold → 1 finding; 60 days with one above → 0 findings; revert correctly bookends and restores previous version.

---

## Task 5: CLIs

Three small scripts following the Stage 4a template:
- `scripts/track_live_ic.py [--as-of YYYY-MM-DD] [--persist]`
- `scripts/compute_hit_rates.py [--as-of YYYY-MM-DD] [--persist]`
- `scripts/check_weight_drift.py [--as-of YYYY-MM-DD] [--apply]` — `--apply` actually executes reverts; without it, prints findings only

---

## Task 6: API endpoint

`GET /api/admin/weight-performance` returns:
```json
{
  "active_sets": [
    {
      "tier": "tier_1_megacap",
      "version": "tier_1_megacap@2026-05-12T...",
      "predicted_ic": 0.0511,
      "last_30_days": [{"date": "...", "realized_ic": 0.04, "ratio": 0.78}, ...],
      "days_below_threshold": 12,
      "in_revert_territory": false
    }, ...
  ],
  "recent_reverts": [...]
}
```

Mounted on `internal_recompute` like the proposals route. Bearer-or-JWT auth via `_require_admin`.

---

## Task 7: Frontend — `weight_performance.ts` + RealizedICSparkline + RevertBanner

Recharts sparkline. Red threshold line at 0.5× predicted IC. Banner at top of `/admin/composite-proposals` if any reverts fired today.

---

## Task 8: Frontend — HitRateRow on deep-dive

Surgical addition to `ConvictionBreakdownPanel.tsx`. Renders a single line above the per-signal bars:
> "Last 20 high-conviction days: 14/20 outperformed tier median (70%)"

Greyed-out if `n_high_conviction_days < 5`.

---

## Task 9: Frontend — `/admin/weight-performance` page

Lists each active weight set with predicted IC, realized 30-day sparkline, days_below_threshold, an explicit "OK" / "Watch" / "Revert imminent" status pill.

---

## Task 10: Nightly orchestration wire-in

Update `run_atlas_nightly.sh` on EC2 to chain (in order, after the existing compute pipeline):
```bash
python scripts/recompute_signal_ic.py --persist        # Stage 4a
python scripts/generate_weight_candidates.py --persist # Stage 4a
python scripts/track_live_ic.py --persist              # Stage 4c
python scripts/compute_hit_rates.py --persist          # Stage 4c
python scripts/check_weight_drift.py                   # Stage 4c (dry-run; promotes to --apply once 60 days of data exist)
python -m atlas.agents.validator --scope sensibility --persist  # Validator A
python -m atlas.agents.validator --scope schema --persist       # Validator B
```

Document the `--apply` activation as a 60-day deferred enablement — we can't auto-revert until we have 60 days of live performance data anyway.

---

## Task 11: Memory file + master plan badge + validator HTML status

- Memory: `project_sp04_stage4c_state.md`
- Master plan: SP04 badge → "Stage 3 + 4a + 4c Shipped 2026-05-12"
- Validator HTML: add "Phases A & B operational; nightly schedule live" status row in §9.2

---

## Final verification checklist

- [ ] Migration 041 applied locally + EC2
- [ ] All monitoring unit + integration tests green
- [ ] First live-IC run produces ≥5 rows (one per active weight set)
- [ ] First hit-rate run produces rows for ~728 instruments (matches conviction count)
- [ ] First drift check produces zero reverts (we have <60 days of data)
- [ ] `/admin/weight-performance` renders 5 active weight sets
- [ ] `/stocks/PFOCUS` deep-dive shows HitRateRow
- [ ] Nightly script updated on EC2 with all 7 chained steps
- [ ] Memory file + master plan badge + validator HTML refreshed
