# Atlas-OS M6 Frontend Design Spec

**Date:** 2026-05-08
**Milestone:** M6 — Fund Manager Research Tool (internal, auth-gated)
**Status:** Approved for implementation planning

---

## 1. Purpose and User

Atlas-OS M6 is an internal research tool for fund managers at Javeri Securities. The primary user (Nimish) does a daily morning review: understand the market regime, identify which sectors to express, and check instrument-level decisions before acting. This is not an investor-facing dashboard — it is a dense, analytical tool built for a professional who knows the domain.

**Backend state (M0–M5 complete):** All data is pre-computed nightly. The frontend reads from Supabase Postgres (`atlas` schema) via the `postgres` npm package in Next.js Server Components. No client-side data fetching. No real-time updates.

---

## 2. Design Language (binding — DS PDF v1.0)

| Token | Value |
|---|---|
| Background | `#F8F4EC` (paper ivory) |
| Ink primary | `#1A1714` |
| Ink secondary | `#5A5248` |
| Ink tertiary | `#8C8278` |
| Paper rule | `#C2B8A8` |
| Signal positive | `#2F6B43` (forest) |
| Signal negative | `#B0492C` (terracotta) |
| Signal warning | `#B8860B` (ochre) |
| Accent | `#25394A` (slate) |

**Typography:** Source Serif 4 (headings/narrative), Inter (UI/labels), JetBrains Mono (numbers/tickers)

**Cards:** 1px `paper-rule` border, 2px radius, no shadow

**Charts allowed:** Sparklines, bar charts, donuts — no 3D, no pie, no gradient fills, no emoji

**Numbers:** Tabular-nums always. ₹ prefix. Indian lakh/crore format. Percentages always with +/− sign. Green positive, red negative. Dates: DD-MMM-YYYY (IST).

**Tone:** Sentence case everywhere. No emoji. Dense information — financial professionals want detail, not summaries.

---

## 3. Tech Stack (locked)

- **Framework:** Next.js 15, App Router, React 19
- **Styling:** Tailwind v4 (CSS-first, no `tailwind.config.js`)
- **DB access:** `postgres` npm package in Server Components only (`server-only` marker). `ATLAS_DB_URL` env var.
- **Icons:** `lucide-react` at 1.5px stroke
- **No shadcn/ui** — Radix UI primitives directly if needed
- **Auth (M6):** Env-var password gate (`ATLAS_PASSWORD`). Supabase Auth deferred to M7.
- **Path alias:** `@/*` → `./src/*`

---

## 4. Route Architecture

```
/                          Market Regime (full page — 100% regime)
/sectors                   Sector deep dive
/sectors/[slug]            Instruments within a sector
/stocks                    Stocks screener (all sectors)
/etfs                      ETFs screener (all sectors)
/funds                     Funds screener
/stocks/[symbol]           Stock detail
/etfs/[symbol]             ETF detail
/funds/[mstar_id]          Fund detail
```

---

## 5. Navigation Architecture

**Top nav (always visible):**
Links: Regime | Sectors | Stocks | ETFs | Funds. Current section highlighted. `data_as_of` date shown right-aligned so the user always knows data freshness.

**Contextual left sidebar (appears on drill-down pages only):**
- On `/sectors/[slug]`: full sector list — current sector highlighted, click to jump between sectors without backtracking
- On `/stocks/[symbol]`, `/etfs/[symbol]`, `/funds/[mstar_id]`: list of instruments in the same sector (context preserved from navigation path), or screener results list if arrived via screener

When the contextual sidebar is absent (screener pages, regime page), the full content width is used.

---

## 6. Cross-Cutting Design Patterns

These apply to every page, every component — non-negotiable.

### 6.1 Info tooltips (ⓘ buttons)

Every metric name, state label, gate name, chart axis label, and table column header gets an ⓘ button. The tooltip explains:
- What it means (plain English, one sentence)
- How it is calculated (formula or decision logic)
- What each possible state/value means (e.g. what "Overweight" means vs "Avoid")
- How to read this specific chart (if adjacent to a chart)

Implementation: a reusable `<InfoTooltip content={...} />` component (Radix Tooltip primitive, no animation, paper-ivory background, ink-primary text, 1px rule border).

### 6.2 Deterministic commentary blocks

Every page and major section has a synthesized analysis paragraph — a conclusion drawn from the data, not a data listing. The same DB values always produce the same text. Generated server-side as a pure function of DB values. No LLM.

Examples:
- Regime page: *"Market is in Risk-Off. 14 of 18 breadth indicators are bearish with trend, breadth, and participation all aligned. Deployment at 40%. Dislocation not active. Regime has held for 3 weeks."*
- Sector page: *"4 of 22 sectors are Overweight. Breadth is narrow — typical of late-stage corrections. Technology and Pharma showing relative strength despite weak market conditions."*
- Stock detail: *"HDFC Bank is not investable. Direction and Volume gates are failing. RS score has declined for 3 consecutive weeks. No entry trigger is present. Exit triggers: RS exit and Volume exit both active."*

Commentary is a dedicated server function per page type: `generateRegimeCommentary(regime)`, `generateSectorCommentary(sectors)`, `generateStockCommentary(stock, decision)`, etc.

---

## 7. Page Designs

### 7.1 `/` — Market Regime

**Data source:** `atlas_market_regime_daily` (latest row + last 6 months history)

**Layout (top to bottom, no sidebar):**

**Band 1 — Current state (dominant headline):**
- Regime state name as large heading: Risk-On / Constructive / Cautious / Risk-Off
- Deployment multiplier: `1.0×` / `0.7×` / `0.4×` / `0.0×`
- Dislocation badge: shown if `dislocation_active = true` (clear label, terracotta border — not a full-page alert; fund manager already knows)
- `data_as_of` timestamp
- Commentary block: 2–3 sentence deterministic analysis of current regime

**Band 2 — Regime history timeline:**
- Horizontal strip showing regime state transitions over last 6 months
- Each segment colored by state (forest/teal/ochre/terracotta)
- Each segment labeled with state name and duration (e.g. "Risk-Off · 3 wks")
- ⓘ tooltip on the timeline: explains what regime states mean and how transitions work

**Band 3 — Breadth indicators (18 indicators, full treatment):**
- Grouped into 4 categories:
  - **Trend** (MA breadth 50-day, 100-day, 200-day + any MA-based indicators)
  - **Breadth** (A/D breadth, new highs count, new lows count, highs/lows ratio)
  - **Participation** (strength breadth, RS breadth, stocks above RS threshold)
  - **Momentum** (remaining momentum indicators)
- Each category has a header with a consensus score: e.g. "Trend: 4/5 bearish"
- Each indicator row: name + ⓘ tooltip | current value | directional arrow (↑↓→) | 3-month sparkline | signal state (bullish/neutral/bearish dot)
- Category commentary: one sentence per category explaining what the group is saying
- Overall corroboration sentence at top of Band 3: "X of 18 indicators are bearish — high-conviction Risk-Off."

---

### 7.2 `/sectors` — Sector Deep Dive

**Data source:** `atlas_sector_states_daily` (latest + last 6 months per sector)

**Layout (no sidebar):**

**Commentary block:** Deterministic summary of overall sector breadth and notable outliers.

**Bubble chart:**
- All 20-22 NSE sectors plotted
- X axis: configurable (dropdown, default: `breadth_pct`)
- Y axis: configurable (dropdown, default: `momentum_score`)
- Available axes: `avg_rs_score`, `momentum_score`, `breadth_pct`, `participation_rs`, `sector_return_1m`, `sector_return_3m`, `aum_bn`
- Bubble size: `aum_bn` (AUM in ₹ crore)
- Bubble color: sector state (forest = OW, teal = Neutral, ochre = UW, terracotta = Avoid)
- Hover tooltip: all key metrics for that sector
- Click on bubble → `/sectors/[slug]`
- ⓘ on chart header: explains bubble encoding

**Sector table (below bubble chart):**
- All 20-22 sectors, one row each
- Columns: Sector | State | RS Score | Momentum | Breadth % | Participation % | 1M Return | 3M Return | AUM (₹ Cr)
- All columns sortable. Sector column has state badge. Numbers right-aligned.
- Search/filter bar above table. CSV export button.
- Click row → `/sectors/[slug]`

---

### 7.3 `/sectors/[slug]` — Instruments in Sector

**Slug format:** sector name lowercased, spaces replaced with hyphens (e.g. "Information Technology" → `information-technology`). Derived from `sector_name` column.

**Data source:** `atlas_sector_states_daily` (sector header), plus joins to `atlas_stock_states_daily` / `atlas_etf_states_daily` / `atlas_fund_states_daily` + decision tables filtered by sector

**Layout (with contextual left sidebar — full sector list):**

**Sector header:** Sector name, state badge, key metrics strip (RS score, momentum, breadth %, participation %, 1M/3M return). Commentary block: one paragraph on this sector's current state and notable instruments.

**Tabs: Stocks | ETFs | Mutual Funds**

Each tab is a sortable, filterable table:

**Stocks tab columns:** Symbol | Company | State | Investable | RS Score | Momentum | Risk | Volume | Entry Trigger | Exit Trigger
- Investable: green check / red cross
- Entry/exit triggers shown as compact badges
- Click row → `/stocks/[symbol]`

**ETFs tab columns:** Symbol | Name | State | Investable | RS Score | Momentum | Risk | Volume | Entry Trigger | Exit Trigger
- Click row → `/etfs/[symbol]`

**Mutual Funds tab columns:** Fund Name | MF Category | Recommendation | Weeks in State | Entry Trigger | Exit Trigger | Add Trigger | Reduce Trigger
- Recommendation badge colored by signal
- Click row → `/funds/[mstar_id]`

All tabs: filterable, sortable, CSV export.

---

### 7.4 `/stocks` — Stocks Screener

**Data source:** `atlas_stock_states_daily` + `atlas_stock_decisions_daily` (latest, all sectors)

**Layout (no sidebar):**

**Filter bar:** Sector (multi-select) | State (multi-select) | Investable only (toggle) | Has entry trigger (toggle) | Has exit trigger (toggle)

**Table:** Same columns as the Stocks tab in `/sectors/[slug]`, plus a Sector column. All sortable. Search by symbol/name. CSV export. Click row → `/stocks/[symbol]`.

**Commentary block:** "X of Y stocks are investable today. Entry triggers present: N. Sectors with highest investable stock density: ..."

---

### 7.5 `/etfs` — ETFs Screener

**Data source:** `atlas_etf_states_daily` + `atlas_etf_decisions_daily` (latest, all sectors)

**Layout (no sidebar):** Same pattern as `/stocks`. Filter bar, table, commentary. Click row → `/etfs/[symbol]`.

---

### 7.6 `/funds` — Funds Screener

**Data source:** `atlas_fund_states_daily` + `atlas_fund_decisions_daily` (latest)

**Layout (no sidebar):**

**Filter bar:** MF Category (multi-select) | Recommendation (multi-select) | Sector exposure (multi-select) | Has entry trigger (toggle)

**Table columns:** Fund Name | MF Category | Recommendation | Weeks in State | Entry Trigger | Exit Trigger | Add Trigger | Reduce Trigger
- All sortable. Search by fund name. CSV export. Click row → `/funds/[mstar_id]`.

**Commentary block:** "X funds are Recommended. Y funds have active entry triggers. Z funds in Reduce/Exit state."

---

### 7.7 Instrument Detail Pages

All three detail pages (`/stocks/[symbol]`, `/etfs/[symbol]`, `/funds/[mstar_id]`) follow the same two-section structure. Layout: contextual left sidebar (same-sector instruments) + main content.

#### Section 1 — Decision (top, prominent)

**Stocks and ETFs:**
- Large verdict: **Investable** (forest) or **Not Investable** (terracotta) — the first thing you see
- 6 gate booleans in a grid — each gate: name + ⓘ tooltip + pass (✓ forest) / fail (✗ terracotta) indicator:
  - Market Gate | Sector Gate | Strength Gate | Direction Gate | Risk Gate | Volume Gate
- Position size: `position_size_pct` (shown only if investable)
- Entry triggers: Transition Trigger + Breakout Trigger — each with ⓘ tooltip explaining what triggered it
- Exit triggers: 6 exit trigger booleans in a compact grid (RS exit, Momentum exit, Risk exit, Volume exit, Sector exit, Market exit)
- Commentary block: deterministic verdict sentence + explanation of which gates failed and why

**Mutual Funds:**
- Recommendation badge (Recommended / Hold / Reduce / Exit) — large, prominent
- Weeks in current state
- Trigger grid: Entry trigger | Exit trigger | Add trigger | Reduce trigger — each as a labeled badge (active = colored, inactive = muted) with ⓘ tooltip
- Commentary block: fund recommendation rationale based on trigger states and weeks in state

#### Section 2 — History (below, full detail)

**Stocks and ETFs:**
- State timeline: horizontal strip showing how this instrument's state has changed over available history (colored segments per state, same as regime timeline)
- Metric sparklines (one per metric, labeled, with ⓘ):
  - RS Score | Momentum Score | Risk Score | Volume Score
  - Gate history: small sparkline per gate showing pass/fail over time
- All sparklines share the same x-axis (date range). Hover tooltip on sparklines shows exact values.

**Mutual Funds (additional):**
- NAV history: line chart (Recharts) showing NAV over time
- Composition: donut chart showing top sector exposures (% allocation)
- Holdings snapshot: top 10 holdings table (symbol, weight %)
- Three-tuple history: how recommendation + entry/exit triggers have changed over time

---

## 8. Data Layer Architecture

**Pattern:** Every page is a Next.js Server Component. Data fetched at render time using `postgres` npm package. No `useEffect`, no client-side fetch, no SWR.

```
src/
  lib/
    db.ts                  — postgres client (server-only)
    queries/
      regime.ts            — market regime queries
      sectors.ts           — sector state queries
      stocks.ts            — stock state + decision queries
      etfs.ts              — ETF state + decision queries
      funds.ts             — fund state + decision queries
    commentary/
      regime.ts            — generateRegimeCommentary()
      sectors.ts           — generateSectorCommentary()
      stocks.ts            — generateStockCommentary()
      etfs.ts              — generateEtfCommentary()
      funds.ts             — generateFundCommentary()
  components/
    InfoTooltip.tsx        — universal ⓘ tooltip component
    StateBadge.tsx         — colored state badge (regime/sector/stock states)
    Sparkline.tsx          — single-metric sparkline (Recharts)
    StateTimeline.tsx      — horizontal state transition strip
    GateGrid.tsx           — pass/fail gate grid for stock/ETF decisions
    TriggerBadge.tsx       — entry/exit/add/reduce trigger badge
    Commentary.tsx         — deterministic analysis paragraph block
    SectorBubbleChart.tsx  — configurable bubble chart (Recharts)
    DataTable.tsx          — universal sortable/filterable/exportable table
    ContextSidebar.tsx     — contextual left sidebar (sector list / instrument list)
```

**Auth middleware (`middleware.ts`):** Password gate. Reads `ATLAS_PASSWORD` env var. Redirects unauthenticated requests to `/login`. `/login` is a simple form — submit password → set httpOnly cookie → redirect to `/`.

---

## 9. Key DB Tables (read-only)

| Table | Used on |
|---|---|
| `atlas_market_regime_daily` | `/` |
| `atlas_sector_states_daily` | `/sectors`, `/sectors/[slug]` |
| `atlas_stock_states_daily` + `atlas_stock_decisions_daily` | `/stocks`, `/stocks/[symbol]`, `/sectors/[slug]` |
| `atlas_etf_states_daily` + `atlas_etf_decisions_daily` | `/etfs`, `/etfs/[symbol]`, `/sectors/[slug]` |
| `atlas_fund_states_daily` + `atlas_fund_decisions_daily` | `/funds`, `/funds/[mstar_id]`, `/sectors/[slug]` |
| `atlas_thresholds` | Commentary generation (threshold values for ⓘ tooltips) |

All queries filter to `date = (SELECT MAX(date) FROM <table>)` for current state. History queries use `date >= NOW() - INTERVAL '6 months'` or `'3 months'` depending on context.

---

## 10. Deferred to Later Milestones

- **M7:** Supabase Auth (replace env-var password gate)
- Real-time data updates / streaming
- Client-facing investor surface (DS PDF surface 17 — "Hi Aarav" dashboard)
- Portfolio tracking, transaction history
- Alert / notification system
- Mobile-first layout (desktop-first for M6)
