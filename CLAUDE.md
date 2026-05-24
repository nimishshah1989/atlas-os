---
nimish-os: 1.0
project: atlas-os
domain: fintech
regime: [SEBI, DPDP]
stack: [python, fastapi, postgres]
has_frontend: true
scale: large
---

# atlas-os

Global engineering rules live at `~/.claude/CLAUDE.md`. This file is a thin
pointer; substance lives in the docs below.

## Active track

**v6** — discovery-first equity intelligence platform rebuild (post-2026-05-24).
Read `docs/v6/runbook.html` FIRST every v6 session. Phase 2 (SP01-SP10) still
exists as a parallel surface; read `docs/phase2/00-master-plan.html` if you
touch it.

## Required reading (every session)

1. `docs/v6/runbook.html` — build runbook (bootstrap, per-chunk loop, gates)
2. `CONTEXT.md` — domain glossary (auto-loaded with this file)
3. `~/.gstack/projects/atlas-os/ceo-plans/2026-05-24-atlas-v6-product-spec.md` — CEO plan
4. `~/.gstack/projects/atlas-os/eng-plans/2026-05-24-atlas-v6-eng-review.html` — eng review

## Pointers (read on demand)

- `docs/health-audit-rules.md` — 2026-05 audit guardrails (compute / frontend / arch)
- `docs/agents/supabase-mcp.md` — Supabase MCP tiers + marker protocol
- `docs/agents/issue-tracker.md` — GitHub issues via `gh` CLI
- `docs/agents/triage-labels.md` — five canonical triage roles
- `docs/agents/domain.md` — CONTEXT.md + ADR conventions
- `decisions.jsonl` — append-only hash-chained audit log (Ruflo-managed)
- `.ruflo/adr/` — ADRs for hard-to-reverse decisions
- `<consolidation>/docs/atlas-signal-discovery/methodology-lock-2026-05-23.md` — methodology lock

## Architectural rules (HOOK-ENFORCED — don't fight)

1. **Modulith**. Each top-level `atlas/` package is a bounded context. No cross-context imports except via `atlas.primitives`, `atlas.db`, `atlas.config` or a context's public `__init__.py`.
2. **Tiered file-size limits**: 600 LOC source / 800 LOC tests / 250 LOC page shells. Escape valve: `# allow-large: <reason>` (Python) or `// allow-large: <reason>` (TS).
3. **Methodology thresholds** live in `atlas.atlas_thresholds`, loaded via `atlas.db.load_thresholds()`. No hardcoded constants in code.
4. **Decimal for money. Tz-aware datetimes.** Float for money is rejected by global hooks.
5. **v6 module edits gated** — `atlas/{features,decisions,regime,portfolio,ledger,macro,agents}/` Edits require a chunk-level planning skill (`/grill-with-docs`, `/tdd`, or `/plan-eng-review`) invoked first in the session.
6. **Phase 0 gated** — `git checkout -b feat/v6-phase-0-*` or migration 080 require all 4 pre-build gates closed in `~/.gstack/projects/atlas-os/v6-gates.json`.

## Skill cadence — invoke BEFORE coding

| Situation | Skill |
|---|---|
| Start of v6 chunk | `/grill-with-docs` (lock terms vs CONTEXT.md) |
| Bugfix or new feature | `/tdd` |
| New feature / module | `/plan-eng-review` (full review) or just grill-with-docs (mini) |
| Refactor existing | `simplify` |
| UI components | `frontend-design:frontend-design` |
| Unclear scope | `superpowers:brainstorming` or `office-hours` |
| Multi-step plan | `superpowers:writing-plans` |
| Before claiming done | `superpowers:verification-before-completion` |
| Pre-merge | `/review` + `/codex review` |
| Ship | `/ship` then `/land-and-deploy` |
| Session end | `/context-save` (or wait for Stop hook to auto-write) |
| Session start (gap > 1 day) | `/context-restore` |
| Weekly | `/retro` |
| Monthly (cathedral test) | `/zoom-out` |
| Quarterly | `/improve-codebase-architecture` |
| Stuck > 3 attempts | `/codex:rescue` or `/diagnose` |

PreToolUse hook blocks Edit/Write on `atlas/**`, `frontend/src/**`,
`migrations/versions/**` unless one of the planning skills was invoked
earlier in the session.

## API design (v6 endpoints)

- Bloomberg-style terse URLs (`/v1/screen.stocks`), versioned, immutable.
- Pydantic v2 every request/response. Schema = contract. OpenAPI auto-gen.
- Response envelope: `{"data": ..., "meta": {"data_as_of", "fetched_at", "source"}}`.
- Error envelope: `{"error_code", "field", "message", "context"}`.
- Cursor pagination. Never offset. `X-RateLimit-*` headers. `Idempotency-Key` on writes.
- Auth = Supabase JWT in middleware; `request.state.user` carries `user_id`, `role`.

## What goes in this file

Project-only conventions, paths, and pointers. NOT a place to duplicate
global rules from `~/.claude/CLAUDE.md`. Keep this file under 120 lines —
long CLAUDE.md files dilute their own enforcement.
