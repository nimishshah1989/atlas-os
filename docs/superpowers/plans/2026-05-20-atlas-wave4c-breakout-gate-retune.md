# Atlas v2 Wave 4C — Breakout-Gate IC Re-tune — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the root cause of the Stage-2 collapse — the un-validated breakout gate `theta_base_breakout = 1.000` that blocks 66 trend-qualified stocks — by building and IC-validating the `breakout_ratio` factor and tuning `theta_base_breakout` to the value the IC data supports.

**Architecture:** Implement the deferred `breakout_ratio` factor builder; run it through the existing IC harness to validate it; grid-tune `theta_base_breakout` over 0.90–1.00 against IC; apply the tuned threshold; review the Stage-2A→2B→2C reachability chain; re-classify and verify the Stage-2 cohort and downstream sector/fund spread expand.

**Tech Stack:** Python 3.12, pandas, the Atlas IC harness (`atlas/intelligence/states/ic_harness.py`), Postgres.

**Spec / source of truth:** [docs/audits/2026-05-stage2-threshold-audit.md](../../audits/2026-05-stage2-threshold-audit.md) — the audit that root-caused this. **Read it first.**

**Authorization:** The user explicitly authorized this engine re-tune (the decision-engine spec had fenced the IC-validated engine off; this is the deliberate, separately-validated re-tune the Wave 4A audit recommended).

---

## Cross-cutting acceptance criteria

- **No threshold ships without IC validation.** `theta_base_breakout` is only changed to a value the IC harness output supports — the data sets it, not a guess.
- **Zero synthetic data** — IC runs against real historical panels.
- **Coexistence:** the IC-validated states already in production must not be silently degraded — the re-tune is validated to be neutral-or-better on the composite, not just on Stage-2 count.
- Thresholds live in `atlas.atlas_thresholds` / the threshold store — not hardcoded.

---

## Task 1: Implement the `breakout_ratio` factor builder

**Files:** Modify `atlas/intelligence/states/tune_catalog.py` (the `NotImplementedError` stub); test `tests/intelligence/states/test_tune_catalog.py`.

- [ ] **Step 1: Explore.** Read `tune_catalog.py` — find the `breakout_ratio` stub and how other factor builders in the same file are structured (signature, what panel columns they take, what they return). Read `features.py` for the `max_close_60d` / rolling-max feature if it exists. Report the builder contract.
- [ ] **Step 2: Failing test.** A test that `breakout_ratio` for a panel of known close prices returns `close / rolling_max(close, 60)` per row — hand-compute for a small fixture (e.g. a 5-row series with a known 60-day-window max). Assert the ratio.
- [ ] **Step 3: Run — FAIL.**
- [ ] **Step 4: Implement.** Replace the `NotImplementedError` with the real builder: `breakout_ratio = close / rolling_max(close over the trailing 60 trading days)`. Vectorized pandas (no iterrows — data-engineering rule). Match the sibling factor builders' style.
- [ ] **Step 5: Run — PASS.**
- [ ] **Step 6: Commit** — `feat(states): implement breakout_ratio factor builder`

## Task 2: IC-validate `breakout_ratio`

**Files:** No production code — a validation run + a written result. Output to `docs/audits/`.

- [ ] **Step 1: Run the IC harness** on `breakout_ratio` over the 2023–2026 historical panel (the same harness + horizon used to validate the other state factors — read `ic_harness.py` for the entry point and standard horizon). Record IC, IR, and the IC time series.
- [ ] **Step 2: Write the validation result** to `docs/audits/2026-05-breakout-ratio-ic-validation.md`: the IC/IR numbers, the verdict (validated / weak / inverse), and how it compares to the existing validated state factors (e.g. `theta_rs` at IR 0.74). If `breakout_ratio` is IC-invalid or inverse, STOP — report that the breakout gate should be loosened toward removal rather than re-tuned, and escalate. If validated, proceed to Task 3.
- [ ] **Step 3: Commit** — `docs(audit): breakout_ratio IC validation result`

## Task 3: IC-tune `theta_base_breakout`

**Files:** The threshold store (`atlas.atlas_thresholds` or `atlas/intelligence/states/thresholds.py` — find where `theta_base_breakout` lives). A migration if it is a DB threshold.

- [ ] **Step 1: Grid run.** For `theta_base_breakout` ∈ {0.90, 0.92, 0.94, 0.96, 0.98, 1.00}, compute, on the historical panel: (a) the resulting Stage-2A cohort size, (b) the IC/IR of the *resulting Stage-2 state membership* against forward returns (the state's own predictive power — the state must stay predictive, not just larger). Use the IC harness.
- [ ] **Step 2: Pick the value.** Choose the `theta_base_breakout` that maximizes the Stage-2 state's IR (or, if a plateau, the highest threshold within the plateau — conservative). Document the choice with the grid table. The value must be IC-supported — if every value below 1.00 degrades the state's IR, keep 1.00 and report that the gate is correct after all.
- [ ] **Step 3: Apply the tuned threshold.** Update `theta_base_breakout` in its store — if it is an `atlas_thresholds` row, a migration (`down_revision` = current head — confirm); if it is a code constant, the threshold module. Update its provenance/validation note.
- [ ] **Step 4: Test.** A unit test pinning that the classifier reads the tuned `theta_base_breakout` and that a stock at the boundary classifies as expected.
- [ ] **Step 5: Commit** — `feat(states): IC-tuned theta_base_breakout — <value>`

## Task 4: Stage-2A→2B→2C reachability review

**Files:** `atlas/intelligence/states/classifier.py`; test alongside.

- [ ] **Step 1: Explore.** Read the classifier's Stage-2B and Stage-2C entry logic. Confirm the audit's finding that 2B/2C are reachable ONLY via a prior 2A — i.e. a stock in a confirmed uptrend that was never caught at the 2A breakout day is orphaned in Stage 1.
- [ ] **Step 2: Failing test.** A stock that satisfies the 2B (or 2C) structural conditions but whose `prior_state` is `stage_1` (never passed through 2A) should still be admitted to Stage 2B/2C — assert it is.
- [ ] **Step 3: Run — FAIL** (if the audit's finding holds) — OR, if exploration shows 2B/2C are already independently reachable, mark this task N/A with a one-line note and skip to Task 5.
- [ ] **Step 4: Implement** an "already in Stage 2" admission path: a stock meeting the 2B/2C structural conditions enters 2B/2C regardless of whether it was caught at 2A. Keep the change minimal and within the classifier's existing structure.
- [ ] **Step 5: Run — PASS.**
- [ ] **Step 6: Commit** — `feat(states): admit confirmed uptrends to Stage 2B/2C without a 2A pass`

## Task 5: Re-classify + verify

**Files:** No new code — a re-classification run + verification.

- [ ] **Step 1: Re-run the classifier** over the universe (or the latest date) on EC2 with the Task 3 + Task 4 changes. (Deferred to the controller / EC2 — Mac has no DB.)
- [ ] **Step 2: Verify.** The Stage-2A cohort is materially larger than 9 and the 2B/2C cohorts are non-empty; the downstream `atlas_sector_signal_unified` shows strong sectors clearing the Wave-4A absolute floor and labelling `Overweight`; the fund recommendation spread widens. Record before/after numbers.
- [ ] **Step 3: Commit** — `docs(audit): post-retune Stage-2 cohort + downstream verification`

---

## Self-review

**Spec coverage:** breakout_ratio builder → Task 1; IC validation → Task 2; theta_base_breakout tune → Task 3; reachability → Task 4; re-classify + verify → Task 5. All audit recommendations covered.

**Placeholder scan:** Tasks 2/3/5 are validation/compute tasks, not pure-code TDD — their steps are concrete (run the harness, record numbers, write the result). The IC-tuned `theta_base_breakout` value is deliberately not pre-stated — it must come from the Task 3 grid. That is correct, not a placeholder.

**Risk gate:** Task 2 has an explicit STOP — if `breakout_ratio` is IC-invalid, the plan halts and escalates rather than shipping an unvalidated re-tune.
