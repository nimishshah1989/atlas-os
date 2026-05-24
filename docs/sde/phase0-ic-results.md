# SDE Phase 0 - Factor IC Results

Generated: 2026-05-20

## Decision: PROCEED to Phase 1 (qualified)

Raw gate: 9 survivors (out-of-sample IC, same sign as train, |IC|>=0.03, |t|>=2.0).
Run: 881 liquid instruments, 6-year window, 19 factors x 3 horizons (63/126/252d).

| Factor | Horizon | Train IC | Train t | Test IC | Test t | N test |
|---|--:|--:|--:|--:|--:|--:|
| vol_63 | 126 | 0.0614 | 12.70 | -0.1358 | -21.16 | 328 |
| vol_63 | 252 | 0.0709 | 14.23 | -0.1342 | -19.42 | 202 |
| atr_pct_14 | 252 | 0.0912 | 19.25 | -0.1232 | -17.54 | 202 |
| atr_pct_14 | 126 | 0.0809 | 18.08 | -0.1176 | -16.40 | 328 |
| vol_21 | 252 | 0.0643 | 15.23 | -0.0971 | -12.55 | 202 |
| vol_21 | 126 | 0.0562 | 13.93 | -0.0946 | -16.44 | 328 |
| vol_63 | 63 | 0.0345 | 7.05 | -0.0926 | -12.20 | 391 |
| prox_52w_high | 126 | 0.0576 | 22.61 | 0.0823 | 11.91 | 328 |
| kurt_63 | 126 | -0.0262 | -13.63 | -0.0789 | -25.03 | 328 |
| atr_pct_14 | 63 | 0.0443 | 9.97 | -0.0743 | -8.85 | 391 |
| kurt_63 | 252 | -0.0083 | -3.77 | -0.0736 | -15.51 | 202 |
| kurt_63 | 63 | -0.0272 | -12.57 | -0.0724 | -22.44 | 391 |
| cmf_20 | 252 | 0.0095 | 4.17 | 0.0659 | 17.34 | 202 |
| vol_21 | 63 | 0.0297 | 7.12 | -0.0637 | -8.85 | 391 |
| prox_52w_high | 63 | 0.0545 | 19.51 | 0.0596 | 7.17 | 391 |
| roc_252 | 252 | 0.0686 | 16.14 | -0.0581 | -13.82 | 202 |
| prox_52w_high | 252 | 0.0538 | 25.32 | 0.0523 | 14.55 | 202 |
| roc_126 | 252 | 0.0977 | 24.85 | -0.0523 | -12.70 | 202 |
| cmf_20 | 126 | 0.0178 | 6.89 | 0.0452 | 10.81 | 328 |
| skew_63 | 63 | 0.0035 | 1.55 | -0.0441 | -11.08 | 391 |
| obv_chg_21 | 63 | -0.0017 | -0.77 | -0.0440 | -10.66 | 391 |
| prox_52w_low | 252 | 0.0835 | 16.01 | -0.0434 | -9.63 | 202 |
| skew_63 | 126 | 0.0229 | 12.64 | -0.0389 | -10.31 | 328 |
| prox_52w_low | 126 | 0.1007 | 18.94 | -0.0377 | -7.04 | 328 |
| mfi_14 | 126 | 0.0228 | 9.75 | -0.0359 | -8.90 | 328 |
| mfi_14 | 63 | 0.0108 | 4.47 | -0.0341 | -6.59 | 391 |
| obv_chg_21 | 126 | 0.0016 | 0.74 | -0.0330 | -8.77 | 328 |
| mfi_14 | 252 | 0.0387 | 15.72 | -0.0288 | -5.33 | 202 |
| vol_ratio_20 | 126 | -0.0053 | -2.51 | 0.0283 | 8.60 | 328 |
| roc_252 | 126 | 0.0984 | 20.91 | -0.0276 | -5.51 | 328 |
| skew_63 | 252 | 0.0320 | 17.02 | -0.0263 | -10.06 | 202 |
| dist_sma_200 | 252 | 0.0866 | 22.41 | -0.0232 | -5.16 | 202 |
| ema_ratio_50 | 63 | 0.0364 | 11.61 | -0.0232 | -3.31 | 391 |
| prox_52w_low | 63 | 0.0876 | 18.68 | -0.0212 | -3.60 | 391 |
| roc_63 | 63 | 0.0499 | 16.04 | -0.0207 | -3.37 | 391 |
| dist_sma_200 | 126 | 0.0886 | 24.40 | 0.0194 | 3.17 | 328 |
| obv_chg_21 | 252 | 0.0190 | 8.79 | -0.0187 | -3.60 | 202 |
| vol_ratio_20 | 252 | -0.0116 | -5.80 | 0.0187 | 4.39 | 202 |
| roc_63 | 126 | 0.0599 | 21.00 | -0.0174 | -3.88 | 328 |
| vol_ratio_20 | 63 | 0.0003 | 0.14 | 0.0172 | 5.51 | 391 |
| rsi_14 | 63 | 0.0195 | 6.82 | -0.0168 | -2.56 | 391 |
| dist_sma_20 | 252 | 0.0315 | 10.86 | 0.0153 | 2.34 | 202 |
| dist_sma_20 | 63 | 0.0119 | 3.99 | -0.0145 | -2.22 | 391 |
| rsi_14 | 252 | 0.0433 | 16.25 | 0.0142 | 2.73 | 202 |
| roc_126 | 126 | 0.0883 | 26.85 | 0.0141 | 2.58 | 328 |
| rsi_3 | 63 | 0.0004 | 0.16 | -0.0127 | -2.66 | 391 |
| cmf_20 | 63 | 0.0170 | 6.92 | 0.0100 | 2.06 | 391 |
| roc_63 | 252 | 0.0888 | 28.82 | -0.0085 | -1.54 | 202 |
| rsi_14 | 126 | 0.0269 | 9.80 | 0.0073 | 1.46 | 328 |
| dist_sma_200 | 63 | 0.0626 | 17.07 | 0.0067 | 1.04 | 391 |
| ema_ratio_50 | 126 | 0.0506 | 17.04 | -0.0056 | -1.11 | 328 |
| rsi_3 | 252 | 0.0101 | 4.24 | 0.0056 | 1.12 | 202 |
| rsi_3 | 126 | 0.0068 | 2.75 | 0.0039 | 0.94 | 328 |
| roc_252 | 63 | 0.0899 | 22.44 | -0.0033 | -0.59 | 391 |
| ema_ratio_50 | 252 | 0.0727 | 23.72 | 0.0021 | 0.40 | 202 |
| roc_126 | 63 | 0.0571 | 16.24 | 0.0019 | 0.34 | 391 |
| dist_sma_20 | 126 | 0.0228 | 7.81 | 0.0009 | 0.17 | 328 |

## Interpretation (analyst read, 2026-05-20)

The raw gate verdict "PROCEED / 9 survivors" must be read with care — the gate
is crude. The honest reading:

**Dominant finding: non-stationarity.** The factors with the largest in-sample
IC — volatility (`vol_63`, `vol_21`, `atr_pct_14`) and medium-term momentum
(`roc_126`, `roc_252`) — *invert sign* out of sample: train IC ≈ +0.06 to +0.09,
test IC ≈ -0.06 to -0.14. In the older era, high-volatility / high-momentum
stocks outperformed cross-sectionally; in the recent ~1.8 years they
underperformed. This reproduces a real, known Indian-market regime shift (the
post-COVID high-beta rally giving way to a 2024-25 quality / low-volatility
rotation) — it is not a bug. The implication: a composite naively fit on
history would be actively wrong today.

**Genuinely stable signals (≈2 factor families of 19):**
- `prox_52w_high` — positive IC in both eras at all three horizons (train
  +0.05 to +0.06, test +0.05 to +0.08). The classic 52-week-high momentum
  effect; robust here.
- `kurt_63` — consistently *negative* IC in both eras (train -0.01 to -0.03,
  test -0.07 to -0.08). Lower return-kurtosis stocks outperform; stable, and
  the magnitude grows out of sample.

**Gate artifacts (false survivors):** `cmf_20` and `obv_chg_21` cleared the
gate but their train IC is ≈0 (`obv_chg_21@63`: train IC -0.0017, t -0.77 —
pure noise). They passed on a sign technicality. The gate needs a minimum
train-IC floor.

**t-stats are inflated** roughly 4-5x by overlapping-window autocorrelation
(as the spec predicted). |t| ≈ 20 is not real significance; read IC magnitude
and train/test sign-consistency, not t.

**Caveats from pre-flight:** `close_adj` coverage 100% (Check 1 PASS); only 14
delisted instruments retained (Check 2 WARN) — a mild survivorship lean that
slightly inflates IC.

**Honest verdict: qualified yellow, not green.** There is a thin, real edge —
but it lives in ~2 stable factors, and the dominant effect in the data is
regime-dependence. This is materially better than v6's IC ≈ 0.009 (nothing),
and worse than the raw "9 survivors" headline suggests. Phase 1, if pursued,
should: (1) build around `prox_52w_high` + `kurt_63`, not the inverting
factors; (2) treat regime-conditioning as first-class; (3) fix the gate
(minimum train-IC, autocorrelation-corrected significance).

**Known minor tech-debt:** factor `pct_change` calls use the deprecated pandas
default `fill_method='pad'`, which forward-fills across the rows nulled by
`mask_extreme_moves`. Effect is negligible at ~0.01% of rows but should be set
to `fill_method=None` in Phase 1.
