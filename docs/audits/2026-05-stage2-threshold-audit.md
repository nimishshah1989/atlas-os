# Stage-2 Threshold Audit — Atlas v2 State Engine

**Date:** 2026-05-20 · **Wave 4A, Task 1** · **Report-only — no engine changes**
**Author:** Atlas audit agent · **Branch:** `feat/atlas-consolidation`
**State table:** `atlas.atlas_stock_state_daily` (`classifier_version='v2.0-validated'`)
**Latest data:** 2026-05-19

---

## 1. Today's state distribution

Latest-date (2026-05-19) count per `state`, 747 stocks:

| State          | Count | % of universe |
|----------------|------:|--------------:|
| stage_1 (Base) |   542 |        72.6 % |
| stage_4 (Decline) | 194 |     26.0 % |
| **stage_2a (Fresh Breakout)** | **9** | **1.2 %** |
| stage_2b / stage_2c | **0** | **0.0 %** |
| uninvestable   |     2 |         0.3 % |
| **Total**      |   747 |               |

The 9/747 Stage-2A figure is **confirmed**. There are **zero** Stage-2B and
Stage-2C stocks — the entire Stage-2 cohort is the 9 fresh-breakout stocks.
Classified universe (excl. uninvestable) = 745.

## 2. Historical Stage-2 share — monthly series 2023-01 → 2026-05

`% of classified universe in stage_2a + stage_2b + stage_2c`, sampled on the
last trading day of each month:

| Period | Stage-2 % | | Period | Stage-2 % |
|---|---:|---|---|---:|
| 2023-01 | 1.16 | | 2024-11 | 3.49 |
| 2023-04 | 7.16 | | 2024-12 | 4.77 |
| 2023-07 | 12.91 | | 2025-01 | **0.44** (series min) |
| 2023-11 | 12.26 | | 2025-02 | 0.44 |
| 2024-01 | **12.93** (series max) | | 2025-07 | 1.27 |
| 2024-03 | 2.84 | | 2025-08 | 0.84 |
| 2024-06 | 9.29 | | 2026-03 | 0.67 |
| 2024-10 | 4.59 | | 2026-04 | 5.76 |
| | | | **2026-05** | **1.21** |

**Series statistics (41 months):** min **0.44 %**, max **12.93 %**,
median **4.55 %**, mean **5.18 %**.

Today's 1.21 % is in the **bottom quartile** but is **not an outlier**:
seven prior months printed a lower Stage-2 share (0.44–1.16 %), and the
immediately-preceding tape was volatile — 2026-03 was 0.67 %, 2026-04 jumped to
5.76 %, 2026-05 fell back to 1.21 %. Stage-4 share simultaneously ran 50–26 % over
2026-01→05, confirming a genuinely weak tape. **The macro picture is consistent
with a weak-but-not-extreme market.**

## 3. Stage-2 entry conditions (from `classifier.py`)

**Stage 2A — Fresh Breakout** (`classify_stage_2a`). ALL must hold:

1. `prior_state ∈ {stage_1, stage_4}` — only fires on a *transition* day.
2. MA stack up: `close > sma_50 > sma_150 > sma_200`.
3. `sma_200_slope > 0`.
4. **Breakout:** `close ≥ theta_base_breakout × max_close_60d`
   (`theta_base_breakout = 1.000` → close must equal/exceed the exact 60-day high).
5. `rs_rank_12m × 100 ≥ theta_rs` (`theta_rs = 80`).
6. `days_in_stage_2 ≤ theta_fresh_days` (21).

**Stage 2B — Confirmed** (`classify_stage_2b`). Requires `in_stage_2 = True`
(which requires `prior_state` *already* in `stage_2a/2b/2c`), `21 < days_in_stage_2 ≤ 126`,
zero 5-day distribution days, `close > sma_50`.

**Stage 2C — Mature** (`classify_stage_2c`). Requires `in_stage_2 = True`, then
ANY of: `days_in_stage_2 > 126`, `close/sma_50 > 1.10`, `atr_14/atr_14_50d_avg > 1.40`.

**Structural consequence:** 2B and 2C can **only** be reached by a stock that
*first passed through 2A*. A stock that holds a clean uptrend but never prints an
exact 60-day high *on a transition day* can never enter Stage 2 at all — it stays
in stage_1 indefinitely. The breakout gate is therefore the **single chokepoint**
for the entire Stage-2 family.

**IC-validation status of the gates:**
- `theta_rs` (=80) — **IC-validated**, IR 0.7410 (`atlas_state_thresholds`).
- `theta_base_breakout` (=1.000) — **NOT IC-validated.** `tune_catalog.py`
  explicitly raises `NotImplementedError` for the `breakout_ratio` factor builder;
  the Phase-2 IC doc (`state-engine-phase2-ic-2026-05.md` §"breakout_ratio tuning")
  records it as *"deferred to a Phase 2 iteration."* The value 1.000 is an
  un-tuned assumption, not a validated threshold.

## 4. Near-miss cohort (today, 2026-05-19)

Each Stage-2A gate evaluated independently across the 745 classified stocks
(MA-stack reconstructed from `close_vs_sma_50/150/200`; a larger `close_vs_sma_k`
implies a smaller `sma_k`):

| Gate | Stocks passing |
|---|---:|
| MA stack up (`close>sma50>sma150>sma200`) | 116 |
| `sma_200_slope > 0` | 592 |
| `rs_rank_12m ≥ 80` | 139 |

**Stocks passing BOTH the MA-stack AND the slope gate (full positive trend): 115.**
Of those 115, **75 also have RS ≥ 80** — i.e. 75 stocks satisfy *every*
structural Stage-2A gate (trend + slope + RS) yet only **9** are classified
Stage 2A.

Where the 75 trend-OK + RS≥80 stocks actually land today:

| Landing state | Count |
|---|---:|
| stage_2a | 9 |
| **stage_1** | **66** |

All 66 have `prior_state = stage_1`. They are eligible for Stage 2A on
prior-state grounds — they fail **only** the breakout gate (`close ≥ max_close_60d`)
and/or are past the 21-day fresh window with no 2B/2C to catch them.

**Largest near-miss cohort: 66 stocks** — full MA-stack-up, rising SMA-200,
RS ≥ 80, currently parked in stage_1, blocked at the **breakout gate**.

Sensitivity of the RS gate (for the 115 full-trend stocks):
RS≥80 → 75, RS≥75 → 92, RS≥70 → 99, RS≥65 → 103, RS≥60 → 106. Loosening RS adds
relatively few stocks; the RS gate is **not** the binding constraint.

## 5. Universe input distributions (today)

| Input | min | p25 | p50 | p75 | p90 | max | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| `rs_rank_12m × 100` | 0.1 | 27.2 | 50.0 | 73.1 | 89.3 | 100 | ≥ 80 |
| `close_vs_sma_50` | −0.652 | −0.010 | 0.037 | 0.093 | — | 0.773 | > 0 (stack) |
| `sma_200_slope` | −0.037 | 0.0005 | 0.0028 | 0.0057 | — | 0.027 | > 0 |

- 18.7 % of the universe has RS ≥ 80 — a healthy supply of relatively-strong stocks.
- 69.9 % trade above their SMA-50; 79.5 % have a rising SMA-200. The market is
  **not** structurally broken — most stocks have a positive long-term slope.
- The mass that *clears the trend gates* is large (115 stocks); it is the
  **breakout gate** that compresses 115 → 9.

## 6. VERDICT — **UNDER-CLASSIFYING**

The 9/747 Stage-2A figure is **not** primarily a thin-breadth bear market. The
macro tape is genuinely weak (1.21 % Stage-2 is bottom-quartile, 26 % Stage-4),
but the magnitude of the under-count is a **structural artefact of one gate**.

**The binding gate:** `theta_base_breakout = 1.000` in `classify_stage_2a`
(`close ≥ theta_base_breakout × max_close_60d`).

**Near-miss count:** **66 stocks** today satisfy every structural Stage-2A
condition (MA stack up, rising SMA-200, RS ≥ 80, eligible `prior_state`) and are
blocked solely at the breakout gate, sitting in stage_1.

**Why it cascades:** Stage 2B and 2C are reachable *only* via Stage 2A
(`in_stage_2` depends on a prior `stage_2x` state). Because the breakout gate
fires only on the exact day a stock prints a fresh 60-day high *and* is on a
transition, the vast majority of healthy uptrending stocks never enter the
Stage-2 family — hence **zero** Stage-2B and Stage-2C. A 1.000 multiplier with no
tolerance band means a stock 0.5 % below its 60-day high on its transition day is
permanently excluded. This explains both the thin 9-stock 2A cohort and the
complete absence of 2B/2C that collapsed the downstream sector/fund classifiers.

**Aggravating factor:** `theta_base_breakout` was **never IC-validated** — the
`breakout_ratio` factor builder is an explicit `NotImplementedError` in
`tune_catalog.py`, deferred per the Phase-2 IC doc. By contrast `theta_rs` (the
gate that is *not* binding) carries a validated IR of 0.74. The system's only
un-validated Stage-2 threshold is the one doing all the damage.

### Follow-up recommendation (SEPARATE task — NOT Wave 4A)

Re-tuning `theta_base_breakout` is **out of scope for Wave 4A** and must NOT be
done as part of this task. The state engine is IC-validated as a whole; changing
a gate requires full IC re-validation. Recommended separate follow-up:

1. **Build the deferred `breakout_ratio` factor builder** (`close / max_close_60d_excl_today`,
   the `NotImplementedError` path in `tune_catalog.py`) and run it through
   `ic_harness.py` to produce an IC/IR curve for `theta_base_breakout`.
2. **IC-tune `theta_base_breakout`** across a grid (e.g. 0.90–1.00) and pick the
   value that maximises forward-return IC, exactly as `theta_rs` was tuned. A
   plausible outcome is a small tolerance band (e.g. 0.97) that admits "breakout
   from a tight base" without admitting non-breakouts — but the data, not this
   audit, must set the number.
3. **Separately review the Stage-2A→2B→2C reachability chain.** Even with a
   looser breakout gate, a stock that is mid-uptrend on the day the engine first
   sees it (no prior `stage_1→stage_2a` transition in-window) cannot enter
   Stage 2. Consider an "already in Stage 2" admission path (trend + RS satisfied,
   regardless of a fresh breakout) so confirmed uptrends are not orphaned in
   stage_1. This too requires IC re-validation.

Until that validated re-tune lands, downstream sector/fund classifiers should
**not** assume a populated Stage-2 cohort.

## 7. Bottom line for a PM

Only 9 of 747 Indian stocks currently read as Stage-2 "fresh breakout," and there
are zero confirmed or mature Stage-2 names. The market *is* weak — a quarter of
the universe is in decline — but that is **not** the main reason the Stage-2
bucket is nearly empty. 66 stocks are in clean, rising-200-day-average uptrends
with strong 12-month relative strength, and the engine is leaving every one of
them in "Base." The cause is a single, never-validated rule that only tags a
stock as Stage 2 on the *exact day* it closes at a fresh 60-day high. The number
9 understates how many genuinely-uptrending stocks exist today; treat the
Stage-2 list as incomplete until that one rule is re-tuned and re-validated as a
separate piece of work.
