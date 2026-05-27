# v6 12-Mockup Implementation Plan — LOCKED 2026-05-27

> **Source of truth.** Written after a session-long failure where I built parallel pages that diverged from the locked mockups. This document supersedes my earlier "rebuild plan" (95431fa4). Strict execution against this list only.

---

## Locked scope (signed off 2026-05-27)

The 12 mockup HTMLs in `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/` are the canonical design spec. All implementations must match each mockup's look, feel, design, colors, components, and overall appearance — pragmatic fidelity, not pixel-exact.

| # | Mockup | Target URL | Build status | Backend | This round? |
|---|---|---|---|---|---|
| 01 | `01-market-regime.html` | `/regime` | ✅ Built (D.9) | ✅ MV live | Audit + close gaps |
| 02 | `02-india-pulse.html` | `/india-pulse` | ❌ Not built | ❌ Blocked C2 | **DEFERRED — next round** |
| 03 | `03-markets-rs.html` | `/markets-rs` | ❌ Not built | ✅ MV live | **BUILD** |
| 04 | `04-sectors.html` | `/sectors` | ✅ Built (D.3, currently at `/v6/sectors`) | ✅ MV live | Move to `/sectors` + audit |
| 04a | `04a-sector-energy.html` | `/sectors/[name]` | ✅ Built (D.4, currently at `/v6/sectors/[name]`) | ✅ MV live | Move to `/sectors/[name]` + audit |
| 05 | `05-stocks.html` | `/stocks` | ✅ Built (currently at `/v6/stocks`) | ✅ MV live | Move + audit |
| 05a | `05a-stock-reliance.html` | `/stocks/[iid]` | ✅ Built (C.16, at `/v6/stocks/[iid]`) | ✅ MV live | Move + audit |
| 06 | `06-funds.html` | `/funds` | ✅ Built (D.5, at `/v6/funds`) | ✅ MV live | Move + audit |
| 06a | `06a-fund-ppfas.html` | `/funds/[code]` | ✅ Built (D.6, at `/v6/funds/[code]`) | ✅ MV live | Move + audit |
| 07 | `07-etfs.html` | `/etfs` | ✅ Built (D.7, at `/v6/etfs`) | ✅ MV live | Move + audit |
| 07a | `07a-etf-goldbees.html` | `/etfs/[iid]` | ✅ Built (D.8, at `/v6/etfs/[iid]`) | ✅ MV live | Move + audit |
| 08 | `08-calls-performance.html` | `/calls` | ❌ Not built | ✅ MV live | **BUILD** |

**This round: 11 of 12 mockups live at their canonical root URLs.** India-pulse deferred to next round (needs Phase C2 backend backfill first).

---

## Fidelity bar (signed off)

> Pixel-exact is not required. The look, feel, design, colors, all the components, and how it appears in the mockup — that's how it should be there.

Acceptance criteria per page:
1. Every major section from the mockup HTML is present on the page.
2. Layout (column order, hero shape, table structure, chart placement) matches the mockup.
3. Color palette + typography come from the locked design tokens (paper/ink/teal/signal palette + Source Serif 4 / Inter / JetBrains Mono).
4. The same v6 components from `frontend/src/components/v6/` are used — no parallel implementations.
5. Data is real (from MVs), not synthetic.
6. `/design-review` skill passes against the mockup HTML.

---

## URL strategy (signed off)

Root URLs only. `/v6/*` prefix retired. Migration:
- `/v6/today` → kept (or merged into `/regime` if companion); decide during execution
- `/v6/sectors` → `/sectors` (legacy `/sectors/page.tsx` retired)
- `/v6/sectors/[name]` → `/sectors/[name]`
- `/v6/stocks` → `/stocks` (legacy retired)
- `/v6/stocks/[iid]` → `/stocks/[iid]`
- `/v6/funds` → `/funds`
- `/v6/funds/[code]` → `/funds/[code]`
- `/v6/etfs` → `/etfs`
- `/v6/etfs/[iid]` → `/etfs/[iid]`
- `/v6/cells/[cell_id]` → `/cells/[cell_id]`
- `/v6/screening` → `/screening`
- New: `/markets-rs`, `/calls`

Legacy v5-era routes at the same URLs (`/sectors/page.tsx`, `/stocks/page.tsx`, `/etfs/page.tsx`, `/funds/page.tsx`) get **replaced** with the v6 implementations. The `_components/` siblings + queries follow.

---

## Execution tasklist

### Phase 0 — Audit (1 day) — done FIRST, blocks nothing else

| Task | Output |
|---|---|
| 0.1 | For each of 9 built pages (01, 04, 04a, 05, 05a, 06, 06a, 07, 07a): screenshot live route + open mockup HTML + visual diff. Use `/design-review` skill. |
| 0.2 | Per page, produce a `docs/v6/audits/2026-05-27-<page>-gap-report.md` listing every section/element missing or diverged. |
| 0.3 | Aggregate into `docs/v6/audits/2026-05-27-audit-summary.md` — per-page status (clean / minor / major gaps) + total gap-fix effort estimate. |
| 0.4 | Commit + push. |

**Acceptance:** 9 gap reports + 1 summary. No code changes.

### Phase 1 — Build 2 missing pages (3-4 days)

#### 1.A — `/markets-rs` (mockup 03) — ~1.5 days

| Task | Detail |
|---|---|
| 1.A.1 | Read `03-markets-rs.html` line by line. Identify every component, every data field, every interaction. |
| 1.A.2 | Map each mockup component → existing v6 component in `frontend/src/components/v6/`. List any TRULY new components needed (likely 0-2; the 9×5 RS grid + narrative card may already exist as `MultiBenchmarkRSWaterfall` variants). |
| 1.A.3 | Write `docs/superpowers/plans/2026-05-27-markets-rs-page.md` via `superpowers:writing-plans` skill — exhaustive per-section breakdown. |
| 1.A.4 | If any truly new components: build them via `superpowers:subagent-driven-development` (one subagent per component). |
| 1.A.5 | Build query module `frontend/src/lib/queries/v6/markets_rs.ts` (snake_case per existing pattern in v6/) — types from MV schema, postgres-js Decimal→number coercion. |
| 1.A.6 | Build `frontend/src/app/markets-rs/page.tsx` (≤250 LOC RSC shell) + `MarketsRsClient.tsx` (all rendering). |
| 1.A.7 | `/design-review` against mockup. Iterate until fidelity bar met. |
| 1.A.8 | `/review` + `/codex review` pre-merge. Commit + push. |
| 1.A.9 | Deploy to EC2 via SSH. Verify `https://atlas.jslwealth.in/markets-rs` returns 200 and renders the mockup. |

#### 1.B — `/calls` (mockup 08) — ~1.5 days

| Task | Detail |
|---|---|
| 1.B.1 | Read `08-calls-performance.html` line by line. |
| 1.B.2 | Map mockup → existing v6 components. `RecentSignalCalls.tsx` is the closest existing; identify new components needed (likely: 24-cell win-rate heatmap matrix + cumulative excess landscape chart). |
| 1.B.3 | `superpowers:writing-plans` → `docs/superpowers/plans/2026-05-27-calls-page.md`. |
| 1.B.4 | Build new components via subagent-driven-development. |
| 1.B.5 | Build query module `frontend/src/lib/queries/v6/calls_performance.ts`. |
| 1.B.6 | Build `frontend/src/app/calls/page.tsx` + `CallsPerformanceClient.tsx`. |
| 1.B.7 | `/design-review` against mockup. Iterate. |
| 1.B.8 | `/review` + `/codex review`. Commit + push. |
| 1.B.9 | Deploy + verify `/calls` returns 200 and matches mockup. |

### Phase 2 — URL migration for 9 existing pages (~1 day)

Single batch — atomic move so no broken links mid-migration.

| Task | Detail |
|---|---|
| 2.1 | For each of 9 routes: `git mv frontend/src/app/v6/<page>/ frontend/src/app/<page>/` (or replace existing legacy `<page>/` with v6 contents). Document the moves in a single map. |
| 2.2 | `git grep -l '/v6/'` to find every `<Link href='/v6/...'>` and `router.push('/v6/...')` in the codebase. Update all to root URLs. |
| 2.3 | Update `TopNav.tsx` GROUPS array — replace all `/v6/*` hrefs with root URLs. |
| 2.4 | Run `tsc --noEmit` + visual scan to catch broken imports / references. |
| 2.5 | Add Next.js redirect rules in `next.config.js` for `/v6/*` → `/*` (so any cached browser tab + outbound links don't 404). |
| 2.6 | Commit + push. Deploy to EC2. Curl-verify each of the 11 routes returns 200. |

**Acceptance:** No `/v6/*` URL is canonical anymore. All 11 live routes are at root URLs. Old `/v6/*` URLs 308-redirect.

### Phase 3 — Close gaps from Phase 0 audit (1-3 days, scope-dependent)

For each page that scored "minor" or "major" gaps in the Phase 0 audit:

| Task | Detail |
|---|---|
| 3.x.1 | Read the per-page gap report. |
| 3.x.2 | If gaps require new components: `superpowers:writing-plans` → `superpowers:subagent-driven-development`. |
| 3.x.3 | Edit the page + components in place. Use existing v6 components where possible — never duplicate. |
| 3.x.4 | `/design-review` against mockup. Iterate until fidelity bar met. |
| 3.x.5 | `/review` + `/codex review`. Commit. |
| 3.x.6 | Deploy + verify. |

### Phase 4 — Deploy mechanism cleanup (0.5 day, last)

| Task | Detail |
|---|---|
| 4.1 | Replace `/home/ubuntu/atlas-frontend-v2/` (non-git rsync target) with a git checkout of `atlas-os`. Symlink or refactor so future deploys are `cd ~/atlas-frontend-v2 && git pull && npm run build && pm2 restart atlas-frontend-v2`. |
| 4.2 | Document the new deploy procedure in `docs/v6/deploy.md`. |

---

## Hard rules (mine to follow, yours to enforce)

1. **No code changes outside this tasklist.** If something I encounter needs deviation, I stop and ask.
2. **Always check `frontend/src/components/v6/` BEFORE writing UI** — 114 components live there. Memory entry `[[check-v6-components-first]]` is the load-bearing reminder.
3. **Mockup HTML is read line-by-line before each page build.** No "I have the gist."
4. **Skill cadence per page is non-negotiable:** read mockup → writing-plans → subagent-dev → design-review → review/codex → ship.
5. **Deploy via SSH on EC2** (`ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214`). No paste-back loops.
6. **One commit per logical step.** No mass commits.
7. **Memory updates as I learn things** — not at session end.

---

## What's NOT in this round (explicit deferrals)

- **Mockup 02 india-pulse** — deferred until Phase C2 backend backfill (NSDL DII, FRED US10Y, MCX Brent, MOSPI CPI, NSE VIX9 ingest) is done. Document the deferral in `docs/v6/2026-05-27-india-pulse-deferred.md`.
- **Phase B/C backend work** — `atlas_etf_scorecard` 34→126, sector 5-yr backfill of 8 new cols, ETF + sector MVs. None of these block the 11-of-12 scope this round.
- **Storybook / component demo route** — not needed; the v6 components exist and are exercised by their pages.
- **TopNav redesign** — the existing TopNav stays; only the hrefs change in Phase 2.

---

## Estimated total wall-clock

- Phase 0 audit: **1 day**
- Phase 1 build (markets-rs + calls): **3 days**
- Phase 2 URL migration: **1 day**
- Phase 3 gap fixes: **1-3 days** (depends on what audit finds)
- Phase 4 deploy mechanism: **0.5 day**

**Total: 6-9 focused days.**

Parallelizable: Phase 0 audit + Phase 1.A markets-rs can overlap (different subagents). Phase 2 is strictly after Phase 1 (URL migration must include the new routes).

---

## Sign-off

Plan locked 2026-05-27. Execution starts ONLY after explicit user approval ("go" or equivalent). Any change to scope, fidelity bar, URL strategy, or deferral requires editing this document first.
