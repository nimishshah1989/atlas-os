# breakout_ratio IC Validation — Atlas v2 State Engine

**Date:** 2026-05-20 · **Wave 4C, Task 2** · **Report-only — no engine changes, no DB writes**
**Author:** Atlas audit agent · **Branch:** `feat/atlas-consolidation`
**Factor:** `breakout_ratio` = `close / max_close_60d_excl_today` (`tune_catalog.py`)
**Validation range:** 2023-01-01 → 2026-05-19 · **Universe:** 2,251 instruments, 841 trading days
**Factor panel:** 1,412,956 (date, instrument) observations

---

## 1. What was validated and how

The Stage-2A breakout gate (`classify_stage_2a`) uses `close ≥ theta_base_breakout × max_close_60d`.
The Stage-2 threshold audit (`docs/audits/2026-05-stage2-threshold-audit.md`) flagged
`theta_base_breakout = 1.000` as the single binding gate that compresses the entire
Stage-2 family — and as the **only** un-IC-validated Stage-2 threshold. Wave 4C Task 1
built the `breakout_ratio` factor builder (previously a `NotImplementedError`). This
task runs it through the IC harness before any re-tune (Task 3).

**Harness entry point:** `compute_ic_over_window(factor, returns_wide)` in
`atlas/intelligence/validation/ic_engine.py` — per-date Spearman rank IC across
instruments, then mean/std across dates. `ICResult.mean_ic` and `ic_std` give
**IR = mean_ic / ic_std**. Forward returns from `compute_forward_returns` on the
`public.de_equity_ohlcv` price matrix.

**Horizons:** `theta_base_breakout`'s catalog entry uses **21 trading days**;
the validated comparator `theta_rs` used **63 days**. Both were run.

**Validation bar (from `ic_harness.classify_ic_status` / `component_validator.py`):**
- `IR > 0.4` AND `|spread| > 0.005` → **validated**
- `IR < -0.4` AND `|spread| > 0.005` → **validated_inverse**
- `0.2 ≤ |IR| ≤ 0.4` → **weak**
- `|IR| < 0.2` → **decorative**

---

## 2. Results

| Metric | Horizon 21d | Horizon 63d |
|---|---:|---:|
| mean IC | +0.013066 | +0.015462 |
| IC std | 0.122514 | 0.106849 |
| IC t-stat | 3.054 | 4.036 |
| **Information Ratio (IR)** | **0.1066** | **0.1447** |
| Q5−Q1 spread | **−0.005005** | **−0.014059** |
| n observations (dates) | 820 | 778 |

**IR is 0.11 (21d) and 0.14 (63d) — both well below the 0.4 validation bar AND
below the 0.2 weak floor.** Mean IC is statistically distinguishable from zero
(t-stat 3–4 over 800 dates) but the *magnitude* is trivially small. A factor
with mean IC ≈ 0.013–0.015 and IC std ≈ 0.11–0.12 has almost no cross-sectional
ranking power: the signal-to-noise ratio is roughly 1:7.

**The quantile spread is NEGATIVE at both horizons** (−0.005 at 21d, −0.014 at
63d). Stocks in the *top* breakout-ratio quintile (closest to / above their
60-day high) earn **lower** forward returns than the *bottom* quintile. The
mean IC is marginally positive while the top-vs-bottom decile spread is
negative — meaning whatever weak monotonic signal exists does not survive at
the extremes, and the extreme "fresh breakout" cohort the gate actually selects
shows mild *mean-reversion*, not continuation.

## 3. IC time series

| | 21d | 63d |
|---|---:|---:|
| months | 40 | 38 |
| % months IC positive | 55.0 % | 57.9 % |
| monthly IC min | −0.222 (2026-03) | −0.181 (2025-03) |
| monthly IC max | +0.184 (2024-08) | +0.190 (2025-11) |
| monthly IC median | +0.016 | +0.017 |

The monthly IC oscillates around zero with no stable sign. It is positive in
roughly 55–58 % of months — a near-coin-flip. There is no regime where
`breakout_ratio` is reliably predictive; the most recent prints (2026-03 at
−0.22, 2026-04 at −0.08) are firmly negative.

## 4. Comparison to validated state factors

| Factor | IR | Status |
|---|---:|---|
| `theta_rs` / `rs_rank_12m` | **~0.74** | validated (in `atlas_state_thresholds`) |
| `breakout_ratio` (63d) | **0.14** | **decorative** |
| `breakout_ratio` (21d) | **0.11** | **decorative** |

`breakout_ratio`'s IR is roughly **one fifth** of `theta_rs`'s. `theta_rs`
clears the bar with 1.85× margin; `breakout_ratio` misses the *weak* floor (0.2)
by ~30 % and misses the *validated* bar (0.4) by ~3.5×. The two Stage-2A gates
are not remotely comparable in predictive quality.

---

## 5. VERDICT — **INVALID**

`breakout_ratio` is **not IC-validated and not genuinely predictive.**

- IR = 0.11 (21d) / 0.14 (63d) — below the 0.2 weak floor, far below the 0.4 bar.
- Q5−Q1 spread is **negative** at both horizons: the top breakout-ratio quintile
  *underperforms*. The extreme cohort the gate selects shows mild mean-reversion.
- Monthly IC is positive only ~55–58 % of months — no stable predictive regime.
- IR is ~5× weaker than the validated `theta_rs` gate.

Per `ic_harness.classify_ic_status`, with `|IR| < 0.2` this classifies as
**`decorative`**. With a negative quantile spread it leans toward
**anti-predictive at the selection extreme** — i.e. the gate is not just weak,
the cohort it isolates does not earn the continuation premium the gate assumes.

## 6. STOP — Task 3 must NOT proceed as a re-tune

Per the Wave 4C STOP gate: **`breakout_ratio` is IC-invalid → Task 3 (grid
tuning of `theta_base_breakout`) MUST NOT proceed.** Re-tuning the multiplier
across 0.98–1.05 would optimise the threshold of a non-predictive factor — it
would fit noise and produce a falsely-precise number.

**Escalation / recommendation:**

1. **Do not re-tune `theta_base_breakout`.** There is no validated curve to
   tune against. A tuning grid would overfit the IC noise.
2. **Loosen the gate toward removal, not optimisation.** The Stage-2 audit
   already showed the 1.000 multiplier is the structural chokepoint blocking
   66 otherwise-qualified stocks. Since the breakout factor itself carries no
   predictive edge, the correct move is to *relax or drop* the exact-60-day-high
   requirement and let the **validated** gates (`theta_rs` IR 0.74, MA-stack,
   rising SMA-200) carry Stage-2A admission — possibly with a soft tolerance
   band (e.g. 0.90–0.95) used only as a noise filter, not as a predictive gate.
3. **Pair with the Stage-2A→2B→2C reachability fix** recommended in §6.3 of the
   Stage-2 threshold audit (an "already in Stage 2" admission path), so
   confirmed uptrends are not orphaned in stage_1.
4. Any change to `classify_stage_2a` requires full state-engine IC
   re-validation as its own piece of work — it is not a threshold tweak.

**Bottom line:** the breakout-ratio factor does not predict forward returns.
The Stage-2 audit's hypothesis — that `theta_base_breakout = 1.000` is an
un-validated assumption doing structural damage — is confirmed by the data, and
the data further shows the factor cannot be rescued by tuning. Stop the re-tune;
escalate to a gate-removal / soft-band redesign decision instead.
