ultracode

# AUTONOMOUS LOOP A — instrument-level data COMPLETE, CORRECT, and HISTORICAL

**FIRST read `scripts/loops/GUARDRAILS.md` and obey it absolutely.** Branch `feat/v4-six-lens`.

## THE GATE (this is your only definition of done — do NOT weaken or edit it)
`python scripts/foundation/validate_lenses.py --check A` must exit 0. It asserts on the
REAL produced data (not unit tests). You may NOT modify `validate_lenses.py` to pass.
Also: `pytest atlas/lenses` stays green. Commit/push per GUARDRAILS; STOP only when both pass.

## Why this loop exists (a real bug the last build's self-tests missed)
The engine scored only 750/2000 stocks, on a single date, and the **catalyst lens returned
0 for names with hundreds of filings** (unit tests passed on synthetic data while the real
`lens_filings` never flowed through). Fix the integration, not the unit tests.

## Tasks
1. **Fix CATALYST (top priority).** `foundation_staging.lens_filings` has ~930K rows / 2,002
   instruments, yet ~all top names score catalyst=0. Debug the path end-to-end: the adapter
   query (`atlas/lenses/data/adapters.py::load_catalyst_data`), the instrument_id join, the
   filing category/keyword/date-lookback logic in `compute/catalyst.py`. Prove the fix on a
   real name with ≥500 filings → catalyst>0 with sensible evidence. (Gate assertion #2.)
2. **Fix/review FLOW.** Currently avg 12.2, near-flat. Ensure it actually reads
   `lens_insider` / `lens_shareholding` / `lens_bulk_deals` and produces a real distribution. (Gate #3.)
3. **Score the FULL universe.** Switch the pipeline universe from `atlas_universe_stocks` (750)
   to `foundation_staging.instrument_master` stocks (~2,000). The feed data already covers ~2,000. (Gate #1.)
4. **Compute the HISTORICAL journal.** Run the pipeline point-in-time across history so
   `atlas_lens_scores_daily` has ≥250 dates per instrument (lens vector *as it would have been*
   each day): technical from `technical_daily` (25y), fundamentals as-of each quarter, valuation
   as-of, etc. This is what makes IC calibratable. (Gate #5.) Chunked + resumable (≤6 workers).
5. **Calibrate IC weights** on the journal (walk-forward), write to `atlas_thresholds`. Reuse
   the existing `atlas_signal_ic` / `atlas_signal_weights` machinery.

## Accuracy discipline (GUARDRAILS §2 — enforce concretely)
Before each commit: run `validate_lenses.py --check A`, run `pytest`, and spot-check 2 real
names per fixed lens against the raw feed (e.g. a fundamental vs the XBRL figure; a catalyst
vs the actual filing). Never claim green you haven't proven by the gate.
