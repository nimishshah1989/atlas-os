# Atlas — Development Plan

**Document:** 06_DEVELOPMENT_PLAN
**Status:** v1
**Last updated:** 2026-05-06
**Owner:** Nimish Shah (Architect)
**References:**
- `00_METHODOLOGY_LOCK.md` (the canonical spec — methodology wins over milestone drift)
- `01_BACKEND_ARCHITECTURE.md` (conventions and topology)
- `prds/00_INFRA_DECISIONS.md` (Supabase pivot, F1-F7 fixes, schema additions)
- All milestone docs in `docs/milestones/`

---

## Purpose

This document is the **strategic plan for the rest of the Atlas v0 build**. The
foundation docs say *what* and *how at a system level*; the milestone docs say
*what to build per milestone*; this document says *how we sequence the work, run
reviews, and deliver an exceptionally strong backend + frontend*.

It is the answer to "what do we do next, with which gstack skills, and in what
order, end-to-end through M5 + frontend."

---

## 1. Session bootstrap (every milestone-touching session)

Every coding session that will touch milestone code MUST begin by reading the
foundation docs and the active milestone doc. The order:

1. `docs/00_METHODOLOGY_LOCK.md`
2. `docs/01_BACKEND_ARCHITECTURE.md`
3. `docs/02_DATABASE_SCHEMA.md`
4. `docs/03_VALIDATION_FRAMEWORK.md`
5. `docs/04_THRESHOLD_CATALOG.md`
6. `prds/00_INFRA_DECISIONS.md`
7. `docs/milestones/ATLAS_M<N>.md` (active milestone)

Reading is non-negotiable. The foundation docs are dense (~4,000 lines combined)
and contain seven internally-cross-referenced rules — threshold discipline,
library discipline, suspension states, Below Trend conjunction, Stage-1
bootstrap, divergence flag semantics, dislocation override. Skipping the read
is the most common cause of drift between code and methodology.

This rule overrides the agent's normal "don't read files unprompted" instinct.
It's also persisted in the agent's memory at
`~/.claude/projects/.../memory/feedback_session_bootstrap.md`.

---

## 2. Per-milestone build loop

Every milestone (M1 → M2 → M3 → M4 → M5) follows the same four-step cadence:

```
Plan         →  Implement      →  Review                      →  Ship
────────────    ─────────────    ─────────────────────────    ──────────────
/plan-eng-    /superpowers:    /review                       /ship
  review        test-driven-   /security-review              /land-and-deploy
                development    /sebi (auto-fires fintech)    /canary (M5 only)
              /superpowers:    /codex (independent 2nd op)
                subagent-
                driven-dev
```

### 2.1 Plan phase — `/plan-eng-review`

Before any code lands, run `/plan-eng-review` against the milestone doc + any
related code skeleton. Eng-review catches:

- Numerical / library drift between methodology and proposed implementation
- Coupling concerns (which atlas tables touch which JIP tables)
- Missing edge cases (what happens with INSUFFICIENT_HISTORY, ILLIQUID,
  DISLOCATION_SUSPENDED states)
- Test gaps — what's covered by Tier 2 hand-validation, what's not

For M5 specifically, also re-run `/plan-ceo-review` since decisions are the
business product. For M4, also run `/sebi` since holdings handling crosses
the data-sensitivity boundary.

### 2.2 Implement phase — `/superpowers:test-driven-development`

Tier 2/3 validation pairs (per `03_VALIDATION_FRAMEWORK.md`) are the test
spec. Write the failing test first using the methodology's verbatim rule, then
implement. The state classifiers (`atlas/compute/states.py`) and the four
primitives (`atlas/compute/primitives.py`) are pure-math — perfect for TDD.

For pipelines that can be parallelised (e.g. M2 stock pipeline + M2 ETF
pipeline share primitives but split outputs), use
`/superpowers:subagent-driven-development` to fan out work across subagents.

### 2.3 Review phase — `/review` + `/security-review` + `/sebi` + `/codex`

Per PR (not just per milestone):

- **`/review`** — diff-scoped review. Architecture, tests, code quality.
- **`/security-review`** — built-in OWASP-style scan. New endpoints, input
  validation, authorization scope, secrets handling.
- **`/sebi`** — auto-fires for fintech projects per CLAUDE.md regime tag.
  Catches PII leakage, money-as-float violations, Decimal encoder gaps,
  audit-log completeness for threshold changes.
- **`/codex`** — independent second opinion from a different AI model.
  Particularly valuable for complex math (state classifiers) and decision
  logic (M5 gate evaluation). Catches blind spots from single-model review.

Or `/autoplan` to run the whole sequence with one command.

### 2.4 Ship phase — `/ship` + `/land-and-deploy` + `/canary`

- **`/ship`** — final merge gate. Bundles `/review` + adversarial review +
  commit + PR creation. The gate before merge.
- **`/land-and-deploy`** — production deployment.
- **`/canary`** (M5 only) — gradual rollout for the decision-engine cutover.
  Decisions affect actual fund-manager behaviour; full-deploy on day-one risks
  mass-trade signals from a buggy classifier.

### 2.5 What's NOT in the loop

- `/superpowers:write-plan` — we already have six locked milestone docs.
  Re-writing them adds noise.
- `/office-hours` — methodology is locked. The fuzzy-idea-to-spec stage is past.

---

## 3. Per-milestone notes

| Milestone | Plan-phase additions | Risk to watch | DoD signoff |
|---|---|---|---|
| **M1 — Schema + Reference** | Standard `/plan-eng-review` | Tier classification correctness; threshold seed parity with catalog | `validation_M1_<date>.md` + Nimish |
| **M2 — Stock + ETF Metrics** | Standard `/plan-eng-review`. **Highest library-discipline risk** — pandas-ta seeding, EMA boundary cases. | Numerical drift between Tier 2 hand validation and production code | `validation_M2_<date>.md` + Nimish + Bhaven (spot-check sample) |
| **M3 — Sector + Market Regime** | Standard `/plan-eng-review`. Numerical-drift risk in market-cap weighting. | Bottom-up vs top-down divergence handling; McClellan EMA seeding | `validation_M3_<date>.md` + Nimish + Bhaven (3-sector + 1-month regime spot-check) |
| **M4 — MF Three-Lens** | `/plan-eng-review` **plus `/sebi`** — holdings data crosses data-sensitivity boundary. | Holdings disclosure lag; `unknown_aum_pct` for non-universe stocks | `validation_M4_<date>.md` + Nimish + Bhaven |
| **M5 — Decision Engine** | **`/plan-ceo-review` first** (decisions are the business product), then `/plan-eng-review`, then `/sebi`. | Methodology drift (already patched once — F1-F7); ATR-stop integration | `validation_M5_<date>.md` + Nimish + Bhaven (10 stock decisions across investability/entry/exit) |

---

## 4. Frontend plan (post-M5)

### 4.1 Stack recommendation

The architecture spec (Section 10.1) names Streamlit + FastAPI for v0. **For a
fund-manager-facing UI with the "0 latency, scalable" target, recommend
switching to Next.js + Supabase JS + thin FastAPI** — flag this with
`/plan-design-review` when frontend planning starts. Streamlit is great for
analyst-internal tools but its re-run model has a ~200ms latency floor.

| Layer | Choice | Why |
|---|---|---|
| Framework | Next.js 15 (App Router) + TypeScript | RSC for first paint; ISR for non-personalised parts |
| Data client | `@supabase/supabase-js` | Direct PostgREST queries; no extra server hop for reads |
| Cache layer | TanStack Query (SWR fallback) | Stale-while-revalidate; instant cached + background refresh |
| Realtime | Supabase Realtime subscriptions | Push notifications when nightly run completes |
| UI primitives | shadcn/ui + Tailwind | Composable, themeable |
| Tables | AG Grid (per `~/.claude/rules/frontend-viz.md`) | Sortable, filterable, CSV export, financial-data-grade |
| Charts | Recharts (default) + D3 (complex viz) | Per global frontend rules |
| Hosting | Vercel | Edge-distributed, zero ops |

### 4.2 Design pipeline (gstack)

| Step | Skill | Output |
|---|---|---|
| 1. Explore | `/design-consultation` | Define design language with gstack designer |
| 2. Generate | `/design-shotgun` | 5-10 mockup directions for key screens (regime banner, sector heatmap, decision dashboard, instrument detail, fund three-lens) |
| 3. Concretise | `/design-html` | Concrete HTML mockups bound to actual atlas decision-table column names. **This is the link to backend** — mockups embed real Layer 3 schema |
| 4. Plan | `/plan-design-review` | Review chosen design against foundation docs |
| 5. Build | (no skill — implement Next.js) | Turn mockup into production frontend |
| 6. Validate | `/design-review` | Live UI check — spacing, contrast, edge cases |

### 4.3 Why gstack `/design-html` over Claude.ai design

- gstack `/design-html` knows project context. Generates mockups using actual
  atlas column names (`stock_states.rs_state`, `fund_decisions.recommendation`)
  — not generic "card with metric." Backend wiring becomes trivial.
- Output is checked into the repo, reviewable.
- Design-review skill closes the loop on the same toolchain.

### 4.4 UI contract doc (the linking artefact)

After M5 ships, write `docs/05_UI_CONTRACT.md` listing every screen + every
data binding (which atlas table, which columns, refresh cadence, filter shape).
This is the document `/design-html` reads to generate mockups bound to real
schema. It also feeds:

```bash
supabase gen types typescript --project-id PROJECT > frontend/src/types/atlas.ts
```

…which gives end-to-end type safety: mockup HTML, frontend code, and database
share one type definition.

---

## 5. Backend-frontend linking (the "0 latency, scalable" path)

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (Next.js, edge-cached)                             │
│   ▲                                                          │
│   │ static / ISR for non-personalised parts                 │
│   │ React Server Components for first paint                 │
│   │                                                          │
│   ▼ live state for interactions                             │
│  Supabase JS client (PostgREST + Realtime)                  │
│   │                                                          │
│   ▼  (with atlas_reader role + RLS)                         │
│  Supabase pooler (port 6543)                                │
│   │                                                          │
│   ▼                                                          │
│  Postgres: atlas.* tables (pre-computed Layer 3)            │
│            └── 100ms range queries via existing indexes     │
└─────────────────────────────────────────────────────────────┘

For mutations (threshold updates, "Apply & Reclassify"):
                  │
                  ▼
          FastAPI endpoint (separate process)
                  │
                  ▼
          atlas_writer role + audit log
```

### 5.1 Why this hits "0 latency"

1. **Pre-computed tables** (architecture pillar 4) — no compute at request time.
   Sub-100ms queries via the indexes already defined in migration 008.
2. **PostgREST direct queries** — Supabase's auto-generated REST API skips
   FastAPI for read-heavy pages. Latency = network + 1 DB query.
3. **React Server Components** — first-paint HTML rendered server-side with
   data attached.
4. **TanStack Query** — instant cached response, background refresh.
5. **Supabase Realtime** — when the nightly run finishes, dashboards
   auto-update. No polling.
6. **Edge caching** for static paths (methodology page, threshold catalog UI).

### 5.2 Why this is "easy / scalable"

- One stack (Postgres + Next.js + Supabase) instead of three (Streamlit +
  FastAPI + Postgres).
- Type safety end-to-end via `supabase gen types`.
- Auth + RLS handle user permissions without per-endpoint logic.
- Vercel hosting → zero ops, edge-distributed.
- Supabase pooler handles connection scaling.

### 5.3 Minimal FastAPI surface

Three endpoints only:

1. `POST /thresholds/update` — fund manager edits a threshold (writes
   `atlas_thresholds` + `atlas_threshold_history` audit row).
2. `POST /thresholds/reclassify` — triggers the ~5-minute reclassify job
   (idempotent; logs to `atlas_run_log` with `reclassify=TRUE`).
3. `POST /admin/run-pipeline` — manual nightly trigger (cron handles the
   normal case).

Everything else is direct Supabase reads via PostgREST.

---

## 6. Sequencing — concrete order from "now" to "v0 backend complete + frontend live"

### 6.1 Right now (Supabase migration in flight)

- User: completing JIP→Supabase migration via `scripts/migrate_to_supabase.py`.
- Agent: doc + code work that doesn't need a live DB (already done — see
  `prds/00_INFRA_DECISIONS.md` and the `atlas/` package).

### 6.2 Immediately after migration completes

```bash
# Verify Supabase has everything M1 needs
python scripts/m1_preflight.py
```

→ GO / REVIEW / NO-GO + `output/preflight_supabase_<date>.md` markdown report.

If REVIEW or NO-GO, fix the gap in the JIP migration before continuing.

### 6.3 M1 build sequence

```bash
# Plan
/plan-eng-review docs/milestones/ATLAS_M1_SCHEMA_AND_REFERENCE.md

# Implement (already mostly written; eng-review may surface tweaks)
python scripts/m1_run.py    # migrations + universe lock

# Verify
pytest tests/unit/                    # universe filter logic
python -m atlas.validation.tier1_raw  # M1 Tier 1 raw cross-validation (to be written)

# Review the PR
/review
/security-review
/sebi

# Ship
/ship
```

### 6.4 M2 → M3 → M4 → M5

Same loop per milestone. See Section 3 for milestone-specific notes.

### 6.5 Frontend (post-M5)

```bash
# Design language
/design-consultation

# Mockup directions
/design-shotgun

# Bound mockups
# (write docs/05_UI_CONTRACT.md first)
/design-html

# Review chosen direction
/plan-design-review

# Build with Next.js (no specific skill)

# Validate live UI
/design-review

# Deploy
/land-and-deploy
/canary  # decision-engine cutover gradually
```

---

## 7. Memory and continuity

This plan is persisted in three places, and the agent is instructed to read all
of them at session start (per `feedback_session_bootstrap.md`):

1. **This file** (`docs/06_DEVELOPMENT_PLAN.md`) — versioned in the repo.
2. **Auto-memory** at
   `~/.claude/projects/-Users-nimishshah-Documents-GitHub-atlas-os/memory/`
   — pointers, feedback, project context.
3. **Project-level `CLAUDE.md`** — orientation directive for the agent at
   session start.

When this plan changes (e.g. v0.5 retrospect re-orders milestones), update all
three locations. Don't let any one fall stale.

---

## 8. What this document does NOT cover

- Specific milestone build steps — see milestone docs (`ATLAS_M*.md`).
- What gets computed — see `00_METHODOLOGY_LOCK.md`.
- Library choices — see `01_BACKEND_ARCHITECTURE.md` Section 5.
- Table layouts — see `02_DATABASE_SCHEMA.md`.
- Validation criteria detail — see `03_VALIDATION_FRAMEWORK.md`.
- Threshold catalog — see `04_THRESHOLD_CATALOG.md`.

---

**Document version:** 1.0
**Last updated:** 2026-05-06
**Next review:** After M2 completion — re-evaluate cadence based on actual time spent in each phase.
