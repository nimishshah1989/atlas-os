---
nimish-os: 1.0
project: atlas-os
domain: fintech              # fintech | restaurant | content | health | other
regime: [SEBI, DPDP]              # YAML list, e.g. [SEBI, DPDP] — drives skill auto-load
stack: [python, fastapi, postgres]                 # YAML list, e.g. [python, fastapi, postgres, react]
has_frontend: true   # true | false
scale: large                 # small | medium | large
---

# atlas-os

This file orients agents working on this project. Global engineering rules live at `~/.claude/CLAUDE.md`. Hooks fire on every edit regardless of mode (planned milestone, ad-hoc chat, exploration). The frontmatter above drives:
- regime-specific skill auto-load (Indian regulatory matrix from `~/forge-skills/<regime>/`)
- fintech context detection for hooks (no float on money, no PII in logs, FastAPI Decimal encoder)
- Design Protocol activation if `has_frontend: true`

## Project-specific notes

- Stack-specific decisions: see `decisions.jsonl` (append-only, hash-chained).
- ADRs: see `.ruflo/adr/` (managed by `ruflo-adr` plugin).
- Active milestone status: see `tasks.jsonl` if present, or run `npx ruflo hive-mind status`.

## What goes in this file (vs the global one)

- Project-only conventions (e.g. "we use Polars not pandas in this codebase")
- Project-only paths or entry points
- Project-only deferred work / known limitations

Do NOT duplicate global rules from `~/.claude/CLAUDE.md` here — they're already loaded.

---

## Engineering discipline (NON-NEGOTIABLE)

atlas-os is a **modular monolith** ("modulith"). Each top-level package under
`atlas/` is a bounded context. The boundaries are enforced by hooks; treat
them as load-bearing.

### Skill cadence — invoke BEFORE coding

For ANY new file or non-trivial edit in `atlas/`, `frontend/src/`, or
`migrations/versions/`, you MUST first invoke at least one of these skills:

| Situation | Skill |
|---|---|
| Any meaningful edit | `andrej-karpathy-skills:karpathy-guidelines` |
| New feature / new module | `plan-eng-review` |
| Refactor or simplify existing | `simplify` |
| UI components | `frontend-design:frontend-design` |
| New bounded context | `ruflo-ddd:ddd-context` |
| New aggregate root | `ruflo-ddd:ddd-aggregate` |
| Unclear scope / new product idea | `superpowers:brainstorming` or `office-hours` |
| Multi-step plan | `superpowers:writing-plans` |
| Bugfix or feature with TDD | `superpowers:test-driven-development` |
| Before claiming done | `superpowers:verification-before-completion` |
| Pre-merge | `review` + `codex` |

A PreToolUse hook enforces this gate: Write/Edit on `atlas/**`, `frontend/src/**`,
or `migrations/versions/**` is blocked unless one of the planning skills was
invoked earlier in the session. Don't fight the hook — invoke a planning skill
or argue the rule out in a plan first.

### Architectural rules (hook-enforced)

1. **No file > 400 LOC.** Approaching the limit = split into a sub-package.
2. **No cross-context imports.** `atlas.compute.*` cannot import `atlas.api.*`,
   etc. Exchange happens via the shared kernel (`atlas.primitives`, `atlas.db`,
   `atlas.config`) or a context's public `__init__.py`.
3. **Methodology thresholds live in `atlas.atlas_thresholds`,** loaded via
   `atlas.db.load_thresholds()`. No hardcoded thresholds in code (use
   `# noqa: threshold` only for genuine non-thresholds).
4. **Decimal for money. Tz-aware datetimes.** Float for money is rejected by
   global hooks.

### API design (when M6+ ships)

- Bloomberg-style: terse, function-style URLs (`/api/v1/screen.stocks`),
  versioned, immutable contract.
- Pydantic v2 for every request/response. Schema = contract. OpenAPI auto-generated.
- Response envelope: `{"data": ..., "meta": {"data_as_of", "fetched_at", "source"}}`.
- Error envelope: `{"error_code", "field", "message", "context"}`.
- Cursor pagination. Never offset.
- `X-RateLimit-*` headers always.
- `Idempotency-Key` header on writes.
- Auth = Supabase JWT verified in middleware; `request.state.user` carries `user_id`, `role`.

### Threshold tuning

Threshold values in `atlas.atlas_thresholds` are tunable at runtime. To change a
value:
1. UPDATE the row (will trigger `atlas_threshold_history` audit log).
2. Next compute run picks up the new value via `load_thresholds()`.
3. No redeploy needed.

When `/admin/thresholds` UI ships, it'll surface diff preview + audit trail
before save.
