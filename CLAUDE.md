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

Discovery-first equity-intelligence boards: nightly REAL market data → lens scoring → glass-box Next.js board over
Supabase Postgres. Two platforms: **Atlas India** (`atlas_foundation`, `frontend/`) and **Global Atlas** (US S&P 500 + ETFs:
`atlas_global`, `atlas/global_market/`, `scripts/global_market/`, `frontend-global/`; `docs/global/`). Keep this file ≤60 lines.
<!-- gstack:verify: make gate -->

## ⛔ RULE #0 — NO SYNTHETIC OR DERIVED DATA (zero tolerance)

Never use synthetic, mocked, placeholder or stubbed data — not in code, fixtures, or unit tests. Every
number traces to a real source; tests assert on REAL records; no default score stands in for a computation;
any synthetic/derived number needs the FM's explicit prior approval. (Fake test data once went green while the
real catalyst feed scored every filing-rich name 0.) Gates assert on produced output: `validate_lenses.py`, `validate_global.py`.

## Shape

- **One schema per market, zero cross-schema references** (`scripts/ops/schema_gate.py --market`; ADR-0006).
- Ingestion (`scripts/foundation/`, `atlas/global_market/providers/`) is the ONLY off-box boundary. India: Kite, NSE,
  AMFI, Morningstar, screener.in. Global: Alpaca, SEC EDGAR, issuer holdings CSVs, Nasdaq Trader, FRED (+ Stooq CSVs).
- `atlas/` is a modulith: each top-level package is a bounded context; cross-context imports only via
  `atlas.primitives`/`atlas.db`/`atlas.config` or an edge declared in `scripts/hooks/check_module_boundaries.py`.
- Boards read Postgres directly — no internal APIs, no Python spawned from route handlers. India: pm2
  `atlas-frontend-v3` :3004 on the box. Global: Vercel, transaction pooler, auth on from day one.
- Orchestrators `scripts/ops/atlas_daily.sh` (16:00 IST) and `atlas_global_daily.sh` (01:00 UTC): gates withhold
  publish; every guarded table names its producer (`freshness_guard.py` + `test_producer_registry.py`).
- Migrations: `0001_baseline_*` (verbatim prod dump) + `0002_atlas_global`. Prod DDL is managed directly.

## Rules (hook-enforced where marked)

1. No hardcoded methodology numbers — every weight/threshold lives in `<schema>.atlas_thresholds` (hook).
2. Decimal for money (INR/USD); tz-aware datetimes (IST / America/New_York). Float-for-money is rejected (hook).
3. File-size tiers 600 source / 800 tests / 250 page shells; escape valve `# allow-large: <reason>` (hook).
4. Model proposes, deterministic code executes — every LLM step. The repo is PUBLIC: no keys, positions, client data.
5. The box IS prod: never `pm2 reload` mid-build — rebuild → `.next/BUILD_ID` → clear fetch-cache → reload once.

## Workflow

Code on the laptop (`~/All AI/atlas-os`, never under iCloud), never on the box. `make gate` (lint + unit +
pyright ratchet, ~7s; not `make check`) → branch → PR → merge `main` → the box fast-forwards. Codebase
questions: `graphify query "…"` first (`graphify-out/`, rebuilt by `.claude/hooks/session-start.sh`). Details
and tooling install: `docs/dev-workflow.md`. Pointers: `CONTEXT.md` (glossary) · `docs/global/` · `docs/adr/` ·
`docs/refresh-schedule.md` · `docs/table-census.md` · `docs/deploy.md` · `docs/deploy-hygiene.md` ·
`docs/engineering-process.md` · `docs/health-audit-rules.md` · `decisions.jsonl` (hash-chained decision log).

| Situation | Skill (vendored in `.claude/skills/`; gstack installed by the session hook) |
|---|---|
| Bugfix / feature | `test-driven-development`; new module → `plan-eng-review` |
| Refactor | `simplify`, then `ponytail-review` the diff |
| UI · unclear scope · stuck > 3 tries | `frontend-design` · `brainstorming` · `investigate` |
| Done / ship | `verification-before-completion` → `review` → `ship` → `land-and-deploy` |
