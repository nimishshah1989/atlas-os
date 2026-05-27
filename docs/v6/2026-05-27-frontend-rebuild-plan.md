# v6 Frontend Rebuild Plan — 2026-05-27

> Written after the live deploy revealed my pages diverged from the locked mockups in `~/.gstack/projects/atlas-os/designs/v6-redesign-20260526-mockups/`. This plan locks the rebuild against those mockups and the LIVE Supabase backend audit performed 2026-05-27.

---

## Discipline (non-negotiable — these get me fired if skipped)

For **every** page, in order:
1. Read the mockup HTML line-by-line. Cite specific elements in the plan.
2. `superpowers:writing-plans` to produce a per-page plan that names every component, every data field, every interaction.
3. Build against the plan with `superpowers:subagent-driven-development` (one component per subagent).
4. `/design-review` against the mockup — visual diff, not "does it compile."
5. `/review` + `/codex review` pre-merge.
6. Deploy via SSH (now unblocked) — `git pull && rsync && npm run build && pm2 restart atlas-frontend-v2 && curl-verify`.

If at any step a page doesn't match its mockup, I stop and call it out — I don't ship "close enough."

---

## Backend audit summary (LIVE Supabase verified 2026-05-27)

**Complete (✅):**
- 30/30 v6 tables exist + populated
- 10+ years history on every time-series table (5-yr min comfortably met)
- 7 of 14 expected MVs live + populated
- Universes: 750 stocks · 592 funds · 126 ETFs · 75 indices · 31 sectors
- Migration head 098 matches canonical doc
- Repo clean (Conductor dupes + orphan tests purged in `b9b1f388`)

**Incomplete (per Phase B/C plan — needs EC2 Python compute):**
- `atlas_etf_scorecard` 34/126 (Phase C1.c)
- `atlas_sector_metrics_daily` missing 8 new cols across 5-yr backfill (Phase C1.d)
- `atlas_macro_daily` 5 new cols NULL: dii_flow, us_10y_yield, brent_inr, cpi_yoy, vix_9d (Phase C2)
- 7 MVs not yet built: `mv_india_pulse`, `mv_markets_rs_detail_charts`, `mv_sector_cards/breadth/rrg/deepdive`, `mv_stock_landscape`, `mv_etf_list_v6`, `mv_etf_deepdive`, `mv_fund_amc_ladder` (per index.html — not in canonical doc, may be folded into list MV)

---

## Page → backend readiness × mockup complexity

| # | Page | MV(s) needed | Backend ready? | Mockup sections | Est. complexity |
|---|---|---|---|---|---|
| 01 | Market Regime landing | `mv_market_regime_landing` | ✅ | hero 3-tile + 12-week journey + 4 pulse tiles + 6 cell cards + 3-tab conviction | **Medium** (tab JS + journey grid) |
| 02 | India Pulse | `mv_india_pulse` | ❌ blocked on C2 | 4 classifier inputs + 8 indices + 9-row breadth table + dispersion/concentration + volatility + tier leadership + 22-sector heatmap + 8 macro cards | **Heavy** (heatmap + tables) |
| 03 | Markets RS | `mv_markets_rs_grid` ✅, `mv_markets_rs_detail_charts` ❌ | partial | 4-card hero + 9×5 RS grid + narrative + multidim chart grid (≤8 visible) | **Heavy** (signature multidim) |
| 04 | Sectors | 5 MVs ❌ | blocked on C1.d | 3-block hero + RRG + 15-col heatmap table + 6 overweight cards | **Heavy** (RRG SVG + wide table) |
| 04a | Sector deep-dive | `mv_sector_deepdive` ❌ | blocked on C1.d | breadcrumb + page-stamp + 6-tile verdict + multidim + RS grid 5×6 + sub-industry decomp + 62 constituents + methodology + macro overlays | **Heavy** |
| 05 | Stocks list | `mv_stock_list_v6` ✅, `mv_stock_landscape` ❌ | partial | 6-tile hero + 4-up story + RS×Composite bubble + 24-cell matrix + trajectory grid + 6 rich picks + 750-row table | **Heavy** (bubble + matrix + 750 rows) |
| 05a | Stock deep-dive | `mv_stock_deepdive` ✅ | ✅ | 8 meta-chips + 6-tile verdict + multidim w/ cell fires + 365d cell-fire timeline + methodology + RS grid + peer set + fundamentals + open positions + macro + events | **Very heavy** |
| 06 | Funds list | `mv_fund_list_v6` ✅, (AMC ladder?) | mostly ✅ | 6-tile hero + 4-up story + AMC leaderboard + quartile heatmap + trajectory grid + 6 rich + 587-table | **Medium-Heavy** |
| 06a | Fund deep-dive | `mv_fund_deepdive` ✅ | ✅ | 8 meta-chips + 6-tile verdict + rolling 3Y + drawdown + top10/allocation/attribution + peer + 60-month quartile transition + SWITCH rule | **Heavy** |
| 07 | ETFs list | `mv_etf_list_v6` ❌ | blocked on C1.c | 6-tile hero + 4-up story + category bands + AMC tile row + NAV-vs-price scatter + 6 cards + 34-table | **Medium-Heavy** |
| 07a | ETF deep-dive | `mv_etf_deepdive` ❌ | blocked on C1.c | 8 meta-chips + 6-tile verdict + multidim + premium distribution + TE rolling + composition + cost stack + peer + macro | **Heavy** |
| 08 | Calls Performance | `mv_calls_performance` ✅ | ✅ | 6-tile hero + 4-up story + cumulative excess landscape + 24-cell win-rate matrix + 6 cell-IC trajectories + 6 rich + 1,847-row ledger | **Very heavy** |

**Backend-ready right now (5 pages):** 01, 05a, 06, 06a, 08
**Backend-partial (2 pages):** 03, 05
**Backend-blocked (5 pages):** 02, 04, 04a, 07, 07a

---

## Shared design system (build ONCE, reuse everywhere)

### Tokens (lock in `frontend/tailwind.config.ts`)

```
paper:        #F8F4EC    paper-soft:   #FBF8F1    paper-deep:   #F1ECDF
paper-rule:   #C2B8A8    ink-rule:     #DDD3BF
ink:          #1A1714    ink-2:        #3D362E    ink-3:        #6B6157    ink-4: #9A8F82
signal-pos:   #2F6B43    signal-neg:   #B0492C    signal-warn:  #B8860B    signal-info: #3E5C76
accent:       #25394A    teal:         #1D9E75

font-serif: 'Source Serif 4'    font-sans: 'Inter'    font-mono: 'JetBrains Mono'
H1: 56px (landing) / 44px (everything else)    section-title: 26-28px    card: 18px    body: 14px    eyebrow: 10-11px (uppercase, ls 0.18-0.22em)
Border radius: ALWAYS 2px (no rounded corners except dots)
```

### Components (~34 unique)

**5 primitives** (locked per index.html spec):
- `<InfoTooltip />` (i circle + hover tooltip)
- `<RAGChip variant={pos/neg/warn} fill={soft/strong} />`
- `<SegmentedDots n={5} filled={X} label="X/5" />`
- `<ActionVerb action={BUY/AVOID/WATCH/SWITCH_IN/SWITCH_OUT/HOLD/OW/NW/UW} />`
- `<ClickableCard href onClick />` (hover bg/border shift)

**12 layout/structural**: TopNav, PageHead (breadcrumb+title+sub+stamp+meta), MockupBanner (amber strip — KEEP until pages are signed off), SectionHead, HeroStrip4Tile (01,02), HeroStats6Tile (05,06,07,08), VerdictStrip6Tile (04a,05a,06a,07a,08), StoryBlock4Up (04,05,06,07,08), MetaChipRow (8 chips), PageStamp (verdict badge), Footnote, BreadcrumbNav.

**12 chart/data viz** — most important first:
1. **MultidimChart** (THE signature — 03, 04a, 05a, 07a + mini variants on 05/06/07 cards): PRICE lane + RS-strip + VOL lane on shared time axis, S/R dashed, RS diamond markers, 20D-MA overlay, optional cell-fire vertical annotations. Use **Apache ECharts** (mockup index says "Recharts→ECharts" — was a known migration).
2. SparkSvg (60-280px inline trend)
3. RSGrid (9-row × 5-col or 5×6 with rank pills)
4. HeatmapTable (15-col, column chooser, cell colour-shaded by signal-pos/neg opacity .10/.25/.45)
5. HeatmapGrid (22-sector or 24-cell)
6. RRG (4 quadrants + bubbles + 6-week trail)
7. BubbleChart (RS×Composite, mcap-sized, 4 quadrants)
8. AmcLadderStackedBar (Q1/Q2/Q3/Q4 stacks)
9. ConcentrationStackedBar (top10 / 11-50 / 51-200 / bottom300)
10. PremiumDiscountScatter (log-y + ±25bps band tints)
11. JourneyGrid (12-week × 5-row CSS grid)
12. TrajectoryGridSmallMultiples (6-name × 30-day sparks)

**5 form/controls**: ChipControl (active = accent), ColumnChipChooser, ChartSelectorChecklist (≤8), TabStrip (CSS-only OK for v6.0 if no client state), ToggleChip.

---

## Execution phases

### Phase 0 — Design system foundation (1-2 days, do FIRST)

**Why first:** Everything else depends on this. Building pages without these primitives = my original mistake repeated.

| Step | Output | Skill cadence |
|---|---|---|
| 0.1 | Update `tailwind.config.ts` with exact token palette (replace whatever's there) | trivial |
| 0.2 | Build 5 primitives in `frontend/src/components/v6/primitives/` | writing-plans → subagent-dev → design-review against mockup index.html |
| 0.3 | Build 12 layout components in `frontend/src/components/v6/layout/` | writing-plans → subagent-dev → design-review |
| 0.4 | Build MultidimChart (ECharts wrapper) — single component, exhaustively tested against mockup 03's chart | writing-plans → subagent-dev → design-review against 03 |
| 0.5 | Build remaining 11 chart components | writing-plans → 11 subagent-dev calls in parallel → design-review |
| 0.6 | Build 5 form/control components | writing-plans → subagent-dev |
| 0.7 | Storybook-like demo route `/v6/_components` showing every primitive against the mockup token palette | design-review against mockup tokens |
| 0.8 | Commit + deploy to EC2 | classifier-safe SSH path now unblocked |

**Acceptance:** All 34 components exist, render in `/v6/_components`, visually match the mockups' use of them.

### Phase 1 — Rebuild the 5 backend-ready pages (3-4 days)

In order (easiest fidelity first):

| Step | Page | Mockup file | Key components | Est. time |
|---|---|---|---|---|
| 1.1 | **/v6/regime** (Page 01) | 01-market-regime.html | HeroStrip4 + JourneyGrid (12-week × 5-row) + 4 pulse tiles + 6 CellFavoredCards + TabStrip (Stocks/Funds/ETFs) | 4-6 hrs |
| 1.2 | **/v6/funds** (Page 06) | 06-funds.html | HeroStats6 + StoryBlock4Up + AmcLadderStackedBar + quartile-table 12-row + TrajectoryGridSmallMultiples + 6 fund cards + 587-row HeatmapTable | 6-8 hrs |
| 1.3 | **/v6/funds/[scheme]** (Page 06a) | 06a-fund-ppfas.html | PageHead + MetaChipRow + VerdictStrip6 + rolling 3Y chart + drawdown chart + top10/alloc/attribution 3-up + peer set + 60-month quartile transition viz + SWITCH rule check panel | 6-8 hrs |
| 1.4 | **/v6/stocks/[symbol]** (Page 05a) | 05a-stock-reliance.html | PageHead + MetaChipRow + VerdictStrip6 + MultidimChart w/ cell-fire annotations + 365d cell-fire timeline + RSGrid 5×6 + peer set + 8-card fundamentals + open calls table + macro overlays | 8-10 hrs |
| 1.5 | **/v6/calls** (Page 08) | 08-calls-performance.html | HeroStats6 + StoryBlock4Up + cumulative excess landscape chart w/ ±1σ ribbon + 24-cell win-rate HeatmapGrid + 6 cell-IC trajectories + 6 cell cards + 1,847-row HeatmapTable + confidence-band calibration scatter | 8-10 hrs |

**Per-page skill cadence (NON-NEGOTIABLE — print it on the wall):**
1. Read mockup HTML
2. `superpowers:writing-plans` → `docs/superpowers/plans/2026-05-27-v6-page-NN-rebuild.md`
3. `superpowers:subagent-driven-development` (one subagent per component / section)
4. `/design-review` against mockup (visual screenshot diff)
5. `/review` + `/codex review`
6. SSH deploy + curl-verify

### Phase 2 — Build secondary MVs + finish partial pages (2 days)

| Step | What | Why | Est. time |
|---|---|---|---|
| 2.1 | Design + build `mv_markets_rs_detail_charts` MV | 03 detail-chart grid needs per-baseline price/RS/vol series with annotations | 4 hrs (MV) + 6-8 hrs (page rebuild) |
| 2.2 | Rebuild **/v6/markets-rs** (Page 03) | 9×5 RS grid + narrative + 2-col multidim chart grid (≤8 visible) | included above |
| 2.3 | Design + build `mv_stock_landscape` MV | 05 RS×Composite bubble + 24-cell matrix data | 4 hrs (MV) + 8-10 hrs (page rebuild) |
| 2.4 | Rebuild **/v6/stocks** (Page 05) | Full mockup including bubble + matrix + 750-row table | included above |

### Phase 3 — Backend backfill (1-2 days; requires EC2 Python compute)

These cannot be done from local Mac (psycopg2 broken per memory `reference_ec2_access.md`).

| Step | Backend work | Unblocks |
|---|---|---|
| 3.1 | Phase C1.c: backfill `atlas_etf_scorecard` 34 → 126 | Page 07, 07a |
| 3.2 | Phase C1.d: backfill 8 new cols on `atlas_sector_metrics_daily` 5-yr | Page 04, 04a |
| 3.3 | Phase C2: macro ingest jobs for `atlas_macro_daily` 5 cols | Page 02 |
| 3.4 | Build 5 sector MVs (cards, breadth, rrg, deepdive, rotation) | Page 04, 04a |
| 3.5 | Build 2 ETF MVs (list_v6, deepdive) | Page 07, 07a |
| 3.6 | Build `mv_india_pulse` | Page 02 |
| 3.7 | Refresh `pg_cron` schedule for the 8 new MVs | nightly auto-refresh |

### Phase 4 — Remaining pages (3-4 days)

After Phase 3 done:

| Step | Page | Mockup | Est. time |
|---|---|---|---|
| 4.1 | **/v6/sectors** (Page 04) | 04-sectors.html | 8-10 hrs |
| 4.2 | **/v6/sectors/[name]** (Page 04a) | 04a-sector-energy.html | 6-8 hrs |
| 4.3 | **/v6/etfs** (Page 07) | 07-etfs.html | 6-8 hrs |
| 4.4 | **/v6/etfs/[ticker]** (Page 07a) | 07a-etf-goldbees.html | 6-8 hrs |
| 4.5 | **/v6/india-pulse** (Page 02) | 02-india-pulse.html | 8-10 hrs (heaviest data-density page) |

### Phase 5 — URL rename (deferred per your earlier ask)

Drop the `/v6/` prefix. `/v6/regime` → `/regime`, etc. 10 routes renamed, every `<Link>` in the codebase updated, TopNav rebuilt with final paths. ~3-4 hours focused work. **Defer until Phase 1-4 done** so we're not chasing a moving URL target.

### Phase 6 — Deploy mechanism fix (1-2 hours)

Currently `/home/ubuntu/atlas-frontend-v2/` is a non-git deploy target updated via rsync. Convert it to a git checkout of `atlas-os` so future deploys are `cd ~/atlas-frontend-v2 && git pull && npm run build && pm2 restart`. This belongs in Phase 0 or 1 ideally.

---

## Total scope estimate

| Phase | Wall-clock |
|---|---|
| 0 — Design system | 1-2 days |
| 1 — 5 backend-ready pages | 3-4 days |
| 2 — Secondary MVs + 2 partial pages | 2 days |
| 3 — Backend backfill (EC2) | 1-2 days |
| 4 — 5 backend-blocked pages | 3-4 days |
| 5 — URL rename | 0.5 day |
| 6 — Deploy mechanism | 0.5 day |
| **Total** | **~12-15 focused days** |

Parallelism: Phases 0, 3 can run partially in parallel (Phase 3 backend work doesn't block Phase 0 component build). Phase 1 strictly after Phase 0.

---

## Sequencing options (you decide)

**Option A: Strict backend-first** — Phase 3 entirely before any frontend rebuild. Most disciplined, longest time-to-visible-progress.

**Option B: Component-first then parallel** — Phase 0 first, then Phase 1 + Phase 3 in parallel, then Phase 2 + Phase 4. Fastest if I can context-switch.

**Option C: Page-by-page in mockup order** — Reset and do 01 fully (build components needed), 02 next (build more components), etc. Linear, easiest to track, slowest because components get re-built lazily.

**My recommendation: Option B.** Phase 0 is mandatory shared infrastructure. After it lands, I can rebuild backend-ready pages while EC2 compute work happens in parallel.

---

## My commitments to you (read these back to me if I drift)

1. I will read the mockup HTML before writing any line of code.
2. I will not let "the first page's pattern" become a template for subsequent pages.
3. I will invoke `/design-review` against every mockup before claiming a page done.
4. I will stop and call out fidelity gaps rather than ship "close enough."
5. I will not skip the gstack skill cadence on the grounds that it's slower.
6. I will deploy via SSH (now unblocked) for tight feedback loops — no more paste-back.
7. When backend gaps exist, I'll say "blocked on Phase 3" instead of building data-less stubs.

This plan is the source of truth for the rebuild. If I deviate, point at this file.
