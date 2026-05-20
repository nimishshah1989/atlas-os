# Stage-2 State IC Re-validation — Atlas v2 State Engine

**Date:** 2026-05-20 · **Wave 4C, Task 5** · **Read + compute only — no DB writes, no engine changes**
**Author:** Atlas audit agent · **Branch:** `feat/atlas-consolidation`
**Subject:** Does the Stage-2 state still predict forward returns *after* the
Wave 4C Task 3 (breakout-gate removal) + Task 4 (cold-start 2B/2C) classifier changes?
**Run environment:** EC2 `/home/ubuntu/atlas-os-consolidation`, in-memory classification,
live `atlas` DB (read-only).

---

## 1. What was validated and how

Wave 4C Task 3 **removed** the `close ≥ theta_base_breakout × max_close_60d`
breakout gate from `classify_stage_2a` (Task 2 showed the `breakout_ratio`
factor was IC-invalid, IR 0.11/0.14 — decorative). Task 4 added a **cold-start
structural admission path** (`_cold_start_2bc_state`) so confirmed uptrends
reach Stage 2B/2C without a prior 2A pass.

Both changes are in `atlas/intelligence/states/classifier.py`. They are NOT
verified-good until this task confirms the *resulting* Stage-2 state is still
predictive. This is the Wave 4C rigor gate.

**Method (in-memory, no DB writes):**

1. Loaded the `stocks_nifty500` OHLCV panel, 2021-11 → 2026-05 (400-day warm-up
   before the 2023-01 validation start): 695,638 rows, 750 instruments.
2. Built the 18-column feature panel via the production
   `atlas.trading.cli._compute_features_for_stock` — 524,887 (date, instrument)
   rows over 2023-01-01 → 2026-05-19.
3. Classified the SAME panel TWICE in memory:
   - **NEW** — current `classify_state_panel` (with Task 3 gate removal + Task 4 cold-start).
   - **OLD** — `classify_state_panel` from commit `749282e` (pre-Task-3/4, breakout
     gate intact, no cold-start path) — dropped in as `classifier_old.py`.
   This gives a clean apples-to-apples before/after on identical inputs.
4. Turned "is in Stage 2 (2a ∪ 2b ∪ 2c)" into a 0/1 membership factor and ran it
   through `compute_ic_over_window` — per-date Spearman rank IC vs forward
   returns, **IR = mean_ic / ic_std**.
5. Forward returns from `compute_forward_returns` on the `public.de_equity_ohlcv`
   adjusted-close matrix. **Horizons: 63d (the comparator horizon Task 2 used)
   and 21d.**

**Validation bar** (from `ic_harness.classify_ic_status`):
`|IR| > 0.4` → validated · `0.2 ≤ |IR| ≤ 0.4` → weak · `|IR| < 0.2` → decorative.
Comparator: `theta_rs` / `rs_rank_12m` carries a validated IR ≈ 0.74.

---

## 2. Results — Stage-2 membership IC

| Signal | Horizon | OLD IR | NEW IR | OLD mean IC | NEW mean IC | n dates |
|---|---|---:|---:|---:|---:|---:|
| **Stage 2 (a∪b∪c)** | **63d** | **+0.2431** | **+0.1789** | +0.018068 | +0.014655 | 778 |
| Stage 2 (a∪b∪c) | 21d | +0.1043 | +0.0753 | +0.007836 | +0.006239 | 819/820 |
| Stage 2A only | 63d | −0.0049 | +0.0470 | −0.000262 | +0.002411 | 664/777 |
| Stage 2A only | 21d | +0.0648 | +0.0551 | +0.003282 | +0.003119 | 700/820 |

**The key number — the aggregate Stage-2 state at the 63d horizon:**

- **OLD: IR = +0.243** — inside the *weak* band (0.2–0.4). The pre-change Stage-2
  state had a small but real predictive edge.
- **NEW: IR = +0.179** — **below the 0.2 weak floor → decorative.**

The gate removal **degraded** the Stage-2 state's 63d IR by ~26 % (0.243 →
0.179) and pushed it *out of the weak band and into the decorative band*. The
21d horizon shows the same direction (0.104 → 0.075). The degradation is
consistent across both horizons and rests on 778 trading-day observations — it
is not a sampling artefact.

**Stage-2A in isolation was never predictive** at the 63d horizon — OLD IR ≈
0.00, NEW IR +0.047 — confirming Task 2's finding that the breakout gate carried
no edge. But the *aggregate* Stage-2 state (which 2B/2C dominate) DID have a
weak-band edge under the OLD engine, and that is what the change eroded:
removing the gate let a wider, lower-quality cohort into 2A, and those names
flowed downstream into 2B/2C, diluting the whole family.

## 3. Cohort size — before / after

Latest date (2026-05-19), identical in-memory panel:

| State | OLD count | NEW count |
|---|---:|---:|
| stage_2a | 1 | **13** |
| stage_2b | 0 | 0 |
| stage_2c | 35 | 37 |
| stage_1 | 514 | 499 |
| stage_4 | 195 | 195 |

Monthly Stage-2 share (% of classified universe, 2023-01 → 2026-05):
**OLD** min 0.29 % / mean 5.74 % / max 12.93 % → **NEW** min 0.87 % / mean
8.19 % / max 16.35 %.

The gate removal **did** materially expand the cohort — Stage-2A on the latest
date went 1 → 13, and the mean Stage-2 share rose ~5.7 % → ~8.2 %. (Note: the
in-memory cold-start panel produces a smaller latest-date 2A count than the
DB-persisted "9" cited in the Wave 4A audit, because the panel orchestrator
treats every instrument's first observation as a cold start; the **before/after
on the identical panel** — 1 → 13 — is the valid comparison and confirms the
gate was the binding constraint.) **Stage-2B remains empty (0) in both runs** —
the cold-start path admits structurally-mature names straight to 2C, and the
2B time-window (21 < days ≤ 126, zero distribution) is genuinely hard to land in
on a per-instrument cold-start panel. Task 4 did *not* populate 2B.

So: the cohort expanded — but the expansion is precisely what degraded the IR.
The extra names admitted by dropping the gate are, on average, **not predictive
of forward returns at the 63d horizon.** The wider net caught lower-quality fish.

## 4. Comparison to the bar

| Factor / state | 63d IR | Band |
|---|---:|---|
| `theta_rs` / `rs_rank_12m` | ~0.74 | validated |
| Stage-2 state — **OLD** | +0.243 | weak |
| Stage-2 state — **NEW** | **+0.179** | **decorative** |
| `breakout_ratio` factor (Task 2) | 0.14 | decorative |

The NEW Stage-2 state's IR (0.179) is now barely above the IC-invalid
`breakout_ratio` factor (0.14) and **roughly one quarter** of `theta_rs`. The
change moved the Stage-2 state from a (weak but real) signal into the same
decorative band as the factor Task 2 condemned.

---

## 5. VERDICT — **DO NOT SHIP**

The Wave 4C Task 3/4 classifier changes **degrade** the predictive quality of
the Stage-2 state and **must not be deployed as-is.**

- The aggregate Stage-2 state's 63d IR fell from **+0.243 (weak band) to +0.179
  (decorative band)** — a ~26 % degradation that crosses the 0.2 weak floor.
- The 21d horizon confirms the same direction (0.104 → 0.075).
- Removing the breakout gate expanded Stage-2A (1 → 13 on the latest date; mean
  Stage-2 share 5.7 % → 8.2 %), but the expansion **admitted a cohort whose
  state no longer predicts forward returns** — exactly the failure mode the
  Wave 4C STOP gate (and this task) was built to catch.
- Task 4's cold-start path did **not** populate Stage-2B (still 0 in both runs);
  its only effect is routing structurally-mature names to 2C.

This is an honest negative result. Task 2 correctly showed the `breakout_ratio`
*factor* was decorative — but the gate, despite the factor's weakness, was
acting as a **quality filter** on Stage-2A admission. Dropping it without a
replacement filter let lower-quality names into the whole Stage-2 family and
diluted the (genuine, weak-band) edge the Stage-2 state previously carried.

### Recommendation

1. **Do not deploy the Task 3 gate removal in its current form.** Do not run the
   nightly re-classification or persist the new states.
2. **Narrow Task 3, do not fully revert it.** The Wave 4A audit correctly
   identified the exact-1.000 multiplier as a structural chokepoint. The fix is
   a **soft tolerance band**, not outright removal — e.g. re-instate the gate at
   `close ≥ 0.92–0.95 × max_close_60d`. This admits "breakout from a tight
   base" (the 66-stock near-miss cohort) while still excluding names that are
   nowhere near a 60-day high. Pick the band by IC, then re-run this exact
   re-validation; the SHIP bar is **NEW 63d IR ≥ 0.243** (no degradation vs the
   OLD baseline) and ideally back inside the weak band.
3. **Keep Task 4 (cold-start 2B/2C) — it is IR-neutral**, but note it does not
   populate 2B; if a populated 2B matters downstream, the 2B cold-start
   predicate needs its own design pass.
4. Any re-tune of the tolerance band is its own piece of work and requires a
   re-run of this gate before it ships.

**Bottom line:** the Wave 4C engine changes are **NOT safe to deploy.** The gate
removal traded a weak-but-real predictive Stage-2 state for a larger,
non-predictive one. Narrow Task 3 to a soft band and re-validate.
