# Atlas Sector Deep Dive — Design Spec

**Date:** 2026-05-09
**Author:** session
**Reviewers:** /plan-design-review + /plan-ceo-review
**Predecessor:** `2026-05-09-sectors-page.md` (initial sectors page — landed)

## Purpose

The current `/sectors` page summarizes 25 sectors at a glance but the deep-dive
sits in a 520px right-side drawer that:
1. Has a broken `/api/*` proxy (nginx routes `/api/` to a dead FastAPI port; the 3M history call 502s)
2. Treats the sector as a single entity — no view of the underlying stocks, ETFs, or mutual funds the user could act on
3. Excludes small sectors (Housing 1, Telecom 1, Services 3) instead of presenting them sensibly
4. Calls everything in INR with no gold-denominated alternative
5. Shows a watchlist (Actionable / Divergent / Narrow / Exit) without explaining what those words mean or letting you expand the list

The spec proposes a full-page sector deep-dive route, an enriched watchlist,
and a phased path to instrument-level rollups (stocks, ETFs, mutual funds).

## Data Inventory

What we have today, by table:

### Sector level
| Source | Fields |
|---|---|
| `atlas.atlas_sector_metrics_daily` | returns 1m/3m/6m, RS_3m_nifty500, breadth_50ema, RS_participation, leadership_concentration, constituent_count |
| `atlas.atlas_sector_states_daily` | sector_state, bottomup_state, topdown_state, RS_state, momentum_state, divergence_flag |
| `atlas.atlas_sector_master` | sector → primary NSE index, secondary indices, fallback benchmark |
| Coverage | 10 years daily, 25–30 sectors |

### Stock level (NEW for deep dive)
| Source | Fields |
|---|---|
| `atlas.atlas_universe_stocks` | symbol, company_name, sector, industry, in_nifty_50/100/500, tier |
| `atlas.atlas_stock_metrics_daily` | returns 1d/1w/1m/3m/6m/12m, RS_*_tier, RS_*_nifty500, RS_pctile, EMAs, vol_ratio, drawdown, ATR, Weinstein gate, **rs_*_tier_gold (gold-denominated already exists)** |
| `atlas.atlas_stock_states_daily` | rs_state, momentum_state, risk_state, volume_state, gates |
| `atlas.atlas_stock_decisions_daily` | is_investable, gates, triggers, position_size_pct, market/risk multipliers, exit reasons |
| Coverage | Nifty 500 universe + tier-classified stocks |

### ETF level (NEW)
| Source | Fields |
|---|---|
| `atlas.atlas_universe_etfs` | ticker, fund_house, etf_name, theme, **linked_sector**, linked_index, asset_class |
| `atlas.atlas_etf_decisions_daily` | is_investable, gates, triggers, position_size_pct |

### Mutual fund level (NEW)
| Source | Fields |
|---|---|
| `atlas.atlas_universe_funds` | scheme_name, AMC, broad_category, **category_name** (e.g. "Sectoral - Banking"), benchmark_code |
| `atlas.atlas_fund_decisions_daily` | recommendation, gates (performance/sectors/stocks/market), entry/exit/add/reduce triggers, weeks_in_state, last_week_recommendation |

### Gold-denominated returns
- **Already exists** in `atlas_stock_metrics_daily.rs_*_tier_gold` (1w, 1m, 3m)
- **Not yet** at sector / index / market-regime level — would need new aggregation pipeline
- Phase 3 work; **defer**

## Issue → Resolution Map

| # | Issue (user-reported) | Resolution |
|---|---|---|
| 1 | Watchlist eye-icon needs to be a proper button; cards should be bigger; commentary inline | Redesign card: 2× height, includes "What it means" + "What to do" + click-to-expand list |
| 2 | "+3" / "+1" doesn't expand; "23 divergent" — what does it mean? "Actionable" — buy what? | Click any card → reveals full sector list with each linking to deep dive. Plain-English subhead per card |
| 3 | Need gold-denominated view across regime, sectors, stocks, ETFs | Stock-level toggle now (data exists); sector/regime gold aggregation deferred |
| 4 | Bubble chart needs how-to-read; small sectors merged not excluded | Inline "How to read" panel + show-all-sectors toggle; backend sector-merge map deferred |
| 5 | 3M history not loading; drawer should be a full page with stocks/ETFs/funds + 2×2 RS-breadth for instruments | Build `/sectors/[name]` route. Server-render data (no `/api/*` calls needed). Tabs: Overview / Stocks / ETFs / Funds / Methodology |

## Proposed Architecture

### Routes

| Route | Purpose | Rendering |
|---|---|---|
| `/sectors` | Index page (existing, polished) | SSR |
| `/sectors/[name]` | Deep dive (NEW, replaces drawer) | SSR |

### `/sectors` page polishing

**Watchlist row** — replace 4 cramped cards with 4 expanded cards:

```
┌───────────────────────────────────────┐
│ Actionable          (count) ●●●●      │
│ Sectors signalling a buy setup —      │
│ ENTER or ROTATE IN. Bottom-up         │
│ confirms; market gate is open.        │
│                                        │
│ Action → research candidates, size    │
│ via market multiplier × sector        │
│ multiplier × stock multiplier.        │
│                                        │
│ Banking, Pharma, Energy [▾ show all]  │
└───────────────────────────────────────┘
```

Same pattern for Divergent / Narrow Leadership / Exit, each with its own
"What it means" + "What to do" line. Clicking the disclosure reveals the
full list; each sector pill links to `/sectors/[name]`.

**Bubble chart** — add expandable "How to read" panel above the chart:

```
How to read this matrix [▾]
  • X-axis: relative strength vs Nifty 500 (3-month rolling) — right is leading
  • Y-axis: % of stocks above their 50-day EMA — up is broader strength
  • Bubble size: number of stocks in the sector
  • Color: current sector state (green/amber/red)
  • Top-right quadrant (LEADERS) is where you want to be
  • Bottom-left (LAGGARDS) — capital preservation
```

Plus a "Show all sectors (incl. small)" toggle to opt-in to noisy small sectors.

### `/sectors/[name]` deep dive (NEW)

Single full-width page (no drawer). Sticky tabs at top.

#### Header band
- Sector name, current state badge, decision badge, data-as-of, time range toggle (1M/3M/6M/1Y)
- Crumbs: `Sectors / Banking`

#### Tab: Overview (default)
- KPI tiles: state / decision / constituent count / divergence flag
- Returns row: 1M, 3M, 6M
- 2×2 signal-component grid: bottom-up / top-down / RS / momentum (each with hover hint)
- Concentration gauge + interpretation copy
- Divergence callout if flagged
- State distribution stacked bar + run length + transition count
- Per-sector timeline strip
- 4 trend charts: RS, breadth, RS-participation, 3M return

#### Tab: Stocks
- **2×2 RS-vs-breadth bubble matrix for stocks IN this sector**
  - X = RS_3m_nifty500 (stock vs Nifty 500)
  - Y = stock-level breadth proxy (above 50-EMA flag → group %)
  - Bubble size = avg_volume_252 (or position_size_pct)
  - Color = stock state (rs_state + momentum_state composite)
- Sortable table: symbol, company, decision, RS state, 1M / 3M / 6M return, RS pctile, 50-EMA flag, volume, position size %
- Filter chips: All / Investable only / Nifty 50 / Nifty 100 / Nifty 500
- **INR / Gold toggle** for RS columns (uses existing `rs_*_tier_gold`)

#### Tab: ETFs
- Table of ETFs where `linked_sector = <this sector>` or theme matches
- Columns: ticker, name, fund house, decision, position size %, last entry/exit trigger
- Empty state if no ETFs linked

#### Tab: Funds
- Sectoral mutual funds (category_name ILIKE `%<sector>%`)
- Columns: scheme, AMC, recommendation, weeks in state, last week's recommendation, triggers
- Sort by recommendation strength

#### Tab: Methodology
- How sector state is computed (RS state + momentum state + breadth thresholds → 4-state classification)
- How decision is derived from state + RS + momentum
- Current threshold values (read from `atlas.atlas_thresholds`)
- Data sources + last update timestamp

### File structure (new)

```
frontend/src/
  app/sectors/[name]/
    page.tsx                           # SSR, fetches all data
    layout.tsx                         # tab nav (or use search params)
    overview-tab.tsx                   # client component for charts
    stocks-tab.tsx                     # client; bubble + table + INR/Gold toggle
    etfs-tab.tsx                       # client; table only
    funds-tab.tsx                      # client; table only
    methodology-tab.tsx                # server; static
  components/sectors/
    SectorWatchlist.tsx                # NEW — replaces SectorRiskWatch
    SectorDeepDiveStocks.tsx           # 2×2 + table for stocks
    SectorDeepDiveETFs.tsx
    SectorDeepDiveFunds.tsx
    StockBubbleChart.tsx               # reusable D3 bubble for stocks
  lib/queries/
    sector-deep-dive.ts                # NEW — sector + stocks + ETFs + funds queries
  lib/sectors-merge.ts                 # NEW — small-sector merge map (UI-only for Phase 1)
```

### Data-fetching pattern

The `/sectors/[name]/page.tsx` server-renders ALL data in parallel:

```typescript
const [sectorSnapshot, sectorHistory, stateHistory, stocks, etfs, funds] = await Promise.all([
  getSectorSnapshot(name),
  getSectorMetricHistory(name, days),
  getSectorStateHistory(days, name),
  getStocksInSector(name),
  getETFsLinkedToSector(name),
  getFundsForSector(name),
])
```

No client-side `/api/*` calls. Avoids the nginx routing problem entirely.

## Information Architecture

### Visual hierarchy of `/sectors/[name]`

The deep-dive page is a research tool for "should I take a position in <sector>?".
The user's question gets answered in this order:

1. **Verdict** (state + decision badge — biggest, top-left)
2. **Why** (signal components, returns, divergence — middle)
3. **What history says** (charts — below the fold)
4. **What to act on** (stocks/ETFs/funds — separate tab so it's a deliberate move)

Header band is sticky. Tabs are sticky. Everything else scrolls.

```
┌────────────────────────────────────────────────────────────┐
│ < Sectors / Banking                  Data: 9 May  [1M 3M 6M 1Y]│
│                                                                │
│ Banking                                                       │
│ ●  OVERWEIGHT     ★ ENTER            34 stocks                │
└────────────────────────────────────────────────────────────┘
│ [Overview] Stocks  ETFs  Funds  Methodology                  │  ← sticky tabs
└────────────────────────────────────────────────────────────┘
   <tab content>
```

### Default tab + deep-link routing

- `/sectors/[name]` → Overview tab
- `/sectors/[name]?tab=stocks` → Stocks tab (used by watchlist callouts to deep-link straight to instruments)
- `/sectors/[name]?tab=stocks&filter=investable` → pre-applied filter
- Bad tab name → fall back to Overview, no error

### Primary action per tab

| Tab | Primary action |
|---|---|
| Overview | None — research view |
| Stocks | Click stock row → opens stock deep-dive `/stocks/[symbol]` (defer; for now just highlight investable rows) |
| ETFs | Click ETF row → opens ETF deep-dive (defer) |
| Funds | Click fund row → opens fund deep-dive (defer) |
| Methodology | None — reference view |

## Interaction State Coverage

| Surface | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| `/sectors/[name]` page | SSR — no client loader; `loading.tsx` shows skeleton during navigation | Sector not in DB → 404 page with "Pick another sector" link to `/sectors` | DB error → ErrorBoundary with retry button + last successful timestamp | Full page renders with data | Stocks query may return [] for unmapped sectors — show "No stocks classified to this sector yet" |
| Overview KPI tiles | Skeleton blocks during nav | Render even with null fields, dash placeholder | Tile-level error caught — show "—" with hover tooltip explaining staleness | All 8 tiles populated | Up to 4 tiles may show "—" gracefully |
| Trend charts (4 charts) | Skeleton bar | "Insufficient history (need ≥30 trading days)" if range too short | "Chart unavailable" + retry | Recharts area renders | Single-metric failure doesn't block other 3 |
| Stocks tab — bubble | Skeleton | "No stocks classified to this sector" | "Failed to load stocks" + retry button | D3 renders | Some stocks may have null RS — exclude from bubble, count in "N stocks excluded (insufficient history)" footer |
| Stocks tab — table | Skeleton rows ×5 | "Filter returned 0 stocks. Clear filter?" link | Same as bubble | Sortable table | Investable filter may return 0 — show explicit empty CTA |
| ETFs tab | Skeleton | "No ETFs are linked to this sector. Sectoral ETFs typically come from <fund houses>." | Retry button | Table | — |
| Funds tab | Skeleton | "No mutual funds in this category. Sectoral funds appear here when AMCs launch them." | Retry button | Table | — |
| Watchlist card expand | Slide-down 200ms | "No sectors meet this criteria today" | Should never error (computed from props) | Pills with sector links | — |
| INR/Gold toggle on Stocks | Instant — no fetch | Gold column unavailable for some stocks → "—" with hover | If `rs_*_tier_gold` is null across the board, hide the toggle entirely | All RS columns swap | — |

## User Journey

The 5-second scan, the 5-minute drill, the 5-year relationship:

| Time horizon | What the user feels | What the page must deliver |
|---|---|---|
| 5 sec | "Is this sector hot or cold?" | State + decision badge in first viewport, color-coded (green/amber/red) |
| 5 min | "Why does the model think so? Should I trust it today?" | Signal components, divergence flag, concentration gauge, full historical context |
| 5 year | "Is the model methodology sound? Can I learn from it?" | Methodology tab with computed thresholds, state-distribution stats, transition counts |

Storyboard for the entry path "I clicked 'Banking' from the Watchlist's Actionable card":

1. **Land** — Banking deep dive, Overview tab. Sees "OVERWEIGHT · ENTER" badge. ✓ confirms my interest
2. **Confirm** — Reads signal components row. Bottom-up = Improving, Top-down = Improving, RS = Overweight, Momentum = Improving. All four green. Confidence rises.
3. **Check fragility** — Concentration gauge says 42% (moderate). Divergence flag absent. ✓ no red flag.
4. **Look at history** — Charts show RS rising for 6 weeks, breadth holding above 70%. ✓ trend persistent.
5. **Drill to instruments** — Clicks "Stocks" tab. 2×2 bubble: 22 stocks in upper-right (LEADERS) quadrant, 8 in NARROWING.
6. **Filter** — "Investable only" → 14 stocks remain. Sorts by RS pctile. Top 5 names visible.
7. **Decide** — User has shortlist. Clicks one symbol → (Phase 2) lands on stock deep dive.

## AI Slop Avoidance

- Stocks bubble axes corrected: **X = RS_3m_nifty500, Y = RS_pctile_3m**. Breadth is a sector-aggregate concept and meaningless at the individual stock level. RS pctile is a stock-level metric that ranks the stock against its tier — pairs naturally with RS.
- Bubble color = stock state (composite: `rs_state` × `momentum_state`):
  - Improving + Overweight RS = signal-pos (green)
  - Stable + Overweight RS = teal
  - Deteriorating + Overweight RS = signal-warn (amber)
  - Underweight RS = signal-neg (red)
  - Otherwise = ink-tertiary (grey)
- Bubble size = `position_size_pct` from `atlas_stock_decisions_daily` — directly meaningful (the model's recommended sizing). Falls back to constant 8 if null.
- No 3-column feature grid anywhere. No icons in colored circles. No purple gradients. No emoji.
- Tabs use the existing `text-ink-tertiary` style with active state in `text-teal`. No card stacks.
- Decision badges use the same `DECISION_STYLE` map already in `SectorDecisionTable.tsx` — no reinvention.

## Design System Alignment

Tokens used (Tailwind v4 custom properties already in the project):

| Surface | Token |
|---|---|
| Page bg | `bg-paper` |
| Borders | `border-paper-rule` |
| Headings | `text-ink-primary` |
| Secondary text | `text-ink-secondary` |
| Muted text | `text-ink-tertiary` |
| State: Overweight | `signal-pos` (#2F6B43) |
| State: Neutral | `signal-warn` (#B8860B) |
| State: Underweight / Avoid | `signal-neg` (#B0492C) |
| Decision: HOLD | `teal` (#1D9E75) |
| Charts | reuse `IndicatorChart` from `/components/regime/` |
| Tables | reuse `SectorDecisionTable` row pattern |

Fonts: existing `font-sans` (UI), `font-mono` for numbers, `font-serif` for sector name in header.

Numbers: Indian formatting per `~/.claude/rules/frontend-viz.md` — `₹1,23,45,678`, `+1.23%` with sign. Use the existing `pct()` formatter.

Dates: `DD-MMM-YYYY` IST.

## Responsive & Accessibility

### Breakpoints (mobile-first within Tailwind defaults)

| Width | Layout |
|---|---|
| < 640px | Single column. KPI tiles stack 2-up, then 2-up (4 in 2 rows). Tabs become a horizontal scroll-snap strip. Tables use `overflow-x-auto`. Bubble chart hides labels < 12 chars wide; row-table view replaces the bubble below 480px. |
| 640–1024px | Tiles 4-up. Tabs in a row. Bubble chart at 90% width. |
| ≥ 1024px | Full 1400px max-width layout. |

### Keyboard nav

- `Tab` traverses: tab nav → KPI tiles (skip if non-interactive) → chart titles → bubble (focusable, arrow keys move selection) → table (sortable headers focusable, Enter sorts) → row (Enter opens deep-dive)
- `Esc` on the watchlist expanded list collapses it
- Skip link: "Skip to instruments" jumps to the active tab content

### Screen readers

- Tab nav uses ARIA `role="tablist"` + `aria-selected`
- Bubble chart has an `aria-label` summary: "Sector positioning matrix. 25 sectors plotted by 3-month relative strength versus Nifty 500 (X) and breadth (Y). 8 are LEADERS, 7 are LAGGARDS."
- Charts have `aria-describedby` pointing to the description text
- State badges have `aria-label` reading the full state name
- Tables have proper `<th scope="col">`, sortable headers announce sort direction

### Touch targets

- Watchlist card expand: 44px tap target on the count + caret
- Tab nav: 44px minimum height
- Table rows: 40px minimum height; entire row clickable

### Color contrast

- All state colors meet WCAG AA on `bg-paper` (#FBF8F1)
- Sign-only state representation forbidden; always pair color with text or icon
- Decision badges have a fill ≥ 12% of bg + 4.5:1 text contrast

## Resolved Decisions

Picked the recommended option in each tradeoff. User can override before
implementation begins.

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Layout | **Tabs** (sticky) | Keeps overview-charts above the fold for "is this hot?". Stocks discovery is one tab click — cheap. Long-scroll loses the verdict in scroll fog on mobile. |
| 2 | Drawer fate | **Kill the drawer entirely.** Click sector → full page. | The drawer answered too little to justify split-attention. Full page is the new home. Faster scan across sectors comes from the watchlist + bubble matrix on `/sectors`, not the drawer. |
| 3 | Stocks bubble axes | **X = RS_3m_nifty500, Y = RS_pctile_3m** | Both stock-level relative measures. Breadth doesn't apply per-stock. RS pctile = how this stock ranks vs its tier — pairs naturally with cross-universe RS. |
| 4 | Gold toggle scope | **Page-local toggle on Stocks tab only**, Phase 1 | Stock-level data exists. App-global preference is over-engineered until 3+ pages support it. Header toggle deferred. |
| 5 | Show-all-sectors toggle on `/sectors` | Default **OFF** | Small sectors distort positioning. Power users can opt in. Backend reclassification (Phase 3) makes the toggle obsolete. |
| 6 | Phase 1 scope | **Overview + Stocks tabs only** | ETFs / Funds tabs are query+table work — easy to add in Phase 2 once the page architecture is proven. Don't block the deep-dive ship on completeness. |
| 7 | Sector merge map | **Defer to Phase 3 (backend)** | A UI-side merge map would need rebuilding all aggregates client-side and would diverge from the DB. Better to fix the source. Phase 1 keeps the existing exclusion + show-all toggle. |

## NOT in scope (this PR)

- Stock deep-dive page (`/stocks/[symbol]`) — clicked rows are highlighted but don't navigate yet
- ETF deep-dive page
- Mutual fund deep-dive page
- App-global INR/Gold preference
- Sector reclassification (Housing → Realty, Telecom → Digital, etc.)
- Sector-level gold-denominated metrics
- Fundamentals (P/E, revenue growth) anywhere
- Portfolio simulation hooks (M7 territory)
- Stock-level breadth (a thing that doesn't exist)

## What already exists

| Component | File | Reuse for |
|---|---|---|
| `IndicatorChart` | `frontend/src/components/regime/IndicatorChart.tsx` | All 4 trend charts on Overview tab |
| `SectorDecisionTable` row pattern | `frontend/src/components/sectors/SectorDecisionTable.tsx` | Stocks/ETFs/Funds tab tables |
| `pct()`, `pctColor()` formatters | inline in SectorDecisionTable | All percentage cells |
| `STATE_COLOR`, `DECISION_STYLE` | inline | Header badges, table cells, bubble fill |
| `TimeRangeToggle` | `frontend/src/components/ui/TimeRangeToggle.tsx` | Header band of deep-dive page |
| D3 bubble pattern | `frontend/src/components/sectors/SectorBubbleChart.tsx` | Stocks-tab bubble (extract shared `BubbleChart` primitive) |
| `getCurrentSectors`, `getSectorMetricHistory` | `frontend/src/lib/queries/sectors.ts` | Header band data |
| Tailwind v4 tokens | `frontend/src/app/globals.css` | All colors and surfaces |

## Phasing

### Phase 1 — this PR

Scope:
1. Build `/sectors/[name]` SSR route with Overview + Stocks tabs
2. New `lib/queries/sector-deep-dive.ts` with parallel fetches
3. New `StockBubbleChart` D3 component (extract shared bubble primitive from existing `SectorBubbleChart`)
4. Stocks-tab table with filter chips + INR/Gold RS toggle
5. Watchlist redesign: bigger cards with "What it means" + "What to do" + click-to-expand list
6. Bubble chart "How to read" expandable panel + "Show all sectors" toggle (default OFF)
7. Kill the drawer (`SectorDrawer`, `SectorDrawerSnapshot`, `SectorDrawerStateStats`) — replaced by deep-dive page
8. Update `/sectors` SectorViews to navigate on click instead of opening drawer
9. Fix the broken nginx `/api/*` issue by using SSR everywhere (no client-side `/api/*` calls)

Success criteria:
- User clicks any sector → lands on full-page deep dive
- Overview tab shows verdict (state + decision) above the fold on a 1366×768 desktop
- Stocks tab shows ≥ 14 of Banking's 34 stocks in the bubble matrix
- INR/Gold toggle swaps RS columns instantly with no fetch
- Watchlist "Actionable" card click expands to show a list with sector pills linking to deep dives
- 0 console errors; all linter checks pass; bundle size delta < 50 kB

Non-goals (explicit, deferred to later phases):
- Stocks bubble does not need to be interactive at parity with the sector bubble (no drawer-on-click)
- No filtering by industry within a sector
- No sector comparison tool

### Phase 2 — instrument tabs (follow-up)
- ETFs tab (universe + decisions)
- Funds tab (sectoral category match + decisions)
- Methodology tab (read thresholds from `atlas.atlas_thresholds`)
- Stock row click → `/stocks/[symbol]` (when stocks page lands)

### Phase 3 — backend
- Sector reclassification at the data layer (stops needing show-all toggle)
- Sector-level + regime-level gold aggregation pipelines
- App-global INR/Gold preference (header toggle, persists in localStorage + URL param)

## Risks / non-goals

- **NOT** changing the sector classification in the DB. UI shows what the data has.
- **NOT** doing fundamentals (P/E, revenue) — out of scope for this milestone.
- **NOT** doing portfolio simulation on the deep dive — that's M7.
- nginx config can stay as-is once we drop client-side `/api/*` calls; the existing 8010 route is dormant but harmless.

## Success criteria

User can:
1. Click a sector from /sectors and land on a full-page deep dive
2. See all stocks in that sector with a bubble matrix + sortable table
3. Toggle stock RS between INR and gold-denominated
4. Read the watchlist cards and immediately understand what each bucket means and what to do about it
5. Read the bubble chart's how-to-read panel and not need a second explanation

## CEO Review Findings

**Mode:** SELECTIVE EXPANSION. Phase 1 baseline holds; cherry-picks surfaced and accepted below.

**Implementation approach selected:** Full route at `/sectors/[name]` + kill drawer (Approach A). Approaches B (in-place drawer fix) and C (full-screen modal) rejected because the user explicitly asked for a full page with shareable URLs, and a 520px drawer cannot host a stocks table at acceptable density.

### Section 1 — Architecture

```
┌──────────────────┐         ┌─────────────────────────┐
│ /sectors/[name]  │         │  Phase 1 SSR queries    │
│ page.tsx (SSR)   │  Promise.all                       │
│                  │  ────►  │  - getSectorSnapshot    │
│  ┌────────────┐  │         │  - getSectorMetricHist  │
│  │ Overview   │  │         │  - getSectorStateHist   │
│  │  tab       │  │         │  - getStocksInSector    │
│  └────────────┘  │         └─────────────────────────┘
│  ┌────────────┐  │                  │
│  │ Stocks tab │  │                  ▼
│  │  ─ bubble  │  │         ┌─────────────────────────┐
│  │  ─ table   │  │         │  atlas.atlas_universe_  │
│  │  ─ INR/Au  │  │         │  stocks + stock_metrics │
│  └────────────┘  │         │  + stock_states +       │
└──────────────────┘         │  stock_decisions        │
                              └─────────────────────────┘

Happy:   all 4 queries succeed → page renders
Nil:     name not in universe → notFound() → 404 page
Empty:   sector has 0 stocks → "No stocks classified" empty state
Error:   1 query fails → ErrorBoundary surfaces, retry button
```

Coupling: `lib/queries/sector-deep-dive.ts` is new. It imports `lib/db.ts` (existing).
No new external dependencies. No client-side `/api/*` calls — sidesteps the broken
nginx routing.

Rollback: revert the commit + redeploy. No DB migration. No flag needed.

### Section 2 — Error & Rescue Map

| Codepath | Failure | Caught? | User sees | Logged |
|---|---|---|---|---|
| `getStocksInSector(name)` | DB timeout | ✅ try/catch in route handler | Page-level error boundary "Could not load stocks" + retry | structured log via Next.js |
| `getStocksInSector(name)` | unknown sector_name | ✅ returns [] | Stocks tab empty state | — |
| Stock RS columns | `rs_3m_nifty500` is null | ✅ render `—` | "—" cell | — |
| Stock RS columns | `rs_*_tier_gold` is null entirely | ✅ hide Gold toggle | Toggle absent if no stocks have gold data | — |
| Bubble | Some stocks have null RS | ✅ filter out, show count in footer | "N stocks excluded (insufficient history)" | — |
| URL `?tab=invalid` | Bad tab name | ✅ fallback to Overview | Overview tab loaded | — |

No `catch (Exception)` — no catch-all handlers needed since SSR errors bubble to Next.js error boundary correctly.

### Section 3 — Security

- New route `/sectors/[name]` reads from DB only; no writes
- `name` param is decodeURIComponent'd then used in parameterized SQL (`= ${name}`) — postgres.js binds via prepared statement — no SQL injection
- No new auth surface (route is public, same as `/sectors`)
- No PII in the data
- `rs_*_tier_gold` is computed market data, not user data

### Section 4 — Data flow & edge cases

| Surface | Edge | Plan handles it? |
|---|---|---|
| Stocks bubble | Stock with `null` RS_3m_nifty500 | ✅ filtered, count shown |
| Stocks bubble | Stock with `null` rs_pctile_3m | ✅ filtered |
| Stocks table | Investable filter returns 0 rows | ✅ empty CTA "Clear filter?" |
| Stocks table | 80 stocks (Infrastructure) | ⚠️ no pagination — table is sortable + scrollable; 80 rows OK at 36px each |
| Stocks table | 0 stocks (Telecom = 1 stock = excluded) | n/a — small sectors don't have a deep-dive route at all |
| Watchlist expand | 0 sectors in a bucket | ✅ "No sectors meet this criteria today" |
| INR/Gold toggle | Mid-render network reload | ✅ instant — no fetch needed |
| Tab switch | URL deep-link to `?tab=stocks` then user clicks Overview | ✅ updates URL, browser back navigates correctly |

### Section 5 — Code quality

- Reuse `pct()`, `pctColor()` formatters — extract to `lib/format.ts` (deferred — keep inline until 3rd consumer)
- Stocks bubble extends, doesn't duplicate, the existing `SectorBubbleChart` D3 logic — extract a `BubbleChart<T>` primitive in the same PR
- No new abstractions for tabs — use Next.js search params, not a heavyweight tab library

### Section 6 — Tests

The user has historically not enforced frontend tests (per CLAUDE.md the hooks gate Python). Front-end test coverage is currently shallow on the sectors page. **Recommendation**: skip frontend unit tests for Phase 1, add a single Playwright smoke test that:
1. Loads `/sectors`, sees Watchlist
2. Clicks first sector pill in "Actionable", lands on `/sectors/[name]?tab=stocks`
3. Sees ≥ 1 stock in the bubble or "no stocks" message
4. Toggles INR/Gold, verifies a column header changes

Defer broader coverage to Phase 2.

### Section 7 — Performance

- 4 SSR queries in `Promise.all` — bounded by slowest. Stocks query needs index check.
- Banking = 34 stocks → ~34 rows for join across `stock_metrics + states + decisions`. Indexable on `(date, sector)` already. **Verify**: `EXPLAIN ANALYZE` before deploy.
- No client-side fetches — no waterfall.
- Bundle: Stocks tab adds D3 (already loaded for /sectors) + recharts (already loaded) — delta ~5 kB.

### Section 8 — Observability

- Use Next.js built-in instrumentation — `console.error` on query failures already structured by the runtime
- Add `data_as_of` to the page footer (already in spec) so a stale page is visible without checking logs
- No new dashboards needed — page failures will surface as 500s in atlas.error.log (already in nginx)

### Section 9 — Deployment

- No DB migration; no feature flag needed
- Phase 1 ships as a single PR
- Rollback: `pm2 restart atlas-frontend` after `git revert` — < 1 min
- Pre-deploy: tar → SCP to 13.202.162.196 → `npm run build` → `pm2 restart atlas-frontend`

### Section 10 — Long-term trajectory

- Reversibility: 4/5 (route is additive; drawer files removed but in git history)
- Path dependency: route enables `/sectors/[name]?tab=etfs|funds|methodology` in Phase 2 with no architectural change
- 1-year question: a new engineer reading the page should immediately see the per-tab data fetcher pattern — uses the same `lib/queries/` pattern as the rest of the project

### Section 11 — Design (deferred to /plan-design-review which already ran)

Cross-reference: design review of this spec landed at **9/10** — see Design Review Summary below.

## Cherry-Picks (SELECTIVE EXPANSION — pre-accepted into Phase 1 per user direction "maximize")

| # | Proposal | Effort (human / CC) | Decision | Rationale |
|---|---|---|---|---|
| 1 | **Top Picks callout** above the Stocks table — top 3-5 stocks where `is_investable=true` AND state ∈ {ENTER, ROTATE IN} AND rs_pctile_3m is highest | 30 min / 10 min | **ACCEPTED** | Directly answers user ask: "tell me which instruments to take a position on" |
| 2 | **Methodology popovers** on each watchlist card title — small `?` button → popover explaining the metric (e.g., "Divergent = `divergence_flag` from sector_states_daily, computed when bottom-up state and top-down state disagree") | 45 min / 15 min | **ACCEPTED** | Resolves "what does 23 divergent mean?" beyond inline subhead |
| 3 | **Position-size mini-bar** on each stock row — visualizes `position_size_pct` from `atlas_stock_decisions_daily` (model's recommended sizing) | 20 min / 5 min | **ACCEPTED** | Makes the model's quantitative recommendation visceral; ~5 min implementation cost |
| 4 | **Sector merge map (UI-only)** — Housing → Realty, Telecom → Digital | 60 min / 20 min | **DEFERRED to Phase 3 (backend)** | UI-side mapping creates DB/UI drift — risk of confusion outweighs benefit |
| 5 | **Cross-page Gold readiness badge** on regime/ETFs/funds | 20 min / 5 min | **SKIPPED** | Over-promises Phase 3 work; better to ship Gold consistently when the data lands |
| 6 | **Stocks bubble keyboard navigation** — j/k to move selection, Enter to deep-dive | 30 min / 10 min | **DEFERRED to Phase 2** | Power-user delight; not needed before stock deep dive page exists |
| 7 | **Sector vs Sector comparison card** — small "vs Banking" snapshot if non-Banking | 60 min / 20 min | **DEFERRED to Phase 2** | Useful but scope-creep for Phase 1 |

**Phase 1 scope after cherry-picks**:
- Original Phase 1 + Top Picks callout + Methodology popovers + Position-size mini-bar
- Total Phase 1 CC effort: ~2 hours (~1.5 hr core + ~30 min cherry-picks)

## CEO Review Summary

```
+====================================================================+
|            MEGA PLAN REVIEW — COMPLETION SUMMARY                   |
+====================================================================+
| Mode selected        | SELECTIVE EXPANSION                          |
| Premise check        | Right problem; user's "take a position" verb |
|                      | required adding Top Picks callout            |
| Approach selected    | A (full route, kill drawer)                  |
| Section 1  (Arch)    | 0 issues; diagram added                      |
| Section 2  (Errors)  | 0 critical gaps; all paths mapped            |
| Section 3  (Security)| 0 issues — read-only public route            |
| Section 4  (Data/UX) | 0 unhandled edge cases                       |
| Section 5  (Quality) | Recommend extract BubbleChart<T> primitive   |
| Section 6  (Tests)   | 1 Playwright smoke test recommended          |
| Section 7  (Perf)    | EXPLAIN ANALYZE check before deploy          |
| Section 8  (Observ)  | Sufficient — uses existing nginx logs        |
| Section 9  (Deploy)  | Standard rollback < 1 min                    |
| Section 10 (Future)  | Reversibility 4/5; debt: zero                |
| Section 11 (Design)  | Deferred to plan-design-review (9/10)        |
+--------------------------------------------------------------------+
| Cherry-picks proposed | 7                                           |
| Accepted into Phase 1 | 3 (Top Picks, popovers, size-bar)           |
| Deferred to Phase 2   | 2 (keyboard nav, sector comparison)         |
| Deferred to Phase 3   | 1 (sector merge map)                        |
| Skipped               | 1 (cross-page gold badge)                   |
| Critical gaps         | 0                                           |
| Unresolved decisions  | 0                                           |
+====================================================================+
```

## Design Review Summary

```
+====================================================================+
|         DESIGN PLAN REVIEW — COMPLETION SUMMARY                    |
+====================================================================+
| Pass 1 (Info Arch)  | 6/10 → 9/10  (added hierarchy, tab routing)  |
| Pass 2 (States)     | 4/10 → 9/10  (full state-coverage table)     |
| Pass 3 (Journey)    | 5/10 → 9/10  (storyboard + time horizons)    |
| Pass 4 (AI Slop)    | 7/10 → 9/10  (fixed bubble axes, named tokens)|
| Pass 5 (Design Sys) | 7/10 → 9/10  (token map; reuse existing)     |
| Pass 6 (Responsive) | 3/10 → 9/10  (3 breakpoints, a11y, contrast) |
| Pass 7 (Decisions)  | 7 deferred  → 7 resolved                     |
| Overall design score| 5.5 → 9/10                                   |
+====================================================================+
```

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR | score: 5.5/10 → 9/10, 7 decisions resolved |
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR | mode: SELECTIVE EXPANSION, 7 cherry-picks proposed, 3 accepted, 0 critical gaps |
| Eng Review | `/plan-eng-review` | Architecture & tests | 0 | — | recommended before implementation |

**UNRESOLVED:** 0

**VERDICT:** DESIGN + CEO CLEARED. Phase 1 scope locked: route + watchlist redesign + bubble explainer + Stocks tab with Top Picks callout, methodology popovers, position-size mini-bar. Implementation can begin.
