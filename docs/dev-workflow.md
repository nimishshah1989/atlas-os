# Development workflow and tooling

Moved out of `CLAUDE.md` (which is capped at 60 lines) on 2026-09-04. Nothing here is new policy;
it is the long form of the Workflow section.

## Where development happens

**Write code on the laptop, never on the box.** `scripts/ops/atlas-auto-deploy.sh` only ever runs on
`main`; an edit made on the box either gets stashed by the deployer or silently stops future deploys,
with no error surfaced anywhere you'd look. The box is a deploy target, not a workstation.

Loop: edit locally → `make gate` → push a branch → PR → merge to `main` → the box fast-forwards and
rebuilds itself. `scripts/ops/promote_box_to_main.sh` force-resyncs the box if it ever drifts.

Local setup: `make setup`, then `.env` with `ATLAS_DB_URL` (copy from `frontend/.env.local`).
`make gate` (lint + tests + pyright **ratchet**) is the pre-PR check — ~7s. **Not `make check`**, which
runs raw pyright and exits non-zero by design on the grandfathered baseline. `make test` = unit tests
only, no DB. Integration tests run fine **on the laptop** via the `aws-1-ap-south-1` pooler on 6543
(whole portfolio suite ~30s) — point `ATLAS_DB_URL` at it. The direct `db.<ref>.supabase.co:5432` host
is IPv6-only and unreachable from macOS. `aws-0-` refuses the connection.

## Local workspace (NEVER under iCloud)

The git tree MUST live outside any iCloud-synced folder — iCloud "Optimize Mac Storage" evicts `.git`
pack objects and corrupts the repo (`pack … far too short to be a packfile`). Canonical local path:
**`~/All AI/atlas-os`** (moved out of iCloud 2026-07-29). **If this repo moves again, re-key its Claude
memory** — memory is keyed by folder path; `~/.claude/bin/rekey-memory` repairs it.

## Laptop-only guardrails

The PreToolUse hook that gates edits to `atlas/**`, `frontend/src/**`, `migrations/versions/**` until a
planning skill has run lives in the laptop's `~/.claude/`, not in this repo; cloud sessions rely on the
skill cadence in `CLAUDE.md` instead.

## Tooling (what the session hook installs, and what stays laptop-side)

| Tool | Where | How |
|---|---|---|
| **Vendored skills** — ponytail (`ponytail`, `ponytail-review`, `-audit`, `-debt`, `-gain`, `-help`), superpowers (`brainstorming`, `test-driven-development`, `verification-before-completion`, `writing-plans`, `executing-plans`, `subagent-driven-development`, `dispatching-parallel-agents`, `systematic-debugging`, `using-git-worktrees`, `requesting-`/`receiving-code-review`, `finishing-a-development-branch`, `writing-skills`, `using-superpowers`), `frontend-design`, `graphify` | `.claude/skills/` (committed; MIT / Apache-2.0 licences alongside) | Nothing to do — every session (laptop or cloud) loads them. Upstream: DietrichGebert/ponytail, obra/superpowers, anthropics/skills. |
| **gstack** (55 skills: `plan-eng-review`, `review`, `ship`, `land-and-deploy`, `investigate`, `qa`, `browse`, …) | global `~/.claude/skills/gstack` | Laptop: `git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack && cd ~/.claude/skills/gstack && ./setup`. Cloud: `.claude/hooks/session-start.sh` does the same on first start (needs bun; downloads a headless Chromium for `/browse`). |
| **graphify** (code knowledge graph) | CLI via `uv tool install graphifyy`; skill in `.claude/skills/graphify` | `graphify update . --no-cluster` rebuilds `graphify-out/` (~10s, AST only, no LLM). Gitignored; the session hook rebuilds it. Query with `graphify query "…"`, `graphify explain "…"`, `graphify path "A" "B"`. The PreToolUse hooks in `.claude/settings.json` nudge Claude to query the graph before grepping. |
| **headroom** (context compression) | laptop | `uv tool install --python 3.13 "headroom-ai[all]"` then `headroom wrap claude` — a local proxy that compresses tool outputs before they reach the model. Only applies to sessions launched through it (not cloud sessions). `headroom mcp install --agent claude` registers its MCP tools; the hook does that in the cloud, best-effort. |

The session hook (`.claude/hooks/session-start.sh`) runs only in Claude Code on the web
(`CLAUDE_CODE_REMOTE=true`), synchronously, and is idempotent: `uv sync --extra dev`, install
graphify/headroom if missing, rebuild the graph if missing, install gstack if missing. Every step is
best-effort — a network failure never blocks a session.
