# Atlas v2 — Wave 4B: Information Architecture Rework — Design Spec

**Date:** 2026-05-20
**Branch:** feat/atlas-consolidation
**Status:** Design approved via brainstorming; pending writing-plans.
**Anchors:** [Decision Engine spec](2026-05-20-atlas-decision-engine-design.md), [Wave 4A spec](2026-05-20-atlas-wave4a-engine-methodology-design.md). 4B follows 4A — the methodology page describes the 4A-corrected methodology.

## Problem

Atlas v2 became a decision tool (regime → sector → stock → conviction → act → deterioration), but its navigation still reads like the old set of dashboards. Three gaps:

1. The top nav (Research / Portfolio / Intelligence / Reference / Admin) does not mirror how a fund manager works, and "Research" vs "Intelligence" is ambiguous.
2. The Policy — the spine of the decision engine — is only a read-only panel on the portfolio page. There is no way to *edit* it. There are no Setup/onboarding pages at all.
3. The methodology and health pages predate the decision engine and describe a stale model.

## Goals

- A flow-ordered navigation that mirrors the decision path.
- A first-class, editable Policy surface.
- Setup pages for configuring Atlas to a desk's mandate.
- Methodology and health pages that describe the current engine.

## Non-goals

- No change to the decision-flow logic, the state engine, or the 4A classifiers — 4B is navigation, page structure, and the Policy editor only.
- No heavy multi-step onboarding wizard (YAGNI) — Setup is a small set of focused pages.
- No new data model beyond what the Policy editor's save path needs (the `atlas_portfolio_policy` table from Wave 2 already exists).

## The new navigation — 6 sections

| Section | Contents | Notes |
|---|---|---|
| **TODAY** | Regime homepage `/` (verdict + bottom-up scorecard + worklist) + the daily brief. | The morning start surface. Absorbs the daily-brief content from the dissolved Intelligence section. |
| **RESEARCH** | Sectors, Stocks, ETFs, Funds, Global Pulse, US Pulse. | The evidence/exploration surfaces. Content unchanged, regrouped. |
| **PORTFOLIOS** | Portfolio list + detail (holdings, current-vs-target, Act loop, deterioration, the read-only Policy panel showing the active effective policy). Strategy Lab as a sub-area. | Strategy Lab is portfolio-construction; it stays here. |
| **SETUP** *(new)* | Policy editor, portfolio creation, onboarding landing. | Configure the engine to the desk's mandate. |
| **REFERENCE** | Methodology (rewritten), Health (updated), Glossary. | |
| **ADMIN** | Thresholds, composite proposals, signal-validation / IC, data-validator. | Operator surfaces. Absorbs the IC/validation content from the dissolved Intelligence section. |

The current top-level **Intelligence** section is removed: its daily-brief content moves to TODAY, its signal-validation/IC content moves to ADMIN. This resolves the Research/Intelligence ambiguity.

## Policy pages (in SETUP) — the principal new build

A first-class **Policy editor**:

- **House-default view + edit.** Every Policy field (the migration-092 field set: deployment, concentration, entry, exit, instrument-universe, benchmark, cadence) is displayed and editable for the single `is_house_default` row.
- **Per-portfolio view + edit.** For a selected portfolio, every field shows whether it is *inherited* (from the house default) or *overridden*, and is editable. Setting a field creates/updates an override row; clearing it reverts to inherited.
- **Validation on save.** `validate_policy` (Wave 2, Task 2.3) runs before persisting — an incoherent policy (`min_holdings > max_positions`, `max_per_stock > max_per_sector`, ranks out of [0,1], etc.) is rejected with a clear message; nothing is written.
- **Persistence.** Writes to `atlas_portfolio_policy` via a new write path (a server action / API route). The Wave 2 table already exists; no migration needed unless an `updated_at` trigger or audit row is wanted.
- The portfolio detail page keeps its existing **read-only** Policy panel (the active effective policy). The SETUP editor is the single place policy is changed.

## Setup pages (SETUP)

Three focused pages, deliberately minimal:

1. **Policy editor** — as above.
2. **Portfolio creation** — name a book, choose its `instrument_universe`, attach the house-default Policy or start an override set. Creates the portfolio row.
3. **Onboarding landing** — a short "configure Atlas to your desk" page linking to the Policy editor and portfolio creation, with one paragraph of orientation. Not a wizard.

## Methodology page (REFERENCE)

Rewritten to explain the current methodology: layered targets (sector targets filled by instrument picks); Policy rails and `recommendation = engine_signal ∩ policy_constraint`; the 6-step decision flow; the bottom-up 4-signal scorecard; and the Wave 4A hybrid rank + absolute-floor sector/fund classifiers. It replaces the pre-decision-engine methodology content.

## Health page (REFERENCE)

Updated to reflect: the v2 state engine and its coverage; the data-validator's six issue classes; the raw/derived table freshness picture; and an honest surfacing of the known data gaps (holdings ingestion currently failing, `de_adjustment_factors_daily` stale). The health page should not present a green status it has not earned.

## Cross-cutting requirements

Every new and changed page must satisfy the decision-engine plan's C1–C7: cross-linked (the 64-element rule — every ticker/sector/fund/ETF/state token is a link), consistent components, every element explained with a tooltip, dense-not-overwhelming, zero synthetic data, formulas tested, logic checks. The Policy editor in particular: every field gets its tooltip; the inherited/overridden state is always honest; validation errors are explicit.

## Architecture

- Nav: the top-nav component + route grouping change. Routes themselves can largely stay; the nav config and section grouping are what change. Where a route's section changes, redirects or moved files as needed — follow the Next.js App Router structure already in place.
- Policy editor: a new `frontend/src/app/setup/policy/` route + an editable `PolicyEditor` component (distinct from the read-only `PolicyPanel`), a `policy.ts` write path, and validation wired to the Wave 2 `validate_policy` logic (port to TS or call a backend route — match the Wave 2 entry-filter precedent).
- Setup + onboarding: new routes under `frontend/src/app/setup/`.
- Methodology + health: content rewrites of the existing pages.

## Testing

- Policy editor: tests that an edit persists, that `validate_policy` rejects an incoherent policy on save (nothing written), that inherited vs overridden renders correctly, that clearing an override reverts to inherited.
- Nav: every section's links resolve; no dead route after the regrouping.
- Methodology / health: content pages — light render tests.

## Definition of done

1. The 6-section flow-ordered nav is live; no dead links; the Intelligence section is gone with its content rehomed.
2. A fund manager can edit the house-default Policy and a per-portfolio override from SETUP, and an incoherent policy is rejected on save.
3. Portfolio creation works from SETUP.
4. The methodology page describes the decision engine + the 4A classifiers; the health page reflects real engine + freshness state including known gaps.
5. Every new/changed page satisfies C1–C7.
