# Atlas v4 — Backend step goals + the IC calibration spec

Each backend step has ONE goal and a falsifiable gate. The IC calibration is spec'd in
full because it is the keystone — every altitude's "conviction" is IC-driven (D15).

## Phase 1 — finish the stock atom → A

| Step | GOAL | GATE |
|---|---|---|
| 1a Data coverage | every lens's input at real full coverage on ~2,093, PIT-capable, no synthetic/stub | scorecard inputs → A−/A |
| 1b Final pass + lock | derive last inputs (sector-RS, P/B), fill residual gaps, freeze input tables | 0 nulls where a real source exists; tables locked |
| 1c Loop C wiring | every scorer reads the PIT historical source (not the snapshot); composite consumes DB weights; forward returns are truly forward | the 2 blockers proven fixed |
| 1d Journal rebuild | genuine within-instrument time-variance, all 6 lenses, 2019→now, no lookahead | validate_loopC C1–C5 |
| 1e **IC calibration** | learn per-lens weights from forward-return predictive power, walk-forward validated; composite = IC-weighted | OOS IC ≥ floor; weights persisted + consumed (C6–C7) |

## Phases 2–4 (each reuses the same roll-up + IC machinery)

| Phase | GOAL | GATE |
|---|---|---|
| 2 Sector roll-up | free-float-weighted 6-lens + breadth + dispersion + rotation + the momentum×conviction 2×2; **sector IC** | `--check B` (sector) + sector OOS IC ≥ floor |
| 3 ETF + Index | holdings/constituent-weighted vectors + tracking quality; their IC | `--check B` (ETF/index coverage) |
| 4 Mutual funds | MF tables + holdings-weighted fund lens + **active-movement (MoM holdings)** + ranking + fund IC | fund coverage + ranking validated + fund OOS IC |

Then front-end (entire backend A first).

---

## The IC calibration — goal + the loop

### What IC (Information Coefficient) is
For one lens (say Flow) on one date, across all ~2,000 stocks: the **rank-correlation between
the lens score and the stock's FORWARD return** (e.g. the return over the next 1 / 3 / 6 months).
- IC ≈ +0.05 → weak-but-real predictive power; ≈ 0 → none; negative → inverse.
- In equity quant, |IC| 0.03–0.05 is meaningful, 0.10+ is strong. Floor = **0.03**.

### The goal
**Stop hand-setting the lens weights.** Let the data say which lenses actually predicted forward
returns, weight the composite by that, and PROVE it out-of-sample. Result: a conviction score
grounded in realized predictive power, not opinion. The same logic runs at every altitude (the
"return" is the stock's, the sector's, or the fund's forward return).

### The loop (walk-forward, no lookahead)
Inputs: the rebuilt PIT journal (each date D → every stock's 6-lens vector) + true forward returns.
Horizons h ∈ {21, 63, 126} trading days (1m/3m/6m). Metric: cross-sectional **Spearman rank-IC**.

1. **Forward returns** — for each stock at D, return D→D+h (TRUE forward, shifted h NSE sessions
   ahead — NOT the trailing `ret_*` columns; that was the confirmed bug to fix in 1c).
2. **Per-date IC** — on each D, for each lens × horizon: rank-corr(lens score on D, forward return).
   Require ≥5 stocks in the cross-section (else skip the date).
3. **Train window** — average per-date IC over a rolling TRAIN window (e.g. 252 sessions) → each
   lens's mean IC + its sign-stability.
4. **IC → weights** — weight ∝ IC, regularized; drop any lens below the 0.03 floor or whose IC sign
   flips across folds (unreliable). Normalise to sum 1.
5. **Walk forward (out-of-sample)** — apply the TRAIN weights to score the composite on the NEXT
   unseen window; measure whether the IC-weighted composite predicts forward returns **better than
   equal-weight** on that held-out window. **Purge + embargo** a gap of h sessions between train and
   test so train labels never overlap the test period (no leakage).
6. **Slide** the train/test windows across all of history → dozens of OOS folds.
7. **Calibrated weights** = the stable set across folds → written to `atlas_thresholds.lens_weight_*`
   + provenance to `atlas_signal_ic` / `atlas_signal_weights`; the composite consumes them (after
   the 1c blocker fix). **Conviction is now "what actually predicted returns."**

### Two loops
- **Build-time (bootstrap):** run the walk-forward over all history once → the initial calibrated
  weights the engine ships with.
- **Runtime (nightly/weekly):** re-measure IC on the latest window, re-propose weights, run the
  walk-forward gate, and **adopt the new set only if it beats the incumbent out-of-sample**, else
  keep current (auto-revert guardrail — reuses Atlas's existing weight-set IC drift machinery).

### Per-altitude
The identical loop runs at each altitude, calibrating its OWN weights, because the lenses that
predict returns differ by altitude:
- **Stock IC** — lens score vs forward stock return.
- **Sector IC** — sector lens vector vs forward sector (free-float index) return.
- **Fund IC** — fund lens vector vs forward fund NAV return.

### Honest caveats (so we don't over-trust it)
- Depth bounds power: ~7.5y (2019→) gives enough non-overlapping folds for 1m/3m, fewer for 6m.
- Early years (2019–20) have thinner fundamental coverage → record n per date; don't promote a
  weight learned on a shrunken, biased cross-section.
- IC is modest by nature; the win is a *defensible, learned, drift-monitored* weighting, not a
  magic number.
