# Atlas v2 Wave 4B — Information Architecture Rework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Build Wave 4A before this plan — Task 6 (methodology page) describes the 4A-corrected classifiers.

**Goal:** Re-navigate Atlas v2 around the decision flow (6-section nav), give the Policy a first-class editable surface, add Setup pages, and rewrite the methodology + health pages.

**Architecture:** A new flow-ordered top nav (TODAY/RESEARCH/PORTFOLIOS/SETUP/REFERENCE/ADMIN); the Intelligence section dissolves. A new editable `PolicyEditor` under `/setup/policy` writing to `atlas_portfolio_policy` via an API route with `validate_policy` on save. Setup routes for the editor, portfolio creation, and an onboarding landing. Methodology + health pages rewritten.

**Tech Stack:** Next.js App Router, Tailwind v4, Vitest+RTL; Postgres via the existing query layer.

**Spec:** [2026-05-20-atlas-wave4b-information-architecture-design.md](../specs/2026-05-20-atlas-wave4b-information-architecture-design.md)

---

## Cross-cutting acceptance criteria (every page task)

C1 cross-linked (every ticker/sector/fund/ETF/state token a link) · C2 consistent components · C3 every element tooltipped · C4 dense not overwhelming · C5 zero synthetic data (honest empty states) · C6 formulas tested · C7 logic checks. A task touching a page is not done until its slice of C1–C7 is met.

---

## File structure

- Modify: the top-nav component — find it under `frontend/src/components/` (a `Nav`/`Header`/`TopNav`) — change section config to the 6 flow-ordered sections.
- Modify: route grouping — daily brief → TODAY, signal-validation/IC → ADMIN; remove the Intelligence section entry.
- Create: `frontend/src/app/setup/page.tsx` (onboarding landing), `frontend/src/app/setup/policy/page.tsx` (policy editor), `frontend/src/app/setup/new-portfolio/page.tsx` (portfolio creation).
- Create: `frontend/src/components/setup/PolicyEditor.tsx` (editable, ≤350 LOC).
- Create: `frontend/src/app/api/policy/route.ts` (the policy save path).
- Create: `frontend/src/lib/queries/policy-write.ts` (if a query-layer helper is cleaner than inline route logic).
- Modify: the methodology page + the health page (find them — `frontend/src/app/methodology/` / `frontend/src/app/health/` or under reference).

---

## Task 1: The 6-section flow-ordered nav

**Files:** Modify the top-nav component + its section config; test alongside it.

- [ ] **Step 1: Explore.** Find the nav component and how it declares sections/links. Report the file + current structure.
- [ ] **Step 2: Failing test.** Assert the nav renders 6 sections — TODAY, RESEARCH, PORTFOLIOS, SETUP, REFERENCE, ADMIN — and that there is NO "Intelligence" section.
- [ ] **Step 3: Run — FAIL.**
- [ ] **Step 4: Implement.** Rewrite the nav section config: TODAY (`/`, daily brief), RESEARCH (sectors, stocks, ETFs, funds, global, US), PORTFOLIOS (portfolios, strategy lab), SETUP (`/setup`, `/setup/policy`, `/setup/new-portfolio`), REFERENCE (methodology, health, glossary), ADMIN (thresholds, composite-proposals, signal-validation/IC, data-validator). Keep existing route URLs; only the nav grouping changes. Every nav link must resolve to a real route.
- [ ] **Step 5: Run — PASS.** Build (`cd frontend && npm run build` — confirm `✓ Compiled successfully`).
- [ ] **Step 6: Commit** — `feat(nav): 6-section flow-ordered navigation`.

## Task 2: Dissolve the Intelligence section

**Files:** Modify the routes/links previously under Intelligence.

- [ ] **Step 1: Explore.** List every page currently under the Intelligence section. Classify each: daily-brief-like → TODAY; signal-validation/IC/operator → ADMIN.
- [ ] **Step 2: Failing test.** Assert the daily brief is reachable from TODAY and the IC/validation pages from ADMIN; no route 404s.
- [ ] **Step 3: Run — FAIL.**
- [ ] **Step 4: Implement.** Re-home the pages: update their nav section, add any needed in-page links. Do NOT delete the pages — only re-section them. If the daily brief was its own route, surface it from the TODAY/regime page (a link or an embedded panel). Verify no orphaned routes.
- [ ] **Step 5: Run — PASS.** Build.
- [ ] **Step 6: Commit** — `feat(nav): dissolve Intelligence section — brief to TODAY, IC to ADMIN`.

## Task 3: PolicyEditor component (editable)

**Files:** Create `frontend/src/components/setup/PolicyEditor.tsx`, test alongside.

The existing read-only `PolicyPanel.tsx` (Wave 2) renders the effective policy. `PolicyEditor` is the editable twin: every Policy field is an input; per-portfolio mode shows inherited-vs-overridden with a control to override or revert.

- [ ] **Step 1: Failing test.** `PolicyEditor` given a fixture effective-policy renders an editable control for every Policy field grouped (Deployment/Concentration/Entry/Exit/Instrument/Benchmark/Cadence); each field has a `MetricTooltip` (C3); in per-portfolio mode each field shows an inherited/overridden marker and an override/revert control; changing a value and submitting calls the supplied `onSave` with the changed field set.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement `PolicyEditor.tsx`.** Reuse the field grouping + tooltips + the `stage-labels.ts` / `formatPct` helpers from the QA-fix pass. Numeric fields → number inputs; `buy_states` → a multi-select of stage labels; booleans → toggles; `instrument_universe`/`rebalance_cadence` → selects. Per-portfolio mode: a field left "inherited" sends nothing; an overridden field sends its value; a "revert to inherited" control clears the override. The component is presentational — it calls `onSave(changedFields)`; persistence is Task 4.
- [ ] **Step 4: Run — PASS.** Build.
- [ ] **Step 5: Commit** — `feat(setup): editable PolicyEditor component`.

## Task 4: Policy save path + validate_policy on save

**Files:** Create `frontend/src/app/api/policy/route.ts`; a TS `validatePolicy` (mirror the Wave 2 Python `validate_policy`, same as the entry-filter TS-twin precedent) in `frontend/src/lib/policy-validate.ts`; test both.

- [ ] **Step 1: Failing tests.** (a) `validatePolicy` rejects an incoherent policy — `min_holdings > max_positions`, `max_per_stock > max_per_sector`, ranks out of [0,1], bad `instrument_universe`/`rebalance_cadence`, `hard_stop ≤ 0` — returning the violation list; a valid policy returns `[]`. Hand-compute. (b) The `/api/policy` route: a valid POST writes/updates the `atlas_portfolio_policy` row (house default or a portfolio override) and returns the new effective policy; an invalid POST returns the Atlas error envelope `{error_code, message}` and writes nothing.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.** `policy-validate.ts` — port the Wave 2 `validate_policy` rules exactly (read `atlas/intelligence/policy/policy.py`). `api/policy/route.ts` — parameterized UPSERT into `atlas_portfolio_policy` (house default = the `is_house_default` row; a portfolio override = the `portfolio_id` row, created if absent); run `validatePolicy` on the resulting effective policy BEFORE writing — reject on any violation, write nothing. Match the Wave 3 `api/portfolio/propose/route.ts` conventions (envelope, parameterized SQL).
- [ ] **Step 4: Run — PASS.** Build.
- [ ] **Step 5: Commit** — `feat(setup): policy save API + validate-on-save`.

## Task 5: SETUP routes — editor page, portfolio creation, onboarding landing

**Files:** Create `frontend/src/app/setup/page.tsx`, `setup/policy/page.tsx`, `setup/new-portfolio/page.tsx`.

- [ ] **Step 1: Failing tests.** `/setup` renders the onboarding landing linking to the policy editor + portfolio creation; `/setup/policy` renders `PolicyEditor` wired to the `/api/policy` save path (house-default mode, and a portfolio selector for override mode); `/setup/new-portfolio` renders a form (name, `instrument_universe`, attach house default or start overrides) that creates a portfolio.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.** Three page shells (≤250 LOC each — logic in components). `/setup/policy` composes `PolicyEditor` + a portfolio selector + the save wiring. `/setup/new-portfolio` — a creation form posting to a portfolio-create path (reuse the existing portfolio creation if one exists; else a small API route). `/setup` — a short orientation paragraph + two links. No wizard (YAGNI).
- [ ] **Step 4: Run — PASS.** Build + deploy, screenshot each.
- [ ] **Step 5: Commit** — `feat(setup): policy editor, portfolio creation, onboarding pages`.

## Task 6: Methodology page rewrite

**Files:** Modify the methodology page.

- [ ] **Step 1: Failing test.** The methodology page renders sections covering: layered targets, Policy rails (`recommendation = engine_signal ∩ policy_constraint`), the 6-step flow, the bottom-up scorecard, and the Wave 4A hybrid rank+floor classifiers.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.** Rewrite the methodology page content to describe the current decision-engine methodology (per the decision-engine spec) and the 4A classifiers. Keep the existing page styling/components; replace stale content. Every concept links to where it is used (C1/C3).
- [ ] **Step 4: Run — PASS.** Build.
- [ ] **Step 5: Commit** — `feat(reference): methodology page describes the decision engine`.

## Task 7: Health page rewrite

**Files:** Modify the health page.

- [ ] **Step 1: Failing test.** The health page renders: the v2 state-engine coverage, the data-validator's six issue classes, the raw/derived freshness picture, and an explicit "known gaps" block.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.** Rewrite the health page to reflect the v2 engine + data-validator + freshness. The known-gaps block honestly lists current data gaps (holdings ingestion failing, `de_adjustment_factors_daily` stale) — sourced from real freshness data, not a hardcoded green status (C5). If the freshness data isn't queryable from the page, show the gaps as a static honest note with a "last reviewed" date — never a fake green.
- [ ] **Step 4: Run — PASS.** Build.
- [ ] **Step 5: Commit** — `feat(reference): health page reflects v2 engine + honest data gaps`.

---

## Self-review

**Spec coverage:** 6-section nav → Task 1 ✓; Intelligence dissolved → Task 2 ✓; editable Policy editor → Tasks 3+4 ✓; Setup pages → Task 5 ✓; methodology rewrite → Task 6 ✓; health rewrite → Task 7 ✓; validate-on-save → Task 4 ✓.

**Placeholder scan:** Tasks 1/2/6/7 say "find/explore the component first" because the exact nav + methodology + health file paths must be confirmed against the live tree — a real instruction; the change to make is fully specified. No TBDs.

**Type consistency:** `validatePolicy` (Task 4) mirrors the Wave 2 Python `validate_policy`; `PolicyEditor`'s `onSave(changedFields)` (Task 3) is consumed by `/setup/policy` (Task 5) which posts to `/api/policy` (Task 4) — consistent.

**C1–C7:** baked into each page task. Reviewers verify per task.
