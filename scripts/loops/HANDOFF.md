# Atlas v4 six-lens — HANDOFF / STATE (for the next session)

## ⭐ RESUME HERE (Loop C is 95% done — finish it ON-READ, ~20 min)
**DONE + safe in the DB:** lens sub-scores rebuilt PIT (1854 dates × 2093), both blockers
fixed, RS defect fixed, IC calibrated, learned weights LIVE in `atlas_thresholds`
(technical 0.32 / catalyst 0.26 / flow 0.22 / fundamental 0.20; policy=0 FYI-only) +
`atlas_signal_weights` (20 active rows) + `atlas_signal_ic` (21 rows). All code committed.

**The one decision that ends the saga: composite is ON-READ, NOT materialized.** Proven:
computing every stock's composite for a date = **0.075s** in pandas (`compute_composite` over
the stored sub-scores × DB weights). Materializing 3.9M rows to Supabase kept hanging/bloating
(wasted hours) — abandoned. The stored `composite/conviction_tier/coverage_factor/lenses_active`
columns are now **vestigial/stale** (2019-2022 = new weights, 2023-2026 = old) — IGNORE them.

**To finish (repoint gate + tests to on-read, then commit green):**
1. `validate_loopC.py` **C6**: drop the "reconcile to STORED composite" clause; keep the on-read
   path (compute_composite over sub-scores + perturbation discriminator — already there).
2. **C1**: drop `composite` from the variance list (keep the 4 conviction lenses + valuation).
3. **C8**: compute `coverage_factor` on-read for the early/late samples (don't read the stored col).
4. `test_scorers.py` **TestProductionReconciliation**: drop `composite` from `LENSES` (reconcile the
   six lens SUB-scores only — they're stored + correct; composite is on-read).
   **TestComposite.test_consumes_db_weights**: on-read perturbation only (no stored comparison).
   **test_tier_valid_and_coverage_tracks_lenses**: compute tier/coverage on-read or relax.
5. Run `validate_loopC --mode full` + `--check A` + `pytest atlas/lenses` → green → commit.
6. Then: ship a DB VIEW (or API helper) that serves composite on-read for the product (the
   `create_composite_view.py` SQL is verified 500/500 vs the scorer — but make it pushdown-friendly
   / app-level; the multi-CTE view did NOT push the date filter down → don't use as-is).

**Then next: delivery-% enrichment via a tmux goal-loop** (durable long jobs in tmux, on-read
composite, gate-driven, resumable) — see DECISIONS D-next + the delivery-% spec to write.
---


**Branch:** `feat/v4-six-lens` (all work here; nothing on main; lens UI behind `NEXT_PUBLIC_LENS_V4`, OFF).
**Read first:** `GUARDRAILS.md`, `DECISIONS.md` (D1–D16), then this. The active spec is
`loopC_atom_complete.md`. State scorecard: `docs/atlas-six-lens-coverage-map.md`. IC spec:
`docs/atlas-ic-and-step-goals.md`.
**Gate:** `python scripts/foundation/validate_lenses.py --check A` (immutable). Loop C adds a new
independent `validate_loopC.py` (build it — see the spec's C1–C8).

## Where we are (2026-06-21, end of Loop C)
- **Loop A — DONE.** **Data layer — DONE.**
- **Loop C (Phase 1c–1e) — essentially DONE** (final gate run is the last step). What landed:
  - Both blockers fixed: composite consumes DB weights (C6); forward returns are TRUE forward over
    h NSE sessions, NIFTY-50-calendar-reindexed (C7 core). Walk-forward folds with purge+embargo.
  - Every lens wired point-in-time: technical (as-of adjusted close + technical_daily ATR/BB/
    vol_ratio/pos_52w/rs_*_sector); fundamental (`fundamental_pit.py` as-of TTM/YoY/ROE/D-E from
    financials_quarterly+annual); valuation (as-of PE = close÷TTM-EPS + as-of sector-median PE; 52w
    from pos_52w). Fixed the silent RS-zero defect (tech_rs 15→1963/2090). P/B=None (no unit-safe
    source — D17). 31 pytest green.
  - Journal **rebuilt PIT 2019-01-01→2026-06-19 = 1854/1854 NSE sessions × 2093 stocks** via
    chunked, resumable `backfill_lenses.py` (proven byte-identical to `run_pipeline` per
    `--validate-date`).
  - **IC calibration done (D18):** policy removed from scoring (FYI-only — static/selection-biased);
    learned weights over 4 conviction lenses (technical 0.321 / catalyst 0.259 / flow 0.216 /
    fundamental 0.204), persisted to `atlas_thresholds` (DB-variable, frontend-editable) +
    `atlas_signal_weights` (20 rows) + `atlas_signal_ic`. Atom is a **3–6m signal** (composite OOS
    IC 6m=0.034 clears floor + beats equal-weight; 1m weak by design).
  - Composite recompute with learned weights via set-based in-DB SQL (`recompute_sql.py`).
- **GO-FORWARD (next session):**
  1. **Composite → on-read** (DB view computing composite from stored lens sub-scores × live DB
     weights). Materializing 3.9M composites on every re-weight is the wrong design (a full
     re-weight is a ~40-min indexed-row rewrite); on-read makes weight edits instant. The view SQL
     is the verified `recompute_sql.build_sql`. Nightly pipeline already writes composite per-date
     (fast) — only full-history re-weights were the pain.
  2. **Legacy Supabase table cleanup** — after Atlas is live + verified on the rebuilt foundation,
     audit references then drop superseded legacy tables (tv_metrics / de_* etc.). FM-approved,
     destructive — gated.
  3. rs_*_sector population (sector RS currently inert — blends to n500-only).
- **Roll-ups (sector → ETF/index → MF) + front-end — GATED** (D12/D15). Build only after the atom is A.
  MF (D18 brainstorm): Regular/Equity/Growth universe, distributor-recommend-not-advise, ranked
  within SEBI category vs Category Benchmark, full sub-component transparency on the fund page,
  edge = holdings look-through + active-movement, IC-calibrated per category.

## Data layer — real coverage (instrument %) + TIME coverage + depth
| Lens | instrument coverage | time range | median depth/stock |
|---|---|---|---|
| Technical | trend/RS 91%, ATR/BB/vol/52w 100% | 2000→2026 (25y) | ~2,437 days |
| Fundamental | income 97%, balance sheet 86% | income 2005→2026-03; BS 2002→2026 | ~39 quarters / ~12y BS |
| Valuation | PE/EV 100% | ⚠️ **SNAPSHOT — today only, 0 history** | — (built in Loop C) |
| Catalyst | 96% | 2002→2026 | deep |
| Flow | shareholding 96%, insider 78% | 2001→2026 / 2008→2026 | deep |
| Policy | sector-mapped 96% | static | — |

**Two honest holes still at the data layer (fold into Loop C):** sector-RS (`rs_*_sector` = 0%) and
P/B (0% — `tv_metrics.market_cap` is unit-unreliable; do it unit-safe in Loop C). Valuation has NO
time history yet — it is reconstructed in Loop C from 25y price + as-of EPS/equity.

## Key files
- Lens engine: `atlas/lenses/{pipeline.py, data/adapters.py, compute/*.py, calibration.py}`
- Feeds: `scripts/foundation/ingest_{screener,xbrl,insider,filings,shareholding}.py`, `compute_all.py`, `technicals.py`
- Journal rebuild: `scripts/foundation/backfill_lenses.py`. Gates: `validate_lenses.py` (immutable), `validate_loopC.py` (to build).

## The 2 blockers Loop C must fix FIRST (cheap, provable on the current journal)
1. `compute_composite` reads NESTED `lens_weights`/`conviction_tiers`; `load_thresholds()` returns FLAT
   `lens_weight_*` → DB/IC weights silently ignored.
2. `calibration._load_fwd_returns` uses `technical_daily.ret_*` (TRAILING) as "forward" → IC is a tautology.

## Gotchas
- DB from `scripts/foundation/`: `python3 -c "import _db; ..."`. Postgres `NaN > 0` is TRUE.
- Destructive DB deletes get blocked by the safety classifier — need explicit FM approval each time.
- `count(distinct ...)` over `technical_daily` (6.9M rows) is slow / can time out — sample or add an index.
- `nohup python3 X &` → kill the actual python PID (`ps -eo pid,cmd | grep '[i]ngest_'`), not the wrapper.
- 6 corrupt insider rows (year 2924) still present — harmless (excluded by as_of filter), optional purge.
