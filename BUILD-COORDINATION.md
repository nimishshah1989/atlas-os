# v6 Build Coordination

**Purpose:** orientation doc for every spawned Claude Code session working on the v6 build. Read this first.

**Status:** Phase 1 underway · 11 of 12 mockups locked + glossary drafted · awaiting Calls 08 r2 to close design phase.

---

## Locked artefacts (read these before coding)

| Artefact | Path |
|---|---|
| Engineering rules | `~/.claude/CLAUDE.md` + `./CLAUDE.md` |
| Canonical glossary | `./CONTEXT.md` |
| New glossary additions (r2) | `./docs/v6/glossary-additions-2026-05-26.md` |
| ADR for glossary additions | `./.ruflo/adr/2026-05-26-v6-glossary-additions.md` |
| 12 mockups (design lock) | `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/` |
| Mockup index | `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/index.html` |
| Domain map | `./docs/agents/domain.md` |
| v6 runbook | `./docs/v6/runbook.html` |

---

## Stream registry

Each stream is owned by one Claude Code session. Streams have non-overlapping file scopes by design — they can run concurrently without merge conflicts.

| Stream | Owner | Scope | Branch prefix | Status |
|---|---|---|---|---|
| **A1** | Backend agent #1 | `mv_market_regime_landing`, `mv_india_pulse`, `mv_markets_rs_grid` | `feat/v6-mv-pulse-` | ⏳ pending session |
| **A2** | Backend agent #2 | `mv_sector_cards`, `mv_sector_rrg`, `mv_sector_breadth`, `mv_sector_deepdive` | `feat/v6-mv-sectors-` | ⏳ pending session |
| **A3** | Backend agent #3 | `mv_stock_list_v6`, `mv_stock_landscape`, `mv_stock_deepdive` | `feat/v6-mv-stocks-` | ⏳ pending session |
| **A4** | Backend agent #4 | `mv_fund_list_v6`, `mv_fund_amc_ladder`, `mv_fund_deepdive`, `mv_etf_list_v6`, `mv_etf_premium_track`, `mv_etf_deepdive`, `mv_calls_performance` | `feat/v6-mv-funds-etfs-calls-` | ⏳ pending session |
| **B** | Frontend agent | 6 primitives + ECharts migration in `frontend/src/components/v6/primitives/` | `feat/v6-primitives-` | ⏳ pending session |
| **C** | Contracts agent | 12 Pydantic + Zod contract pairs in `atlas/v6/contracts/` + `frontend/src/contracts/v6/` | `feat/v6-contracts-` | ⏳ pending session |
| **D** | Orchestrator (this) | Calls 08 r2 mockup, glossary draft, coordination, PR review/merge | n/a | 🔄 running |

---

## Dependency graph

```
                                       ┌──────────────────┐
                                       │ Phase 1 (Stream D)│
                                       │ glossary + ADR    │  ✅ done
                                       │ Calls 08 r2       │  🔄 running
                                       └────────┬──────────┘
                                                │
                              ┌─────────────────┼─────────────────┐
                              │                 │                 │
                       ┌──────▼──────┐  ┌───────▼────────┐  ┌─────▼─────┐
                       │ Stream C    │  │ Streams A1-A4  │  │ Stream B  │
                       │ Contracts   │  │ Backend MVs    │  │ Primitives│
                       │ (12 pairs)  │  │ (14 MVs total) │  │ (6 + ECharts)│
                       └──────┬──────┘  └───────┬────────┘  └─────┬─────┘
                              │                 │                 │
                              └─────────────────┼─────────────────┘
                                                │
                                       ┌────────▼─────────┐
                                       │ Phase 4 wire-up  │
                                       │ 12 page sessions │
                                       │ in parallel      │
                                       └──────────────────┘
```

**Critical path:** A + B + C must all complete before Phase 4 starts. A1-A4 are mutually independent (different files). C blocks Phase 4 but not A or B (no file overlap).

---

## Workflow per session

Every session does **exactly this**, in this order:

1. **Read the orientation pack:**
   - This file
   - `./CLAUDE.md` + global `~/.claude/CLAUDE.md`
   - `./CONTEXT.md` + `./docs/v6/glossary-additions-2026-05-26.md`
   - The mockup(s) in scope for the stream

2. **Invoke planning skill** (PreToolUse hook enforces this on gated paths):
   - Backend → `/grill-with-docs` → `/plan-eng-review`
   - Frontend → `superpowers:brainstorming` → `/plan-eng-review`
   - Contracts → `/grill-with-docs` → `/plan-eng-review`

3. **Implement with TDD:**
   - `superpowers:test-driven-development` — tests before implementation
   - Backend: pytest hits real DB (no mocks per memory)
   - Frontend: Vitest + Storybook
   - Contracts: fixture-based parse validation

4. **Pre-merge gauntlet** (mandatory · every PR):
   1. `superpowers:verification-before-completion` — show test/type/lint output
   2. `coderabbit:code-review` — automated diff review
   3. `/codex review` — independent Codex pass
   4. `/review` — pre-landing SQL safety + structural review
   5. Frontend pages also need `/design-review` (visual vs locked mockup) + `/qa`

5. **Ship:**
   - `/ship` — open PR
   - `/land-and-deploy` — merge + watch CI + verify deploy
   - `/canary` — post-deploy health monitoring

---

## PR conventions

**Title format:**
- Stream A: `feat(v6): <mv_name> + nightly refresh`
- Stream B: `feat(v6/primitives): <PrimitiveName>` or `feat(v6/charts): ECharts migration`
- Stream C: `feat(v6/contracts): batch <n> — <pages>`
- Stream D / Phase 4: `feat(v6/page): wire <pageId> to <mv_name>`

**Granularity:** PR-per-MV (Stream A), PR-per-primitive (Stream B), PR-per-batch-of-4 (Stream C, 3 PRs total), PR-per-page (Phase 4).

**Branch from `main`.** Stack PRs if dependent (rare — coordination is by file scope, not commit history).

**Squash-merge to `main`.** User has authorized this for v6 (per memory).

---

## Hook-enforced rules (don't fight, address)

Per `./CLAUDE.md`:

- **No float for money** → use `Decimal` (fintech regime, auto-detected)
- **No PII in log lines**
- **`# pragma: finance-critical`** files require a corresponding test file
- **No hardcoded credentials** · **no bare `except:`**
- **No frontend code without `.design-approved.json`** (locked mockups satisfy this)
- **pyright + eslint must pass post-edit**
- **Gated paths** (`atlas/**`, `frontend/src/**`, `migrations/versions/**`) require a planning skill invoked first in the session

If a hook blocks, read the stderr and fix the underlying issue. Don't bypass.

---

## Quality review mechanism

Per FORGE OS + the locked skill cadence:

| Layer | Tool | What it catches |
|---|---|---|
| Pre-implementation | `/grill-with-docs` | Terminology + spec drift before code is written |
| Implementation | `superpowers:test-driven-development` | Untested code path |
| Post-implementation | `superpowers:verification-before-completion` | False "done" claims |
| Diff review (automated) | `coderabbit:code-review` | Style + bug surfaces |
| Diff review (LLM #2) | `/codex review` | Independent second-model pass |
| Pre-merge | `/review` | SQL injection · LLM trust boundaries · structural |
| Visual (frontend) | `/design-review` | Visual drift from locked mockup |
| E2E (frontend) | `/qa` | Browser-driven regression |
| Post-deploy | `/canary` | Console errors · perf regressions · screenshot drift |

Every PR must clear all applicable layers before merge. The orchestrator (this session) gatekeeps.

---

## Status tracking

Each spawned session updates this file's stream-registry status column when it opens its first PR:

`⏳ pending session` → `🔄 in progress · PR #<num>` → `✅ merged`

The orchestrator session monitors via `gh pr list --label v6` and ad-hoc PR check commands.

---

## How to start your stream

1. Open a new Claude Code chat in the same VS Code window (the orchestrator session prepared paste-ready prompts in chat history above)
2. Paste your stream's prompt
3. Let the session invoke `/grill-with-docs` + `/plan-eng-review` first — hooks gate everything else
4. Open PR via `/ship`
5. The orchestrator picks up the PR, runs the gauntlet, merges

---

**Last updated:** 2026-05-26 · post-glossary draft · awaiting Calls 08
