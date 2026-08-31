# Dual composite: hand-set weights + IC-calibrated weights

Status: **design, awaiting FM approval** · 2026-08-25

## What the FM asked for

Two composites, both computed in the nightly run and stored in the database:

1. **Current weights** — hand-set, what the FM uses today (technical 0.90 / flow 0.10)
2. **IC-driven weights** — recalibrated periodically from the measured information
   coefficient

Nothing computed live. The board reads stored columns; the machinery cost stays in the
nightly window where it already is.

## Why this is safe, where auto-tuning was not

The signal-validation spec explicitly REJECTED auto-demoting lens weights on IC decay:
*"a data outage looks identical to signal decay."* That objection was about replacing the
live score.

This is different, and the difference is the whole design: **the IC-calibrated composite
is a second opinion, never the primary.** If the calibration goes wrong — a broken feed
reads as a dead lens — the FM's score is untouched and the divergence between the two
columns is itself the alarm. The failure mode is visible instead of silent.

## The evidence this exists to act on

Measured 2026-08-25, large-cap, 63-day rank-IC:

| lens | current weight | 2019–May 24 | Jun 24–now |
|---|---:|---:|---:|
| technical | **0.90** | +0.037 | **−0.073** |
| flow | **0.10** | +0.025 | **−0.048** |
| policy | **0.00** | **+0.064** | **+0.038** |
| fundamental | 0.00 | −0.036 | +0.016 |
| valuation | 0.00 | −0.024 | −0.010 |
| catalyst | 0.00 | −0.018 | −0.017 |

100% of the weight is on the two lenses that inverted; 0% on the only one that works in
both regimes. Tested across all 24 (cohort × horizon × era) cells, a policy-led blend
beats the current one in 20.

## Weight derivation — five judgment calls

**1. Negative-IC lenses get weight ZERO, never negative.**
Catalyst is reliably inverted (−0.018 both eras). Inverting it would score a genuine
signal — and would also be a different product, a short book. Zero it and say so.

**2. Weights are IC-proportional over positive lenses, normalised to 1.0.**
`w_i = max(IC_i, 0) / Σ max(IC_j, 0)`. No optimiser, no fitting. An optimiser on 7
parameters and ~11 independent observations would fit noise, and its output would be
unexplainable — which fails the glass-box rule harder than a bad weight would.

**3. A single lens is capped at 0.60.**
Uncapped, today's ICs give policy ~0.55 and rising. **Policy has 9 distinct values across
2,093 stocks** — it is a sector score broadcast to constituents. At weight 1.0 every
stock in Capital Goods scores identically and Atlas stops ranking stocks. The cap keeps
at least one instrument-level lens breaking ties inside a sector.

**4. Recalibrate WEEKLY, not nightly, and smooth 20/80.**
The IC window is two years; it barely moves day to day, so nightly recalibration adds
churn without information. New weights blend 20% new / 80% previous, so no single month
can swing the book. Both numbers live in `atlas_thresholds`.

**5. Calibrate from the rolling 2-year pooled IC at the 63-day horizon.**
Not the full history — the point is to adapt to the current regime. Not per-cohort — one
weight set keeps the composite comparable across cap bands, and per-cohort weights would
mean a stock's score changes when its market cap crosses a boundary.

## Guards — this fails loud or not at all

- **A lens with fewer than 250 IC dates keeps its previous weight.** Thin evidence is not
  evidence.
- **If every lens scores IC ≤ 0, the weights do not change at all** and the run reports
  it. That is the data-outage signature, and it must not silently zero the book.
- **Every recalibration is journalled** — old weights, new weights, the ICs behind them,
  the date. `/admin` renders the before/after, per the explainer rule: no number changes
  without the math being visible.
- **The FM's weights are never written by this process.** Only `lens_weight_ic_*` rows move.

## Shape

```
atlas_thresholds
  lens_weight_<lens>          hand-set, FM-owned, unchanged by this feature
  lens_weight_ic_<lens>       IC-calibrated, written weekly
  ic_weight_smoothing         0.20
  ic_weight_max_single        0.60
  ic_weight_min_dates         250

atlas_lens_scores_daily
  composite, conviction_tier            (unchanged — the FM's score)
  composite_ic, conviction_tier_ic      (new — the calibrated score)

atlas_ic_weight_journal (new)
  as_of_date · lens · weight_before · weight_after · mean_ic · n_dates · computed_at
```

`compute_composite()` already takes weights as a parameter (`th['lens_weights']`), and
`nest_thresholds()` already builds that shape from flat DB keys. The nightly pipeline
calls it a second time with the IC weight map. No new maths.

## Board

Both scores visible side by side on the stock page, with the weights that produced each.
The FM's score stays the headline; the IC score sits beside it. Where they disagree
materially, that is the interesting cell — surface it, do not average them.

## Out of scope

Switching which composite is primary (a later decision, once the second has a track
record), per-cohort weights, an optimiser, and any change to how a lens itself is scored.
