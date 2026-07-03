---
nimish-os: 1.0
project: atlas-os
domain: fintech
regime: [SEBI, DPDP]
stack: [python, nextjs, postgres]
has_frontend: true
scale: large
---

# atlas-os

Atlas is a discovery-first **equity-intelligence board** for Indian markets: it
ingests real market data nightly, scores stocks / ETFs / funds / sectors through a
lens methodology, and serves it as a glass-box web board. Global engineering rules
live at `~/.claude/CLAUDE.md`; this file holds only Atlas-specific substance.

## ⛔ ABSOLUTE RULE #0 — NO SYNTHETIC OR DERIVED DATA (ZERO TOLERANCE)

**NEVER use synthetic, mocked, fabricated, placeholder, stubbed, or made-up data
ANYWHERE — not in code, not in fixtures, and NOT IN UNIT TESTS.** Every single number
must trace to a REAL source: the database, a real feed, a real instrument. Tests run
against REAL records pulled from the data layer — never invented inputs. No
default/neutral/stub score may stand in for a real computation. Do not introduce ANY
number that is synthetic or derived in nature without the FM's **explicit prior
knowledge and approval**.

*Why this is rule #0:* synthetic-data unit tests went green while the real catalyst
feed was broken — every filing-rich name scored 0, and fake test data hid a real defect
in a system that allocates capital. Definition-of-done gates MUST assert on REAL produced
output (e.g. `scripts/foundation/validate_lenses.py`), never on synthetic fixtures.

## Shape of the system

- **One database schema: `atlas_foundation`** (Supabase Postgres). There is no other
  data schema. Every read and write goes here. `scripts/ops/schema_gate.py` keeps it 0.
- **Ingestion (`scripts/foundation/`)** pulls from real sources only — Kite (OHLCV),
  NSE (bhavcopy/filings/bulk-deals), AMFI (NAV), Morningstar (holdings), screener.in
  (fundamentals). These are the ONLY external boundaries; nothing else calls off-box.
- **Compute (`atlas/` modulith + `scripts/foundation/compute_all.py`)** derives the
  lenses and composite; results land in `atlas_foundation`.
- **Board (`frontend/`)** is Next.js reading `atlas_foundation` directly via Supabase.
  No FastAPI backend, no internal-service HTTP calls — the board is self-contained.
- **Orchestrator: `scripts/ops/atlas_daily.sh`** (19:30 IST cron) runs the whole
  pipeline + gates + writes the health snapshot. Weekly/QA orchestrators alongside.
- **Migrations** are squashed to a single baseline (`migrations/versions/0001_baseline_*`
  = a verbatim dump of the live schema). Prod schema is managed directly, not by alembic.

## Architectural rules (some HOOK-ENFORCED — don't fight)

1. **Single schema.** All tables in `atlas_foundation`. No new schemas. No cross-schema refs.
2. **Self-contained.** No runtime dependency on any external service except the ingestion
   sources above. The frontend never proxies to an internal API.
3. **Modulith.** Each top-level `atlas/` package (`compute`, `intraday`, `lenses`) is a
   bounded context. No cross-context imports except via `atlas.primitives`/`atlas.db`/`atlas.config`.
4. **No hardcoded methodology numbers.** Every weight/threshold lives in
   `atlas_foundation.atlas_thresholds`, editable from `/admin/thresholds`.
5. **Decimal for money. Tz-aware datetimes.** Float-for-money is rejected by global hooks.
6. **Tiered file-size limits**: 600 LOC source / 800 LOC tests / 250 LOC page shells.
   Escape valve: `# allow-large: <reason>` (Python) / `// allow-large: <reason>` (TS).
7. A PreToolUse hook gates edits to `atlas/**`, `frontend/src/**`, `migrations/versions/**`
   until a planning skill (`/tdd`, `/grill-with-docs`, or `/plan-eng-review`) runs in the session.

## Deploy hygiene (a prod outage came from breaking this)

This box IS prod (pm2 `atlas-frontend-v3` :3004 + live Supabase). NEVER `pm2 reload` while a
build runs — it corrupts `.next` and 500s the board. Deploy = rebuild to completion → confirm
`frontend/.next/BUILD_ID` exists → `rm -rf .next/cache/fetch-cache` → **reload once**. Home/
sectors/stocks are static-ISR (the "as of" date bakes at build), so only a rebuild advances it.
Full post-mortem: `docs/deploy-hygiene.md`.

## Skill cadence — invoke BEFORE coding

| Situation | Skill |
|---|---|
| Bugfix or new feature | `/tdd` |
| New feature / module | `/plan-eng-review` (or `/grill-with-docs` for a mini review) |
| Refactor existing | `simplify` (and `/ponytail-review` the diff) |
| UI components | `frontend-design:frontend-design` |
| Unclear scope | `superpowers:brainstorming` |
| Before claiming done | `superpowers:verification-before-completion` |
| Pre-merge | `/review` + `/ponytail-review` (over-engineering) |
| Ship | `/ship` then `/land-and-deploy` |
| Stuck > 3 attempts | `/diagnose` |

## Pointers (read on demand)

- `CONTEXT.md` — domain glossary (auto-loaded with this file)
- `docs/refresh-schedule.md` · `docs/table-census.md` — the data pipeline + table inventory
- `docs/deploy.md` · `docs/deploy-hygiene.md` — deploy process + the outage post-mortem
- `docs/engineering-process.md` — CI gates (pragma coverage, pyright ratchet)
- `docs/health-audit-rules.md` — compute/frontend/arch audit guardrails
- `docs/adr/` — architecture decision records · `docs/agents/` — agent-workflow conventions
- `decisions.jsonl` — append-only hash-chained decision log

## Local workspace (NEVER under iCloud)

The git tree MUST live outside any iCloud-synced folder — iCloud "Optimize Mac Storage"
evicts `.git` pack objects and corrupts the repo (`pack … far too short to be a packfile`).
Canonical local path: **`~/dev/atlas-os`**.

## What goes in this file

Atlas-only conventions, paths, and pointers — not a copy of global rules. Keep it under
120 lines; long CLAUDE.md files dilute their own enforcement.
