# ML Predictive Lens — Proof-of-Value Spike

**Date:** 2026-07-22
**Status:** approved design, pre-implementation
**Owner:** FM sign-off on the go/no-go bar

## One question

Does a machine-learned cross-sectional rank over Atlas's **existing lens features**
beat the incumbent **linear composite**, out-of-sample, **net of costs**?

If yes → we productionize it as a predictive lens + a model-vs-composite disagreement
view. If no → the linear composite is near its ceiling; ~1 week spent, and knowing that
is itself worth the spend.

This is an **offline research spike**. No qlib dependency, no new tables, no pipeline
wiring, no frontend. One self-contained script + one report. Real `atlas_foundation`
data only (rule #0).

## Data

- **Features (X):** from `atlas_foundation.atlas_lens_scores_daily`, per instrument per
  day, 2019-01-01 → present (~1,876 dates, ~2,090 names). The 6 lens scores
  (`technical, fundamental, valuation, catalyst, flow, policy`) + the ~25 sub-components
  (`tech_*, fund_*, val_*, cat_*, flow_*, policy_tailwind, smart_money_score,
  degradation_score`).
  - **Excluded from X:** `composite` and its derivatives (`conviction_tier`,
    `valuation_zone`, `valuation_multiplier`), plus bookkeeping cols
    (`risk_flags, evidence, lenses_active, coverage_factor, compute_run_id,
    computed_at`). The composite is the baseline, not an input.
- **Label (y):** 63-trading-day forward return from `ohlcv_stock`, converted to a
  **cross-sectional rank within each date**. We forecast *relative* selection, not
  market beta.
- **Universe:** liquidity-filtered investable set (median ADV threshold so decile trades
  are fillable) — roughly Nifty-500-grade names, excluding the illiquid tail.

## Baseline

The `composite` column's own cross-sectional rank, same universe and dates. This is the
incumbent every model result is measured against.

## Model

**LightGBM ranker** — standard for tabular factor ML: captures the non-linear
interactions a linear composite cannot, and yields **SHAP per-name attribution** for
free (preserves the glass-box promise — every prediction gets a reason).

Intermediate rung: also fit a **regularized linear model** (ridge/elastic-net) as a
sanity floor. If LightGBM doesn't beat ridge, the non-linearity isn't earning its keep.

## Validation (where credibility lives)

- **Strict walk-forward.** Train 2019→t, test the following year, roll forward. No
  shuffling, no random splits.
- **63-day purge/embargo gap** between train and test. Overlapping forward-return labels
  leak across the boundary — this is the #1 factor-ML mistake. Non-negotiable.
- Metrics reported **per regime** (`atlas_market_regime_daily`) and per test-year — is
  the edge robust, or one lucky bull run?

### Lookahead-leakage gate

The 2019 backfill must be **point-in-time**. If `val_*`/`fund_*` were computed with
later-restated financials, results are inflated by lookahead.

- (a) Confirm the backfill is PIT-clean (check how the lens backfill sourced
  fundamentals).
- (b) Run a **technical-only variant** (`tech_*`, `flow_*` — price/volume-derived,
  inherently PIT) as a leakage-proof cross-check. If both the full and technical-only
  variants show edge, we trust it. If only the full variant does, suspect leakage in the
  fundamental features.

## Go/no-go scorecard

Reported model-vs-composite:

1. Out-of-sample mean **rank-IC** (Spearman) and **IC-IR** (mean/std — the t-stat).
2. **Top-minus-bottom decile spread** of realized 63d returns, annualized, **net of
   round-trip Indian costs** (STT + brokerage + a conservative impact bps).
3. Decile **turnover** (the cost driver).
4. Robustness across regimes / test-years.

**Pass** = model materially beats composite on rank-IC **and** net-of-cost decile spread
**and** the edge is not concentrated in a single regime. Concrete floor (FM may adjust):
mean rank-IC uplift ≥ +0.02 absolute with higher IC-IR, positive net-of-cost spread
exceeding the composite's, in ≥3 of 4 regimes.

**Fail** = the linear composite is at/near its ceiling. Stop; no productionization.

## Deliverable

- One self-contained script under `scripts/research/` (not wired to prod, touches no
  board table).
- A one-page report: IC table (model vs composite vs ridge), decile-spread chart, SHAP
  feature importances, regime/year breakdown, and sample **disagreement** names (where
  model and composite most diverge — the alpha-or-bug signal).

## Explicit non-goals (YAGNI — deferred until the signal is proven)

qlib dependency · production pipeline · new tables · frontend · portfolio construction ·
execution scheduling · regime-conditioned weighting. None of these are built unless the
spike passes.
