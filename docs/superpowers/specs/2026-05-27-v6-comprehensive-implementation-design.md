# v6 Comprehensive Implementation Spec — 2026-05-27

## Goal

Get **all 12 mockup pages** from `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/` live on `atlas.jslwealth.in`, at root URLs, with locked design fidelity and **no remaining backend data gaps** for any mockup-required data point.

This spec supersedes my earlier "rebuild plan" (95431fa4) and the LOCKED-12-mockup-implementation-plan (ae6170bf), both of which were piecemeal and missed the backend scope.

## Decisions (signed off via brainstorming)

1. **Scope = all 12 mockups.** No deferrals.
2. **Backend = three backfills:** macro ingest + sector 5y + ETF 34→126 expansion.
3. **Frontend architecture = base-table reads.** No new MVs in this round. The 3 missing pages query `atlas_*` base tables directly via query modules — matching the pattern of the 9 existing pages. The canonical 14-MV vision is deferred as performance optimisation.
4. **URLs = root only.** `/regime`, `/sectors`, `/markets-rs`, `/calls`, `/india-pulse` etc. `/v6/*` prefix retired with 308 redirects.
5. **Fidelity bar = "spirit + every section":** every major mockup section present on the page, layout faithful, locked design tokens (paper/ink/teal palette + Source Serif 4 / Inter / JetBrains Mono), existing 114 components in `frontend/src/components/v6/` reused (no parallel implementations).

## Architecture

### Frontend stack (locked per yesterday's plan)

Next.js 15.3.9 App Router · React 19 · postgres-js 3.4.5 (session-mode Supabase pooler) · Tailwind v4 `@theme` tokens · **Recharts 3.8** · D3 v7 · Radix Tooltip · `@tanstack/react-virtual` · Vitest + Testing Library · Playwright + axe-core.

### Page pattern (canonical, used by all 12 pages)

```
frontend/src/app/<route>/page.tsx          (RSC shell ≤250 LOC, hook-enforced)
  → imports query modules from lib/queries/v6/
  → fetches data in parallel via Promise.all()
  → renders <SomethingClient> from components/v6/
  
frontend/src/components/v6/<Something>Client.tsx   (client component, all rendering)
  → composes existing v6 primitives + layout components
  → URL persistence via lib/v6/persistence.ts hooks (STATE.md contract)
```

### Backend pattern

- `atlas_*` tables on Supabase (the 30-table contract) are the read layer
- Pages query base tables via postgres-js template tags
- Backfills run on EC2 (Mac psycopg2 broken per `[[ec2-access]]` memory)
- `pg_cron` schedules nightly refreshes for derivations + MVs that exist

---

## Backend work

### B.1 Macro ingest jobs (new code)

Six NULL columns on `atlas_macro_daily` need writers:

| Column | Source | Historical depth | Approach |
|---|---|---|---|
| `us_10y_yield` | FRED series `DGS10` | 1962+ | FRED API (free, requires key) → daily Python ingest |
| `india_10y_yield` | FRED series `INDIRLTLT01STM` (monthly) OR RBI weekly | 2003+ | FRED API |
| `dii_flow` | NSE bhavcopy `MA_F_FIIDII_<DATE>.csv` (DII row) | 2007+ | NSE archive download + parse |
| `fii_cash_equity_flow_cr` | Same NSE bhavcopy (FII cash equity row) | 2007+ | Same script as `dii_flow` |
| `cpi_yoy` | MOSPI monthly index → YoY % calc | 2011+ | MOSPI CSV download + transform |
| `brent_inr` | `de_global_prices.BZ=F` × `atlas_macro_daily.usdinr` | ⚠️ BZ=F only 18 rows in DB | Need: yfinance backfill of BZ=F OR FRED `DCOILBRENTEU` (1987+) |
| `vix_9d` | NSE India VIX historical CSV | 2014+ | NSE archive (note: NSE may not publish 9d separately; may compute from India VIX rolling) |
| `risk_free_91d` | RBI 91-day T-bill yield | 2000+ | RBI weekly bulletin parse OR FRED `INDIRR1Y` proxy |

**Scope deliverable B.1:**
- Five Python ingest scripts under `atlas/ingest/macro/`:
  - `fred_ingest.py` — pulls US 10Y, India 10Y, Brent (FRED), risk-free
  - `nse_bhavcopy_ingest.py` — pulls FII + DII daily flow
  - `mospi_cpi_ingest.py` — pulls CPI monthly → YoY transform
  - `nse_vix_ingest.py` — pulls India VIX + 9d
  - `runner.py` — orchestrates all four with backfill + incremental modes
- Each writes to `atlas_macro_daily` via UPSERT on `date` PK
- `pg_cron` schedule: nightly 20:15 IST after market data lands
- Initial backfill: from 2016-01-01 (min date in `atlas_macro_daily`)

**Acceptance:** All 8 NULL columns populated at ≥95% coverage from 2016-01-01 to today. Pre-flight test: query `SELECT date, count of non-null cols FROM atlas_macro_daily WHERE date > 2020-01-01` → all 8 cols ≥95%.

### B.2 Sector 5-year backfill (existing writer extension)

`atlas_sector_metrics_daily` has 74,752 rows but 8 columns added by migration 097 are NULL:
- `rs_1w`, `rs_1m`, `rs_6m`, `rs_12m` — sector returns minus Nifty 500 return per window
- `pct_above_ema20`, `pct_above_ema200` — % of sector constituents above 20/200 day EMA
- `pct_52wh` — % of sector constituents within 5% of 52-week high
- `hhi` — Herfindahl-Hirschman concentration index across sector constituents

**Scope deliverable B.2:**
- Extend `atlas/compute/sectors.py` (existing module) to compute the 8 new columns
- 5-year backfill via `scripts/sector_5y_backfill.py` (one-off run on EC2)
- ~640k cell writes (31 sectors × 2575 trading days × 8 cols)
- Add to nightly cron going forward

**Acceptance:** All 8 cols ≥95% non-null for dates ≥ 2016-04-07.

### B.3 ETF scorecard expansion 34 → 126 (existing writer)

`atlas_etf_scorecard` is at 34 leader rows. Universe `atlas_universe_etfs` has 126 ETFs. The scorecard writer needs to run over all 126.

**Scope deliverable B.3:**
- Confirm `atlas/compute/etf_scorecard.py` (or wherever the writer lives) handles full universe; remove any "leaders only" filter
- One-off expansion run on EC2 → writes 92 new rows
- Add to nightly cron going forward
- Also backfills the 3 new cols from migration 097: `premium_bps`, `te_60d`, `adv_20d_inr`

**Acceptance:** `SELECT COUNT(*) FROM atlas.atlas_etf_scorecard` returns 126. New cols ≥95% non-null.

---

## Frontend work

### F.0 Audit existing 9 pages against mockups

For each of: `/regime`, `/v6/sectors`, `/v6/sectors/[name]`, `/v6/stocks`, `/v6/stocks/[iid]`, `/v6/funds`, `/v6/funds/[code]`, `/v6/etfs`, `/v6/etfs/[iid]`:

**Process:**
1. Open the live route on `atlas.jslwealth.in`
2. Open the corresponding mockup HTML
3. Section-by-section visual diff via `/design-review` skill
4. Record gaps in `docs/v6/audits/2026-05-27-<page>-gap-report.md`

**Output:** 9 gap reports + 1 summary file `docs/v6/audits/2026-05-27-audit-summary.md`. No code changes.

### F.1 Build /markets-rs (mockup 03)

**Page structure per mockup:**
- Page-head: title "Markets relative strength", sub explaining 9 baselines × 5 windows
- 4-card hero readout: Today's leadership, India vs world, Within India, India RS grade (A/B/C/D)
- 9-baseline × 5-window RS grid (1w/1m/3m/6m/12m + rank pills)
- Narrative-card with 5 LEADER/LAGGARD/ROTATION rows
- Detail-chart grid: 2-column, ≤8 multidim charts, layer toggles (S/R / RS / VOL / 20D-MA)

**Data sources (base tables):**
- `atlas.mv_markets_rs_grid` already live (9 baselines × 5 windows of return + rank)
- `de_index_prices` + `de_global_prices` for detail-chart series
- `atlas_macro_daily.usdinr` for FX-adjusting foreign baselines

**Components to reuse:**
- `RegimeHero` pattern for the 4-card hero (or extract into new `MarketsRsHero` if shape diverges)
- `MultiBenchmarkRSWaterfall` for the RS grid
- `PerWindowChart` for the multidim detail charts
- `ChipControl` for layer toggles

**Route:** `/markets-rs`. Page-shell ≤250 LOC. Client component in `frontend/src/components/v6/MarketsRsClient.tsx`.

### F.2 Build /calls (mockup 08)

**Page structure per mockup:**
- Page-head: "Calls Performance · YTD 2026 · N fired calls · ledger T+1 onwards"
- 6-tile hero-stats: YTD realized excess, win rate, total fired, closed, open, avg holding
- 4-up story-block: Best closed today / Worst closed today / Open standouts / Cell drift flags
- Cumulative realized excess landscape chart (with ±1σ ribbon + regime-flip markers)
- 24-cell win-rate matrix (3 tier × 4 tenure × 2 dir)
- 6 cell-IC trajectories (30-day rolling)
- 6 rich cell cards
- 1,847-row ledger table (column chooser, virtualised)
- Methodology section

**Data sources (base tables + existing MV):**
- `atlas.mv_calls_performance` (363 rows live)
- `atlas_signal_calls` for richer detail
- `atlas_ledger` (currently empty; fills as tenures expire)
- `atlas_signal_weights_live_perf` for calibration scatter

**Components to reuse:**
- `RecentSignalCalls` (closest existing)
- `CellMatrix` for the 24-cell win-rate matrix
- `StocksTableV6` pattern for the 1,847-row ledger (virtualised already)

**Route:** `/calls`. Client component `frontend/src/components/v6/CallsPerformanceClient.tsx`.

### F.3 Build /india-pulse (mockup 02) — depends on B.1 macro backfill

**Page structure per mockup:**
- Page-head: "India Pulse" + breadcrumb
- 4-tile hero-strip: Small-cap RS Z-score, Breadth %>200DMA, India VIX, Cross-section dispersion
- Headline indices grid: 8 cards (Nifty 50/100/Midcap 150/Smallcap 250/Nifty 500/Bank/IT/Gold)
- Dense breadth table: 9 measures × Today + Δ1w/1m/3m + Position pbar + 3M spark + reads-as commentary
- Dispersion & concentration: 2-up charts
- Volatility: 3-up (VIX spot, 5y percentile, term-structure)
- Tier leadership chart
- 22-sector heatmap (window 1W/1M/3M)
- 8 macro cards: USD/INR, India 10Y, Brent ₹, Real yield, FII flow, DII flow, US 10Y, DXY

**Data sources (base tables, post-B.1):**
- `atlas_macro_daily` (all 8 columns populated by B.1)
- `atlas_market_regime_daily` for breadth/AD/McClellan
- `atlas_index_metrics_daily` for headline indices
- `atlas_sector_metrics_daily` for 22-sector heatmap
- `atlas_stock_metrics_daily` aggregated for dispersion + concentration

**Components to reuse + extend:**
- Existing `BreadthSection`, `BreadthCategory`, `BreadthIndicators` components
- `SectorBreadthPanel` (already on /v6/sectors)
- `BreadthWaterfall` for the dense breadth table
- May need new `MacroCard` component if no equivalent exists (8 cards)
- May need new `DispersionChart` / `ConcentrationStackedBar` if not in v6/

**Route:** `/india-pulse`. Client component `frontend/src/components/v6/IndiaPulseClient.tsx`.

### F.4 Close audit gaps from F.0

For each per-page gap report from F.0:
- If gap = missing section → add the section, reusing existing components
- If gap = wrong data → fix query module
- If gap = visual / token mismatch → fix Tailwind classes against locked tokens
- If gap = missing component → check `frontend/src/components/v6/` first; only build if genuinely absent (`feedback_check_v6_components_first` memory rule)

`/design-review` after each fix.

### F.5 URL migration `/v6/*` → root

**Move map:**
| From | To |
|---|---|
| `/v6/today` | `/today` (or fold into `/regime`) |
| `/v6/sectors` | `/sectors` |
| `/v6/sectors/[name]` | `/sectors/[name]` |
| `/v6/stocks` | `/stocks` |
| `/v6/stocks/[iid]` | `/stocks/[iid]` |
| `/v6/funds` | `/funds` |
| `/v6/funds/[code]` | `/funds/[code]` |
| `/v6/etfs` | `/etfs` |
| `/v6/etfs/[iid]` | `/etfs/[iid]` |
| `/v6/cells/[cell_id]` | `/cells/[cell_id]` |
| `/v6/screening` | `/screening` |
| `/v6/markets-rs` (NEW) | `/markets-rs` |
| `/v6/calls` (NEW) | `/calls` |
| `/v6/india-pulse` (NEW) | `/india-pulse` |

**Execution:**
- `git mv` each route directory atomically
- `git grep -l '/v6/'` to find every internal link; update via `sed`
- Update `TopNav.tsx` GROUPS array
- Add Next.js `redirects()` config: `/v6/:path*` → `/:path*` (308)
- Retire legacy `/sectors`, `/stocks`, `/etfs`, `/funds` v5-era pages (already deleted per earlier session, but verify)
- `tsc --noEmit` + manual smoke before commit

### F.6 Deploy mechanism cleanup

`/home/ubuntu/atlas-frontend-v2/` is currently a non-git rsync target. Convert to git checkout:
- `cd ~ && git clone https://github.com/nimishshah1989/atlas-os.git atlas-frontend-v2-new`
- Move `.env.local`, `.next/`, `node_modules/` from old dir
- `pm2 delete atlas-frontend-v2 && pm2 start ecosystem.config.js`
- Verify nginx upstream still points to 3002
- Future deploy: `git pull && npm run build && pm2 restart atlas-frontend-v2`

---

## Execution sequencing

```
Phase A (~3 days, parallel tracks):
├─ EC2 backend: B.1 macro ingest + B.2 sector backfill + B.3 ETF expansion (3 parallel SSH sessions OR sequential if mac context-switching)
└─ Local: F.0 audit 9 pages (subagent-dispatched, runs in parallel with backend)

Phase B (~2-3 days, parallel):
├─ F.1 build /markets-rs (no backend dep; mv_markets_rs_grid live)
└─ F.2 build /calls (no backend dep; mv_calls_performance live)

Phase C (~2 days, depends on Phase A B.1 + B.2 + B.3):
├─ F.3 build /india-pulse (needs B.1 macro data)
└─ F.4 close gaps from F.0 audit (uses B.2 sector data, B.3 ETF data)

Phase D (~1 day, depends on B + C):
├─ F.5 URL migration with redirects
└─ Verify all 12 routes return 200

Phase E (~0.5 day):
└─ F.6 deploy mechanism cleanup
```

**Wall-clock total: ~8-10 focused days.** Parallelism saves ~3-4 days vs strict serial.

---

## Skill cadence (non-negotiable)

Per page in F.1, F.2, F.3, F.4:
1. **Read mockup HTML** line by line. No skim.
2. **Check `frontend/src/components/v6/`** for existing components (`[[check-v6-components-first]]` memory).
3. **`superpowers:writing-plans`** → per-page plan in `docs/superpowers/plans/2026-05-27-<page>-page.md`.
4. **`superpowers:subagent-driven-development`** dispatches per component / section.
5. **`/design-review`** against mockup HTML — visual diff, not "does it compile."
6. **`/review` + `/codex review`** pre-merge.
7. **SSH deploy** (`ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214`) — no paste-back loops.

For backend tasks B.1, B.2, B.3:
1. **`/grill-with-docs`** to lock terminology against CONTEXT.md.
2. **`superpowers:writing-plans`** for the ingest script architecture.
3. **TDD per script** — write tests against fixture data first.
4. **`/review`** pre-commit.

---

## Architectural rules (hook-enforced reminders)

- 600 LOC source / 800 LOC test / 250 LOC page-shell limits
- Decimal for money; tz-aware datetimes; no float
- Bounded-context imports only via `atlas.primitives`, `atlas.db`, `atlas.config`
- `atlas.atlas_thresholds` for all methodology constants (no hardcoded numbers)
- `apply_migration` MCP tool is denied; use Alembic (already at head 098)
- Supabase MCP write: needs `.supabase-write-approved` marker (consumed per execution)
- No `--no-verify`; use `FORGE_ALLOW_LOW_COVERAGE=1` if pragma coverage hook hangs

---

## Acceptance criteria (single-sentence test per phase)

| Phase | Acceptance |
|---|---|
| A.B.1 macro | All 8 macro cols on `atlas_macro_daily` ≥95% non-null from 2016-01-01; mockup 02 macro cards render with real values |
| A.B.2 sector | All 8 new sector cols on `atlas_sector_metrics_daily` ≥95% non-null from 2016-04-07; mockup 04 sector table renders all column values |
| A.B.3 ETF | `atlas_etf_scorecard` at 126 rows; mockup 07 ETF table shows all 126 |
| A.F.0 audit | 9 gap reports written; summary identifies which pages need 0 / minor / major work |
| B.F.1 markets-rs | `/markets-rs` returns 200; visual diff vs mockup 03 passes |
| B.F.2 calls | `/calls` returns 200; visual diff vs mockup 08 passes |
| C.F.3 india-pulse | `/india-pulse` returns 200; visual diff vs mockup 02 passes; macro cards show real values |
| C.F.4 gap fixes | All 9 audited pages pass `/design-review` against their mockups |
| D.F.5 URLs | All 12 routes live at root URLs; `/v6/*` redirects 308 to root |
| E.F.6 deploy | `cd ~/atlas-frontend-v2 && git pull && npm run build && pm2 restart` works |

---

## What's explicitly NOT in this round

- **5 sector MVs** (mv_sector_cards/breadth/rrg/deepdive) — pages query base tables; MVs are performance opt for later
- **2 ETF MVs** (mv_etf_list_v6, mv_etf_deepdive) — same reasoning
- **mv_stock_landscape, mv_markets_rs_detail_charts** — page F.1 queries base tables directly
- **mv_india_pulse** — page F.3 queries `atlas_macro_daily` + others directly
- **`/v6/cells/[cell_id]` deep-dive** is fine; no separate cell-rule deep-dive (per Vocabulary lock)
- **AuditTrailTab Section 6** — deferred per yesterday's eng-review decision
- **TopNav redesign** — keep existing component; only hrefs change

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| FRED API quota or downtime during backfill | Cache responses; backfill in batches; retry with exponential backoff |
| NSE bhavcopy format changes (historically has) | Parse defensively; alert on schema diff; manual recovery if needed |
| Existing pages diverge from mockups by MORE than minor gaps | Audit (F.0) identifies this early; F.4 budget grows; flag to user immediately |
| ETF scorecard expansion writer has bugs surfacing only at full-universe scale | Run on 10% sample first; verify before full 126 |
| URL migration breaks deep-search-era links scattered in DB content / queries | Pre-flight grep; staged migration with route stubs that redirect |
| Sector backfill compute exceeds EC2 memory (640k row writes) | Batch by year; `to_sql(method='multi', chunksize=5000)` |
| auto-mode classifier blocks SSH again | User adds explicit permission rule (already discussed; user opted for case-by-case re-confirms) |

---

## Sign-off

This spec is the single source of truth for the v6 12-mockup ship. Execution starts ONLY after user reviews this file + signs off.

Any change to scope (12-mockup roster), architecture (base-table reads), fidelity bar, URLs, or sequencing requires editing this document FIRST.

Next step after sign-off: `superpowers:writing-plans` produces the executable tasklist.
