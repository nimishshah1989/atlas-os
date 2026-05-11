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

1. **Tiered file-size limits.** Different file kinds have different reasonable
   lengths; one-size-fits-all is the wrong call:

   | File kind | LOC limit |
   |---|---|
   | Source files (`atlas/`, `frontend/src/components|lib|hooks/`) | **600** |
   | Test files (`tests/`, `*test_*.py`, `*.test.ts`, `*.spec.ts`) | **800** |
   | Page shells (`frontend/src/app/**/page.tsx`, `layout.tsx`) | **250** (thin shells; logic goes in lib/components) |
   | Migrations / lockfiles / generated | no limit (whitelisted) |

   **Escape valve:** if a file is *genuinely* cohesive at its current size,
   add `# allow-large: <reason>` (Python) or `// allow-large: <reason>`
   (TS/JS) anywhere in the file. The reason becomes the load-bearing
   artifact reviewers can challenge — line count alone is never the smell,
   *responsibility count* is. The marker forces the author to write the
   justification down where every reviewer sees it.

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

---

## Standing guardrails from 2026-05 health audit

Learnings from the first full codebase health pass. Each rule maps to a bug
category found in the audit — treat them as patterns to watch for.

### Compute pipeline rules

- **`load_thresholds()` returns `dict[str, Decimal]`.** All compute functions
  that accept thresholds must type-hint them as `Mapping[str, Decimal]` not
  `dict[str, float]`. When using threshold values in arithmetic with floats
  (e.g. `/100.0`), cast first: `float(thresholds["key"]) / 100.0`.

- **Division guards on all ratio columns.** Any `x / y` where `y` comes from
  benchmark or external data must use `.replace(0, pd.NA)` to guard zero
  denominators. Holiday runs and early history produce zero vols → `inf` risk
  states. Pattern: `stock_col / bench_col.replace(0, pd.NA)`.

- **`np.select` ordering is conservative-first.** When conditions overlap at
  threshold edges, the more-restrictive/negative state must appear first.
  "Avoid before Underweight before Overweight", "Below Trend before High before
  Elevated". First-match-wins — wrong order silently overrides the right state.

- **NAV gaps must be logged before filling.** Never call `ffill()` or
  `fillna()` on NAV/price series without first counting and logging gap rows.
  Pattern: `if na_count := df["close"].isna().sum(): log.warning("nav_gaps", count=int(na_count)); df["close"] = df["close"].ffill()`.

- **VIX NaN requires per-condition guards.** Missing VIX must not silently
  force the regime to a non-Risk-On state. Use `vix_valid = vix.notna()` and
  gate conditions: `is_risk_on = ... & (~vix_valid | (vix < threshold))`.

- **No SQL f-strings without `# noqa: S608` with justification.** Global S608
  suppression was removed. Every SQL f-string must have a per-line noqa with a
  reason explaining why the identifier is safe (constant, whitelist-validated,
  schema-introspected — never user input).

### Frontend rules

- **No `SELECT *` on time-series tables.** Enumerate exact columns matching
  the TypeScript type. `SELECT *` on a 30-column regime table breaks silently
  if columns are added/removed.

- **No `parseFloat()` on financial Decimal fields.** Use `Number()` for
  display-only coefficients (deployment multiplier). For anything stored as
  money, keep as string and format at display time.

- **No non-null assertions (`!`) on nullable DB fields.** Use optional
  chaining (`?.`) with `?? '0'` fallback. The assertion produces `NaN%` in
  the UI when the field is NULL — which is valid DB state for new funds.

### Architectural red flags

- **`atlas.api.*` must not import from `atlas.simulation.*` internals.** Use
  the simulation context's public `__init__.py` exports only.

- **Fake 202 responses must not persist `status='running'`.** Either spawn
  the subprocess or return `status='queued'` with no DB row. A running row
  that never completes permanently blocks the 30-min concurrency guard.

- **Auth middleware must exist before shipping M6.** Current `atlas/api/__init__.py`
  has no Supabase JWT middleware. All M6 API routes must be behind
  `get_current_user` dependency before going to production.
