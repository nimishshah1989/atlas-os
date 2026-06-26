ultracode

# AUTONOMOUS LOOP 2 — THE SIX-LENS CALCULATION ENGINE

**FIRST read `scripts/loops/GUARDRAILS.md` and obey it absolutely** — adversarial review +
accuracy-vs-Theta before every commit, push to `feat/v4-six-lens` for phone review, keep `SUMMARY.md` current.

You are running unattended. GOAL, then STOP. Do not deploy, do not merge to main,
do not switch any production surface. Work only on branch `feat/v4-six-lens`.
DEPENDS ON LOOP 1 (the feeds). If a feed is missing, compute the lenses that have data
and renormalise — never block; record what's missing.

## Read first (the locked plan)
- docs/atlas-v4-blueprint.md, docs/atlas-six-lens-data-spec.md, CLAUDE.md, CONTEXT.md
- Study Theta's PURE scorers to PORT (do not rewrite logic):
  /home/ubuntu/jip-india/india_alpha/signals/*.py (compute_* functions),
  /home/ubuntu/jip-india/india_alpha/processing/gem_scorer.py (composite math).

## GOAL (definition of done)
The 6-lens vector + composite + conviction + fractal roll-up is computed for every
instrument into `atlas.atlas_lens_scores_daily`, all scorer/composite unit tests pass,
and the composite weights are IC-calibrated on the 25y history (walk-forward IC ≥ floor).
Stop when the test suite + a coverage check are green.

## Tasks (test-gated; modulith — a NEW bounded context `atlas/lenses/`)
1. **Open the gate**: invoke the project planning skill first (so atlas/** edits are allowed) —
   try `/plan-eng-review` (or `/grill-with-docs` or `/tdd`). This is required by the PreToolUse hook.
2. **Scaffold** `atlas/lenses/` (compute/ pure scorers · data/ adapters · llm/ for the 2 Claude
   touchpoints). Migration for `atlas.atlas_lens_scores_daily` (instrument_id, date, asset_class,
   the 6 lens scores, every subcomponent, composite, conviction_tier, risk_flags jsonb, evidence refs).
   Threshold rows in `atlas_thresholds` for every weight/breakpoint (NO hardcoded constants).
3. **Port the 6 scorers as PURE functions + unit tests** (de-duped per the council — each raw
   metric counted once; quality+op-leverage MERGED into Fundamental; Valuation = neutral descriptor):
   - Technical  ← foundation_staging.technical_daily (+ derive ATR/BB contraction, volume)
   - Fundamental ← tv_metrics (levels) + foundation_staging.financials_quarterly (trends)
   - Valuation  ← tv_metrics (+ cross-universe sector-median PE)
   - Catalyst   ← atlas.lens_filings (rules; LLM-deepen top filings, budget-capped)
   - Flow       ← atlas.lens_insider/shareholding/bulk_deals
   - Policy     ← policy registry
   - Risk flags ← derived (auditor/CFO/downgrade · pledge spike · solvency)
4. **Composite + fractal roll-up** + golden-case tests: subcomponents→lens→composite
   (renormalise over lenses-with-data; convergence on orthogonal agreement) → conviction tier;
   roll up the same vector to sector (cap-weight + breadth + dispersion), ETF/fund
   (holdings-weight + active tilt), index (constituents). EVIDENCE-LINKED: store each score's
   contributing events + point contributions.
5. **Compute** the vectors for all instruments → atlas_lens_scores_daily.
6. **IC calibration**: backfill a point-in-time journal from the 25y history (lens vector + the
   forward return that followed), measure IC per signal/lens, set weights walk-forward, write to
   atlas_thresholds. Reuse the existing atlas_signal_ic / atlas_signal_weights machinery.

## GATE (stop condition)
`pytest` for atlas/lenses passes; atlas_lens_scores_daily covers all instruments with data;
walk-forward IC ≥ the per-tenure floors in CONTEXT.md. Then commit and STOP. Log a summary:
test results, instrument coverage, top signals by IC.

## Rules
- Strict SUPERSET of current Atlas — preserve sectors(22)+rollup, drift, regime, conviction,
  RS/breadth, ETF/fund scorecards, calls/ledger (see blueprint §5). Lose nothing.
- Branch `feat/v4-six-lens` only. No deploy/main/switch. Thresholds-in-DB. Decimal. Tz-aware.
  File-size limits. Minimal code (ponytail). Adversarially verify before claiming green.
