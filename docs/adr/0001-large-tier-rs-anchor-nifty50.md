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
- **No persisted breadth or decision column changes** (corrected after prod
  introspection, 2026-05-31):
  - `pct_stocks_rs_positive` is **not persisted anywhere** — it is computed in
    `regime._compute_strength_breadth` but absent from regime `METRICS_COLUMNS`,
    and confirmed absent from every prod table/view/matview. It is
    computed-and-discarded, so there is nothing to backfill.
  - `regime_state` / `deployment_multiplier` classify off **price breadth**
    (`pct_above_ema_50`) + VIX + Nifty500 trend — not RS — so they are
    unaffected by the anchor.
  - `participation_rs` (sectors) is `rs_state`-derived (`fix(health-audit)`
    redefined it from the old `rs_1m_tier > 0` proxy), and `rs_state` is
    invariant under the anchor — so it is unchanged.
  - Net: the only values that change are the **display** RS columns
    (`rs_*_tier`, `rs_*_tier_gold`) and the new 1d/24m + sector/index columns.

## Decision

1. Set `TIER_BENCHMARK["Large"] = "NIFTY50"`. Nifty 100 remains in use **only**
   for the Calls Performance anchor benchmark.
2. Recompute only the genuinely-affected columns across ~2 years of history,
   vectorized: `rs_*_tier`, `rs_*_tier_gold` (stock display RS), plus the new
   1d/24m and sector/index columns added in M3. **No breadth/regime backfill** —
   `pct_stocks_rs_positive` isn't persisted and `participation_rs` is invariant.
3. **Do not** recompute `rs_pctile_*`, `rs_state`, scorecard scoring, or signal
   calls — proven invariant above. Rerunning them would be wasted cost and
   needless risk to historical decision records.

## Consequences

- Large-tier RS display values now match the locked methodology; the Markets /
  Sectors surfaces show Nifty-50-relative strength for Large-caps.
- **No retroactive change to any breadth/regime timeline**: `pct_stocks_rs_positive`
  isn't persisted, `participation_rs` is `rs_state`-derived (invariant), and
  `regime_state` keys off price breadth — so the India Pulse breadth/regime
  history is byte-for-byte unchanged.
- Signal calls, scorecard verdicts, and within-tier ranks are byte-for-byte
  unchanged, so no decision/audit history is rewritten.
- If the invariance argument is ever broken (e.g. a future consumer thresholds a
  raw `rs_*_tier` value, or cross-tier percentiles are introduced), this ADR's
  "skip the scorecard recompute" conclusion must be revisited.
