# Stage-2 State IC Re-validation — Soft-Band Breakout Gate

**Date:** 2026-05-20 · **Wave 4C, soft-band rework** · **Read + compute only — no DB writes**
**Author:** Atlas audit agent · **Branch:** `feat/atlas-consolidation`
**Subject:** Does re-introducing the Stage-2A breakout gate as a SOFT tolerance
band restore the Stage-2 state's predictive edge to the pre-Task-3 baseline?
**Run environment:** EC2 `/home/ubuntu/atlas-os-consolidation`, in-memory
classification, live `atlas` DB (read-only). Same 524,887-row 2023-2026 panel
as the Task 5 re-validation.

---

## 1. Background — the Wave 4C decision chain

- **Task 2** — the `breakout_ratio` *factor* is decorative cross-sectionally
  (IR 0.11/0.15, below the 0.2 weak floor).
- **Task 3** (commit `6d972c2`) — REMOVED the breakout gate from `classify_stage_2a`.
- **Task 5** — removal **degraded** the aggregate Stage-2 state: 63d IR fell from
  **+0.243** (gate intact) to **+0.179** (gate removed) — out of the weak band
  into the decorative band. The gate, though its factor does not rank, works as a
  useful **binary quality filter**.
- **This rework** — re-introduce the gate as a SOFT tolerance band
  (`close >= theta_base_breakout * max_close_60d`, theta in 0.90-0.98) and
  IC-tune theta to the value that restores the Stage-2 state's 63d IR to **>= 0.243**
  while admitting more stocks than the original hard 1.000 gate.

**SHIP bar:** final Stage-2 state 63d IR **>= 0.243**.

---

## 2. Method

Identical to the Task 5 method (see `2026-05-stage2-state-revalidation.md`):

1. Load `stocks_nifty500` OHLCV, 2021-11 → 2026-05 (400-day warm-up): 695,638
   rows, 750 instruments.
2. Build the 18-column feature panel via the production
   `atlas.trading.cli._compute_features_for_stock` → **524,887 (date, instrument)
   rows**, 2023-01-01 → 2026-05-19.
3. Classify the panel in memory; turn "is in Stage 2 (2a ∪ 2b ∪ 2c)" into a 0/1
   membership factor; run it through `compute_ic_over_window` (per-date Spearman
   rank IC, IR = mean_ic / ic_std).
4. Forward returns from `compute_forward_returns` on `public.de_equity_ohlcv`
   adjusted close. Horizons: **63d** (the comparator) and **21d**.

The grid was run in **two topologies** to isolate the breakout gate's effect
from the Task 4 cold-start path:

- **OLD topology** — `classify_state_panel` from commit `749282e`: hard gate,
  **no Task 4 cold-start path**. This is the exact topology Task 5's +0.243
  baseline was measured in — a clean apples-to-apples for the gate.
- **CURRENT topology** — the shipping `classify_state_panel`: Task 4 cold-start
  path active, with the re-introduced soft gate.

`theta_base_breakout` swept over **{0.90, 0.92, 0.94, 0.96, 0.98}** plus the
1.000 baseline.

---

## 3. Results — IC-tune grid

### 3a. OLD topology (no cold-start) — the clean apples-to-apples vs +0.243

| theta | Stage-2 63d IR | 21d IR | Stage-2A count | 2B | 2C |
|---:|---:|---:|---:|---:|---:|
| 0.90 | +0.2018 | +0.0893 | 9 | 0 | 37 |
| 0.92 | +0.2064 | +0.0967 | 11 | 0 | 36 |
| 0.94 | +0.2076 | +0.1069 | 10 | 0 | 36 |
| 0.96 | +0.2236 | +0.1205 | 8 | 0 | 35 |
| 0.98 | +0.2252 | +0.1022 | 6 | 0 | 36 |
| **1.00** | **+0.2431** | +0.1043 | 1 | 0 | 35 |

The 1.000 row reproduces Task 5's **+0.243** baseline to four decimals — the
harness is sound. The 63d IR is **monotone in theta**: it degrades smoothly as
the band loosens. **No soft-band value in 0.90-0.98 clears the 0.243 bar.** The
best soft value (0.98) reaches only +0.2252 — ~0.018 IR below the bar.

### 3b. CURRENT topology (Task 4 cold-start active) — the shipping classifier

| theta | Stage-2 63d IR | 21d IR | Stage-2A count | 2B | 2C |
|---:|---:|---:|---:|---:|---:|
| 0.90 | +0.2059 | +0.0923 | 9 | 0 | 37 |
| 0.92 | +0.2054 | +0.0956 | 11 | 0 | 36 |
| 0.94 | +0.1986 | +0.0985 | 10 | 0 | 36 |
| 0.96 | +0.2103 | +0.1093 | 8 | 0 | 35 |
| 0.98 | +0.2100 | +0.0904 | 6 | 0 | 36 |
| **1.00** | **+0.2260** | +0.0855 | 1 | 0 | 35 |

In the shipping topology even the **hard 1.000 gate reaches only +0.226** — it
does NOT recover the +0.243 baseline.

### 3c. The decisive finding — Task 4's cold-start path dilutes the IR

Comparing the two 1.000 rows isolates the cause:

| Configuration | 63d IR |
|---|---:|
| OLD topology, hard gate 1.000 (= Task 5 baseline) | **+0.2431** |
| CURRENT topology, hard gate 1.000 (Task 4 cold-start ON) | **+0.2260** |
| Task 3 — gate fully removed (Task 5 result) | +0.179 |

The breakout gate is identical in the top two rows; the only difference is the
**Task 4 cold-start 2B/2C path**. It costs **~0.017 IR**. The cold-start path
admits structurally-mature names *straight to Stage 2C, bypassing the Stage-2A
breakout gate entirely* — so the gate cannot filter them. Task 5 flagged exactly
this risk ("Keep Task 4… but note it does not populate 2B"); the IC cost was not
quantified there.

---

## 4. Comparison to the bar

| Configuration | 63d IR | Band |
|---|---:|---|
| `theta_rs` / `rs_rank_12m` (comparator) | ~0.74 | validated |
| Stage-2 state — OLD baseline (gate 1.000, no cold-start) | +0.243 | weak |
| Stage-2 state — best soft band (OLD topo, theta 0.98) | +0.225 | weak (edge) |
| **Stage-2 state — SHIPPING classifier (gate 1.000 + cold-start)** | **+0.226** | **weak (edge)** |
| Stage-2 state — Task 3 gate fully removed | +0.179 | decorative |

---

## 5. VERDICT — **DO NOT SHIP** (as a soft band)

**No `theta_base_breakout` value in 0.90-0.98 restores the Stage-2 state's 63d
IR to the 0.243 SHIP bar.** Two independent findings, three runs:

1. **The soft band does not work.** 63d IR is monotone in theta — every
   loosening below 1.000 admits a lower-quality cohort and dilutes the IR. The
   gate is predictive *because* it is a literal 60-day-high filter; a tolerance
   band is strictly worse. The original hard 1.000 gate was correct.
2. **Task 4's cold-start path independently caps the IR at +0.226.** Even with
   the hard 1.000 gate restored, the shipping classifier cannot reach +0.243,
   because the cold-start path routes structurally-mature names to Stage 2C
   without passing the breakout gate.

### What was implemented anyway (and why)

The breakout gate is **re-introduced** in `classify_stage_2a` at the IC-proven
**theta_base_breakout = 1.000** (read from `atlas_state_thresholds`, code default
1.000). This is NOT the soft band — it is the restoration of the hard gate Task 3
removed. Rationale: leaving Task 3's no-gate state in place ships a **+0.179
(decorative)** Stage-2 state; restoring the gate at 1.000 recovers it to **+0.226
(weak band)** — a partial recovery that is strictly better than shipping Task 3
as-is. The classifier code is correct and the gate is restored; the **SHIP gate
for Wave 4C is still not met** because of finding 2.

### Recommendation — Wave 4C is NOT safe to deploy as-is

- **Keep the re-introduced hard gate at theta_base_breakout = 1.000.** The IC
  grid proves no soft value beats it; the soft-band hypothesis is rejected on
  data. Do not lower theta below 1.000.
- **The blocker is now Task 4, not the gate.** To clear the 0.243 bar the Task 4
  cold-start 2B/2C path must be revisited — either (a) route cold-start
  admissions through the breakout gate too, or (b) gate cold-start 2C admission
  on the same breakout-quality condition, or (c) revert Task 4. This is a
  separate piece of work and requires its own re-run of this gate.
- Until Task 4 is addressed, the shipping Stage-2 state sits at **+0.226** — in
  the weak band, above Task 3's +0.179, but **below the +0.243 no-degradation
  bar.** Do NOT run the nightly re-classification / persist new states for
  production until the bar is met.

**Bottom line:** the soft-band hypothesis is **rejected** — 1.000 is the
IC-optimal breakout threshold and has been restored. But Wave 4C as a whole is
**DO-NOT-SHIP**: Task 4's cold-start path caps the Stage-2 state at +0.226,
short of the +0.243 bar. Wave 4C is **not safe to deploy** until the Task 4
cold-start admission path is brought under the breakout gate (or reverted).
