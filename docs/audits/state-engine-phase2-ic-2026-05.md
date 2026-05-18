# State Engine Phase 2 — IC Tuning + Component Investigation

**Date:** 2026-05-18
**Branch:** feat/atlas-strategy-lab
**Data window:** 2023-01-01 → 2024-12-31 (487 trading days, 1955 instruments, 273k stock-day rows)

## Summary

Phase 2 tuning + Phase 2.3 component investigation found:

1. **θ_rs is the load-bearing signal.** RS rank ≥ 80 gives IR 0.74 / Q5–Q1 +5.88% at 63d. Applied 70 → 80.
2. **Volume confirmation is decorative.** `volume_today / volume_50d_avg` at 21d has IR 0.15, Q5–Q1 ≈ 0. Dropped from Stage 2A.
3. **NATR (atr/close) is decorative.** Stage 1's old vol metric has IR -0.18 at 63d. Replaced with ATR contraction ratio.
4. **ATR contraction ratio is validated.** `atr_14 / atr_14_252d_avg` has IR -0.48 at 63d (contracting → higher returns). New Stage 1 rule.
5. **realized_vol_63 is validated.** IR +0.55 at 63d in this universe. Added to within-state-rank composite for Stage 2A bonus.
6. **OBV slope 50d at 63d is validated_inverse.** IR -0.43 at 63d (falling OBV cross-section outperforms). Use case is Stage 3 *topping* warning: when a held Stage 2 stock's OBV slope turns negative, it's exiting accumulation. Added as Stage 3 trigger.

## Tuning results (atlas-lab states tune --dry-run, 2023-01-01 → 2024-12-31)

### θ_rs (Stage 2A) — VALIDATED ✓

| cutoff | IR | Q5–Q1 spread (63d) |
|---|---|---|
| 50 | 1.10 | 0.052 |
| 60 | 0.77 | 0.045 |
| 70 (prior active) | 0.67 | 0.045 |
| 75 | 0.71 | 0.051 |
| **80** | **0.74** | **0.059** ← new active |
| 85 | 0.70 | 0.057 |
| 90 | 0.62 | 0.055 |

Optimal selected by max Q5–Q1 among gate-passers. Persisted via direct DB update.

### θ_vol_mult (Stage 2A) — DECORATIVE ✗ (dropped from rule)

| cutoff | IR | Q5–Q1 spread (21d) |
|---|---|---|
| 1.0 | 0.11 | -0.003 |
| 1.5 (prior active) | 0.14 | 0.001 |
| 2.0 | 0.15 | 0.007 |
| 3.0 | 0.07 | 0.002 |

No candidate passed IR > 0.4 gate. Rule removed entirely from `classify_stage_2a` in commit 749282e.

### θ_distribution (Stage 3) — WEAK (kept at 5)

| cutoff | IR | Q5–Q1 spread (21d) |
|---|---|---|
| 5 (prior + new active) | 0.25 | 0.004 |
| 7 | 0.24 | 0.010 |
| 8 | 0.19 | 0.012 |

Falls below gate but signal is monotonic. Kept at 5; OBV slope (newly validated) augments the topping rule.

## Alternative-metric IC investigation (volume + volatility)

Script: `/tmp/investigate_vol_volume_alternatives.py` (run against live DB; not in repo).

### Volume metrics @ 21d and 63d

| Metric | Horizon | IR | Status |
|---|---|---|---|
| up_down_volume_ratio_50d | 21d | -0.24 | weak |
| up_down_volume_ratio_50d | 63d | -0.19 | decorative |
| obv_slope_50d | 21d | -0.32 | weak |
| **obv_slope_50d** | **63d** | **-0.43** | **VALIDATED_INVERSE** |

OBV slope is the only volume-derived metric that crosses the IR > 0.4 bar. Sign is inverse: cross-sectionally, stocks with FALLING OBV outperformed at 63d in this universe. For a held Stage 2 stock, falling OBV is a *topping* signal — incorporated as a Stage 3 trigger.

### Volatility metrics @ 63d

| Metric | IR | Status |
|---|---|---|
| atr_14 / close (NATR) | -0.18 | decorative |
| **realized_vol_63** | **+0.55** | **VALIDATED** |
| **atr_14 / atr_14_252d_avg** (contraction) | **-0.48** | **VALIDATED** |
| h-l range 20d / close | -0.30 | weak |

Two validated metrics. Their interpretation:
- **realized_vol_63 (+0.55)**: high realized volatility correlates with higher 63d forward returns in this universe (small/mid-cap momentum). Inverted "low-vol anomaly." Added to within-state-rank as a positive weight (0.3).
- **atr_contraction (-0.48)**: stocks whose current 14-day ATR is below their 252-day ATR average outperform at 63d. Classic Minervini "volatility contraction precedes breakout." Used as Stage 1 base definition: a stock is "in a base" only when its volatility is contracting.

## Engine changes shipped (commit 749282e)

1. **Stage 1 (Base)**: vol predicate swapped to `atr_14 / atr_14_252d_avg < θ_contraction` (θ_contraction = 0.95 active).
2. **Stage 2A (Fresh Breakout)**: volume conjunct dropped entirely. `volume_today` and `volume_50d_avg` no longer parameters of `classify_stage_2a`.
3. **Stage 3 (Top)**: OBV-slope-negative added as alternative trigger. `(close < SMA_50 OR SMA_50 slope < 0 OR obv_slope_50d < θ_obv_slope_neg)` with θ_obv_slope_neg = 0.0.
4. **within_state_rank**: new formula `0.4 × freshness + 0.3 × rs_rank + 0.3 × realized_vol_rank` (was 0.5 / 0.5).

Migration 078 deactivates `theta_low_vol` and `theta_vol_mult`; inserts `theta_contraction` and `theta_obv_slope_neg`.

## What this audit does NOT cover (deferred to Phase 2.5 + Phase 3)

- **Component-tier validation** (Phase 2.5): each badge tier (RS Leader / Strong / Average / etc.) gets per-tier IC. Tracked.
- **breakout_ratio tuning**: needs raw-OHLCV factor builder. Deferred to a Phase 2 iteration.
- **realized_vol_63 used as Stage 2A entry filter**: not yet — used only for within-state ranking. Phase 3+ may add `realized_vol_rank ≥ θ_min_vol_rank` as an entry filter once we see how the engine performs with the current changes.
- **OBV slope used as Stage 2A entry filter**: not yet — used only for Stage 3 topping detection. Same reasoning.

## Next operational step

Re-classify 2023-2024 with `v2.0-validated` (running 2026-05-18 ~15:50 IST). Compare state distribution against `v1.0-tune-base`. Expected: more Stage 2A entries (volume requirement gone), fewer false Stage 1 (NATR-decorative metric replaced), Stage 3 transitions earlier (OBV trigger active).

## Phase 2.5 — Per-tier component validation (2026-05-18 16:20 IST)

Run via `atlas-lab states validate-components --start 2023-01-01 --end 2024-12-31`. 13 (component, badge) rows persisted to `atlas_component_validation`.

### Findings

**Component: rs_rank_12m**

| Tier | IR | Q5-Q1 | Status |
|---|---|---|---|
| Leader (≥0.90) | +0.62 | +5.5% | validated ✓ |
| Strong (0.70-0.90) | +0.54 | +2.8% | validated ✓ |
| Average (0.30-0.70) | +0.02 | -0.3% | decorative |
| Weak (0.10-0.30) | -0.72 | -4.7% | validated ✓ |
| Laggard (<0.10) | -0.58 | -1.6% | validated ✓ |

→ Extreme tiers earn their badges; middle tier doesn't. Drop "Average" implied-action from UI.

**Component: obv_slope_50d**

| Tier | IR | Status |
|---|---|---|
| Accumulation (slope > 0) | +0.00 | decorative |
| Distribution (slope < 0) | -0.00 | decorative |

→ Binary tier collapses the signal. Continuous OBV slope IS predictive (-0.43 found in alternative investigation), but the *labeled badge* isn't. Frontend should show continuous OBV value, not a "Accumulation/Distribution" badge.

**Component: realized_vol_63**

| Tier | IR | Q5-Q1 | Status |
|---|---|---|---|
| Low (p<0.25) | -0.70 | -6.5% | validated ✓ |
| Normal (0.25-0.50) | -0.25 | -2.9% | weak |
| Elevated (0.50-0.75) | +0.91 | +1.4% | validated ✓ |
| High (p≥0.75) | +0.37 | +8.6% | weak |

→ Strong inversion of "low-vol anomaly": bottom-vol stocks underperform by 6.5% over 63d. Top-vol Q5-Q1 is the largest at +8.6%. Use Elevated/High tiers as conviction-positive; flag Low tier as "warns long."

**Component: atr_contraction_ratio**

| Tier | IR | Status |
|---|---|---|
| Contracting (ratio < 1.0) | +0.01 | decorative |
| Expanding (ratio ≥ 1.0) | -0.01 | decorative |

→ Same as OBV: binary tier collapses signal. Continuous ratio IS predictive (-0.48 found earlier). Frontend needs continuous value display, not contracting/expanding badge.

### Frontend rendering implications (Phase 5)

The per-badge IC validation gives the engine empirical justification for HOW each badge renders. Three render treatments:

- **validated** (8 of 13 tiers): full color badge + implied-action verb in tooltip + IC number
- **weak** (2 of 13 tiers): grey badge with asterisk, no implied action
- **decorative** (3 of 13 tiers): plain label OR replaced with continuous numeric display

The continuous-vs-tier finding (OBV + ATR contraction) is a design lesson: where the tier-level IC collapses, render the raw continuous metric instead of a categorical badge. Phase 5 should track which display kind each component uses.

---

## Audit note — migration 080 bridge view (2026-05-19)

**Phase 1 of signal consolidation plan deployed.**

Migration 080 created `atlas.atlas_stock_signal_unified` VIEW deriving legacy
column names from `atlas_stock_state_daily WHERE classifier_version='v2.0-validated'`.
Applied to Supabase DB (shared between local dev and EC2 atlas-os-sl).

### Smoke query results (latest date in view)

| Metric | Value |
|---|---|
| `engine_rows` (atlas_stock_state_daily v2.0-validated) | 273,231 |
| `view_rows` (atlas_stock_signal_unified) | 273,231 |
| Row count parity | PASS |

**is_investable distribution (latest date — 378 stocks):**

| is_investable | count |
|---|---|
| False | 48 |
| True | 330 |

Both buckets non-zero. 87.3% of universe investable per state engine.

**rs_state distribution (latest date — 378 stocks):**

| rs_state | count |
|---|---|
| Average | 163 |
| Laggard | 35 |
| Leader | 36 |
| Strong | 72 |
| Weak | 72 |

All 5 buckets present. Distribution follows expected RS rank bell-curve with
slight rightward skew (Leader+Strong = 108, Laggard+Weak = 107).

**Goal-post check:** `atlas-lab goal-post --rank 1` → `met: true`
V5-RP-TREND alpha_oos=0.2018, hit_rate=0.631, n_recs=20, n_high_confidence=20.
`atlas/trading/lab.py` untouched throughout.

**Unexpected finding:** Migration 071 (`strategy_leaderboard_profile`) was
present in `main` but not yet merged into `feat/atlas-consolidation` worktree.
Copied to worktree to resolve the alembic revision chain. No functional impact —
the DB had already applied it.
