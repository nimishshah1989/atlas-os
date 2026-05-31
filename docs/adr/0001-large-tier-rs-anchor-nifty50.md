# 0001 — Correct the Large-tier RS anchor from Nifty 100 to Nifty 50

- **Status:** Accepted (2026-05-31)
- **Context chunk:** v6 M3 (Relative Strength baselines + standardization)

## Context

`CONTEXT.md` ("Baselines — 9 canonical") locks the **Large-tier RS anchor as
Nifty 50**, and explicitly reserves **Nifty 100** as an *"Alternate Large anchor
(Calls Performance only)."* The compute code drifted from this: `benchmarks.py`
`TIER_BENCHMARK` maps `"Large" → "NIFTY100"`, so daily Large-tier relative
strength has been computed against Nifty 100, not Nifty 50.

The user re-asserted the lock directly: in India, "Nifty" means **Nifty 50**, and
it is the mandatory Large-tier anchor. So this is a code-vs-methodology
conformance fix, not a methodology change.

We analysed the blast radius before deciding scope:

- Raw `rs_*_tier` (and the gold-numéraire derivative `rs_*_tier_gold`) for
  Large-tier instruments **change** (different benchmark return in the
  denominator of `(1+r_stock)/(1+r_bench)−1`).
- **Within-tier percentiles are invariant.** `add_within_tier_percentiles`
  ranks `rs_*_tier` within `(date, tier)`. On a given date the tier benchmark
  return is a constant across all stocks in the tier, and
  `(1+r_stock)/(1+r_bench)−1` is monotonic in `r_stock`, so the dense rank — and
  therefore `rs_pctile_*`, `rs_state`, stage-1 qualification, scorecard scoring,
  and **signal calls** — does **not** change.
- **Two sign-based breadth metrics do change**, because they threshold the raw
  value at zero (not the percentile): `pct_stocks_rs_positive` (regime breadth,
  `regime.py`) and `participation_rs` (sector participation, `sectors.py`). A
  Large-cap can be RS-positive vs Nifty 100 but negative vs Nifty 50, so these
  fractions shift for the Large-cap contribution across history.

## Decision

1. Set `TIER_BENCHMARK["Large"] = "NIFTY50"`. Nifty 100 remains in use **only**
   for the Calls Performance anchor benchmark.
2. Recompute only the genuinely-affected columns across ~2 years of history,
   vectorized: `rs_*_tier`, `rs_*_tier_gold`, `pct_stocks_rs_positive`,
   `participation_rs`.
3. **Do not** recompute `rs_pctile_*`, `rs_state`, scorecard scoring, or signal
   calls — proven invariant above. Rerunning them would be wasted cost and
   needless risk to historical decision records.

## Consequences

- Large-tier RS display values now match the locked methodology; the Markets /
  Sectors / India Pulse surfaces show Nifty-50-relative strength for Large-caps.
- Regime breadth and sector-participation **history** shift to corrected values
  (a visible, retroactive change to the India Pulse breadth timeline). This is
  intended — the prior values were computed against the wrong anchor.
- Signal calls, scorecard verdicts, and within-tier ranks are byte-for-byte
  unchanged, so no decision/audit history is rewritten.
- If the invariance argument is ever broken (e.g. a future consumer thresholds a
  raw `rs_*_tier` value, or cross-tier percentiles are introduced), this ADR's
  "skip the scorecard recompute" conclusion must be revisited.
