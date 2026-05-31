# 0002 — Standardize stock RS to relative form; redefine gold RS as direct stock-vs-gold

- **Status:** Accepted (2026-05-31)
- **Context chunk:** v6 M3 (Relative Strength baselines + standardization)

## Context

The roadmap and `CONTEXT.md` call for all RS to use the **relative (price-ratio)
form** `(1+r_instrument)/(1+r_benchmark) − 1`. Audit of the code found:

- `indices.py`, `sectors.py` (market-relative vs Nifty 500): already relative ✓
- `stocks.py` tier RS via `add_relative_strength` (`benchmarks.py`): **excess
  form** `r_stock − r_benchmark` ✗ — its docstring even says *"ratio variant
  lives in M3 if needed."*
- `rs_*_tier_gold`: derived as `rs_*_tier / (1+r_gold)` — i.e. the tier *excess*
  return deflated by gold. This only yields a distinct metric **because** the
  tier RS is in excess form.

Switching tier RS to relative form has a non-obvious consequence for gold: under
the ratio form a common numéraire cancels —
`[(1+r_s)/(1+r_g)] / [(1+r_b)/(1+r_g)] − 1 = (1+r_s)/(1+r_b) − 1` — so the old
gold metric becomes degenerate (identical to the non-gold RS). The only
meaningful gold metric in relative form is the **direct** stock-vs-gold ratio.

## Decision

1. `add_relative_strength`: compute `rs_{w}_tier = (1+ret)/(1+ret_benchmark) − 1`
   for every window (now including `1d` and `24m`).
2. Redefine the gold variant as **direct stock-vs-gold relative strength**:
   `rs_{w}_gold = (1+ret)/(1+ret_gold) − 1`, extended to all 7 windows
   (previously the deflated-excess form at 1w/1m/3m only).
3. This is a methodology refinement of the *display* RS metric. It does **not**
   touch `rs_residual` (the regression-based predictive RS used in scoring).

## Consequences

- Raw `rs_*_tier` and `rs_*_gold` **display values change** (magnitude differs:
  `(1+a)/(1+b)−1` vs `a−b`; and gold's meaning shifts from "tier-excess in gold"
  to "stock vs gold").
- **No decision impact — proven invariant.** Within a `(date, tier)` group the
  benchmark return is constant, so both forms are monotonic in `r_stock` →
  within-tier percentiles, `rs_state`, scoring, and signal calls are unchanged.
  The sign is also preserved (`(1+a)/(1+b)−1 > 0 ⇔ a > b`), so the sign-based
  breadth metrics are unaffected by the formula change (they shift only from the
  Nifty-50 anchor change — see [0001](0001-large-tier-rs-anchor-nifty50.md)).
- US/global surfaces (`us_stocks.py`, `global_pipeline.py`) remain in excess
  form for now; their standardization rides with M4 (the Markets RS grid).
