# Atlas-OS M6 Frontend Design Spec

**Date:** 2026-05-08
**Milestone:** M6 — Fund Manager Research Tool (internal, auth-gated)
**Status:** Approved for implementation planning

---

## 1. Purpose and User

Atlas-OS M6 is an internal research tool for fund managers at Javeri Securities. The primary user does a daily morning review: understand the market regime, identify which sectors to express, and check instrument-level decisions before acting. This is not an investor-facing dashboard — it is a dense, analytical tool built for a professional who knows the domain.

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

**Charts allowed:** Sparklines, bar charts, donuts, line charts — no 3D, no pie, no gradient fills, no emoji

**Numbers:** Tabular-nums always. ₹ prefix. Indian lakh/crore format. Percentages always with +/− sign (green positive, red negative). Dates: DD-MMM-YYYY (IST).

**Tone:** Sentence case everywhere. No emoji. Dense information — financial professionals want detail, not summaries.

---

## 3. Tech Stack (locked)

- **Framework:** Next.js 15, App Router, React 19
- **Styling:** Tailwind v4 (CSS-first, no `tailwind.config.js`)
- **DB access:** `postgres` npm package in Server Components only (`server-only` marker). `ATLAS_DB_URL` env var.
- **Charts:** Recharts for 2D charts; raw SVG for sparklines (performance)
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
/health                    System health and run log
/thresholds                Threshold catalog (read-only in M6)
```

---

## 5. Navigation Architecture

**Top nav (always visible):**
Links: Regime | Sectors | Stocks | ETFs | Funds | Health. Current section highlighted.
Right side: `data_as_of` date (always visible so user knows data freshness) + system health dot (green = last run SUCCESS, amber = PARTIAL, red = FAILED/RUNNING) + global search input.

**Global search:** Single input in the top nav. Searches across all active stocks (symbol + company name), ETFs (ticker + name), and funds (scheme name). Instant results dropdown grouped by type. Click → instrument detail page. Keyboard navigable.

**Contextual left sidebar (appears on drill-down pages only):**
- On `/sectors/[slug]`: full sector list — current sector highlighted, click to jump between sectors without backtracking
- On `/stocks/[symbol]`, `/etfs/[symbol]`, `/funds/[mstar_id]`: list of instruments in the same sector (context preserved from navigation path), or screener results list if arrived via screener

When the contextual sidebar is absent (screener pages, regime page, health page), the full content width is used.

---

## 6. Cross-Cutting Design Patterns

These apply to every page, every component — non-negotiable.

### 6.1 Temporal controls on all charts

Every time-series chart, sparkline, and return comparison has a temporal toggle: **1W | 1M | 3M | 6M**. Default is 3M. The backend metrics tables (`atlas_stock_metrics_daily`, `atlas_etf_metrics_daily`, `atlas_fund_metrics_daily`, `atlas_index_metrics_daily`) store 1W/1M/3M/6M return columns natively; history tables provide the data for custom range sparklines.

Implementation: a `<TimeRangeToggle>` component that passes the selected range as a prop down to chart components. The range also determines how many rows to fetch from history tables.

### 6.2 Benchmark overlay on return charts

Every return chart and RS sparkline has a benchmark selector. Available benchmarks from `atlas_benchmark_master`:

| Code | Name | When shown |
|---|---|---|
| NIFTY50 | Nifty 50 | All instruments |
| NIFTY500 | Nifty 500 | All instruments |
| NIFTY100 | Nifty 100 | Large cap stocks/funds |
| MIDCAP150 | Nifty Midcap 150 | Mid cap stocks/funds |
| SMALLCAP250 | Nifty Smallcap 250 | Small cap stocks/funds |
| GOLD | Gold (GOLDBEES) | All instruments |
| MSCIWORLD | MSCI World | All instruments (global context) |
| SP500 | S&P 500 | All instruments (global context) |

Default benchmark is auto-selected based on instrument tier (e.g. Large cap stock → NIFTY100) or fund category benchmark (from `atlas_fund_category_benchmark_map`). User can override. Benchmark data is fetched from `atlas_benchmark_returns_cache` which stores daily close and returns for all benchmark codes.

The benchmark overlay on a chart shows the benchmark return indexed to 100 at the start of the selected time range. Charts show both instrument and benchmark as separate lines with a legend.

### 6.3 Info tooltips (ⓘ buttons)

Every metric name, state label, gate name, chart axis label, and table column header gets an ⓘ button. The tooltip explains:
- What it means (plain English, one sentence)
- How it is calculated (formula or decision logic)
- What each possible state/value means
- How to read this specific chart (if adjacent to a chart)
- The methodology section reference where applicable (e.g. "See methodology §7.1")

Implementation: a reusable `<InfoTooltip content={...} />` component (Radix Tooltip primitive, no animation, paper-ivory background, ink-primary text, 1px rule border). Tooltip content is defined in a central `src/lib/tooltips.ts` file — one object per metric/state/concept. Never inline.

### 6.4 Deterministic commentary blocks

Every page and major section has a synthesized analysis paragraph — a conclusion drawn from the data, not a data listing. The same DB values always produce the same text. Generated server-side as a pure function of DB values. No LLM.

Examples:
- Regime page: *"Market is in Risk-Off. 14 of 18 breadth indicators are bearish with trend, breadth, and participation all aligned. India VIX at 22.4 — above long-run median. Deployment at 40%. Regime has held for 3 weeks with no transition signals."*
- Sector divergence: *"Technology sector shows bottom-up vs. top-down divergence. The NSE IT index reads Neutral, but 68% of stocks in our universe are in Leader/Strong/Emerging states. Bottom-up signal is more reliable when divergence exists."*
- Stock detail: *"HDFC Bank is not investable. Direction and Volume gates are failing. RS score has declined for 3 consecutive weeks. Extension from 200 EMA: −4.2%. No entry trigger present. Exit triggers: RS deterioration and volume distribution both active."*

Commentary is a dedicated server function per page type: `generateRegimeCommentary()`, `generateSectorCommentary()`, `generateStockCommentary()`, etc. Located in `src/lib/commentary/`.

### 6.5 Delta / state-change indicators

All tables show change-since-last-week context:
- State change arrows: ↑ (improved) / ↓ (deteriorated) / → (unchanged) in a `Δ` column
- Newly investable stocks highlighted with a subtle forest-green left border
- Instruments that changed recommendation in the last 7 days have a badge: "NEW" / "DOWNGRADED" / "UPGRADED"
- "Changed this week" toggle on all screeners to filter to instruments with state transitions

---

## 7. Page Designs

### 7.1 `/` — Market Regime

**Data sources:**
- `atlas_market_regime_daily` — current row + last 6 months history
- `atlas_benchmark_returns_cache` — NIFTY500 price data for trend overlay
- `atlas_thresholds` — threshold values for ⓘ explanations

**Layout (top to bottom, no sidebar, full width):**

---

**Band 1 — Current state (dominant headline):**
- Regime state name as large heading (Source Serif 4, ~48px): Risk-On / Constructive / Cautious / Risk-Off
- Deployment multiplier as subtitle: `Deployment: 1.0×` / `0.7×` / `0.4×` / `0.0×` with ⓘ explaining what this means operationally
- Dislocation badge: shown if `dislocation_active = true` — terracotta badge with `dislocation_started` date. No full-page alert mode.
- India VIX: shown as a labeled number with direction arrow vs. last week. ⓘ explains VIX interpretation in Indian context.
- `data_as_of` timestamp. Nifty 500 close price + 1-day return.
- Commentary block: 2–3 sentence deterministic analysis. Covers regime state, deployment, VIX level, and regime duration.

---

**Band 2 — Regime history timeline:**
- Horizontal strip showing regime state transitions over the selected time range (default 6M)
- Each segment colored by state (forest = Risk-On, teal = Constructive, ochre = Cautious, terracotta = Risk-Off)
- Each segment labeled with state name + duration (e.g. "Risk-Off · 3 wks")
- Temporal toggle: **1M | 3M | 6M | 1Y** (regime history benefits from longer range; 1W too short)
- Below the regime strip: Nifty 500 price line chart overlaid with regime state coloring as background bands — shows price action vs. regime context
- Benchmark selector: default NIFTY500, can switch to NIFTY50

---

**Band 3 — Breadth indicators (18 indicators, full treatment):**

Organized into 4 categories. Each category has a header with a consensus score and one-sentence commentary.

**Category 1: Trend**
- `nifty500_above_ema_50` — Nifty 500 above 50-day EMA
- `nifty500_above_ema_200` — Nifty 500 above 200-day EMA
- `nifty500_ema_50_slope` — 50-day EMA slope (σ units) — ⓘ explains what positive/negative slope means
- `nifty500_ema_200_slope` — 200-day EMA slope

Each indicator: name + ⓘ | current value | direction arrow | 3M sparkline (temporal toggle applies) | signal dot (bullish/neutral/bearish)
Category consensus: "Trend: 3/4 bullish"

**Category 2: Breadth**
- `pct_above_ema_20` — % stocks above 20-day EMA
- `pct_above_ema_50` — % stocks above 50-day EMA
- `pct_above_ema_200` — % stocks above 200-day EMA
- `ad_ratio` — Advance/Decline ratio
- `ad_line_slope_21` — 21-day slope of cumulative A/D line
- `advances_count` / `declines_count` — shown as a ratio bar (advances green, declines red)
- `new_52w_highs` / `new_52w_lows` — shown as a ratio bar + net number

Each with sparkline + signal. Category consensus: "Breadth: 5/7 bearish"

**Category 3: Momentum / Oscillators**
- `mcclellan_oscillator` — with ⓘ explaining McClellan and what crossing zero means
- `mcclellan_summation` — running cumulative (sparkline especially useful here)
- `new_high_low_ratio` — `new_52w_highs / new_52w_lows`
- `net_new_highs` — net new highs as a bar chart (positive = bullish)

**Category 4: Participation / Strength**
- `pct_in_strong_states` — % of universe in Leader/Strong/Emerging
- `pct_weinstein_pass` — % passing Weinstein gate

Overall corroboration sentence above Band 3: "14 of 18 indicators are bearish — high-conviction Risk-Off signal."

Temporal toggle on all sparklines in Band 3: **1W | 1M | 3M | 6M**

---

### 7.2 `/sectors` — Sector Deep Dive

**Data sources:**
- `atlas_sector_states_daily` — current + 6M history
- `atlas_sector_metrics_daily` — bottom-up/top-down metrics + breadth
- `atlas_sector_master` — sector → index mapping
- `atlas_benchmark_returns_cache` — for sector index overlay

**Layout (no sidebar, full width):**

**Commentary block:** Deterministic summary of overall sector breadth, number of OW/Neutral/UW/Avoid sectors, notable divergences, and sectors with entry/exit conditions.

---

**Sector state heatmap (new — above bubble chart):**
Compact grid showing all 20-22 sectors × last 12 weeks as colored cells (forest/teal/ochre/terracotta). Read sector rotation at a glance — which sectors are improving, which are deteriorating, which are stable. Cell shows state. Hover tooltip shows full metrics for that sector × date.

---

**Bubble chart:**
- All 20-22 NSE sectors plotted
- X axis: configurable dropdown (default: `participation_rs` = % of stocks in Leader/Strong/Emerging)
- Y axis: configurable dropdown (default: `bottomup_ema_10_ratio` = momentum)
- Available axes: `bottomup_rs_3m_nifty500`, `bottomup_ema_10_ratio`, `bottomup_ema_20_ratio`, `participation_50`, `participation_rs`, `leadership_concentration`, `bottomup_ret_1m`, `bottomup_ret_3m`, `topdown_ret_3m`
- Bubble size: `constituent_count` (number of stocks in our universe in this sector)
- Bubble color: `sector_state` (forest = OW, teal = Neutral, ochre = UW, terracotta = Avoid)
- Divergence indicator: sectors with `divergence_flag = true` get a distinct border (dashed ochre ring)
- Hover tooltip: sector name, state, bottom-up state, top-down state, divergence flag if set, all key metrics
- Click on bubble → `/sectors/[slug]`
- Temporal toggle on axis metrics: **1M | 3M**
- Benchmark overlay: can overlay selected sector index performance
- ⓘ on chart header: explains all encoding dimensions

**Sector table (below bubble chart):**
- All 20-22 sectors, one row per sector
- Columns:
  - Sector (with state badge, click → `/sectors/[slug]`)
  - State (OW/Neutral/UW/Avoid, colored)
  - Δ (state change since last week — ↑↓→)
  - Bottom-up State
  - Top-down State
  - Divergence (flag icon if `divergence_flag = true`)
  - RS vs Nifty 500 (3M)
  - Momentum (EMA-10 ratio)
  - Breadth % (% above 50-day MA)
  - Participation % (% in Leader/Strong/Emerging)
  - Leadership Concentration (top 5 as % of sector market cap, ⓘ)
  - Constituent Count
  - 1M Return
  - 3M Return
- All columns sortable. Row click → `/sectors/[slug]`. Divergence rows highlighted.
- Filters: state filter, divergence-only toggle. Search by sector name. CSV export.
- Temporal toggle on return columns: **1M | 3M**

---

### 7.3 `/sectors/[slug]` — Instruments in Sector

**Slug format:** sector name lowercased, spaces → hyphens (e.g. "Information Technology" → `information-technology`). Derived from `atlas_sector_master.sector_name`.

**Data sources:** `atlas_sector_states_daily` + `atlas_sector_metrics_daily` for the sector header. Instrument tables filtered by sector.

**Layout (with contextual left sidebar — full sector list):**

---

**Sector header:**
- Sector name (large) + state badge + Δ change indicator
- If `divergence_flag = true`: prominent callout — "Bottom-up vs. top-down divergence: bottom-up reads [state], top-down index reads [state]." With ⓘ explaining when to trust which signal.
- Metrics strip: RS vs Nifty 500 | Momentum | Breadth % | Participation % | Leadership Concentration | Constituent Count
- Commentary block: paragraph on sector state, divergence if present, notable sub-themes.

---

**Tabs: Stocks | ETFs | Mutual Funds**

Each tab is a sortable, filterable, searchable table with CSV export.

**Stocks tab columns:**
- Symbol (JetBrains Mono) | Company Name | Tier badge (Large/Mid/Small/Micro) | Index (Nifty 50/100/500 badge if applicable)
- RS State (colored badge) | Momentum State | Risk State | Volume State
- Δ (state change this week)
- Investable (green ✓ / red ✗)
- RS Score (3M, tabular-num)
- RS Percentile (within tier, 0–100)
- Extension % (from 200 EMA) — with ⓘ
- Entry trigger badges (Transition / Breakout / Proximity)
- Exit triggers (count of active exits, e.g. "2 exits active" in terracotta)
- Click row → `/stocks/[symbol]`

Filters: RS state, momentum state, investable only, has entry trigger, has exit trigger, tier.
Temporal toggle for RS/return columns: **1M | 3M**.

**ETFs tab columns:**
- Ticker (JetBrains Mono) | ETF Name | Theme badge (Broad/Sectoral/Thematic)
- RS State | Momentum State | Risk State
- Δ
- Investable (✓ / ✗)
- RS Score | RS Percentile
- Extension %
- Entry trigger badges | Exit trigger count
- Click row → `/etfs/[symbol]`

Filters: same as stocks minus tier.

**Mutual Funds tab columns:**
- Fund Name | MF Category | AMC
- Recommendation badge (Recommended/Hold/Reduce/Exit)
- Δ recommendation change
- NAV State | Composition State | Holdings State (the three lenses)
- Weeks in current state
- Entry / Add / Reduce / Exit trigger badges (active = colored, inactive = muted)
- Click row → `/funds/[mstar_id]`

Filters: recommendation, category, has entry trigger, has exit trigger.

---

### 7.4 `/stocks` — Stocks Screener

**Data sources:** `atlas_stock_states_daily` + `atlas_stock_decisions_daily` + `atlas_stock_metrics_daily` (latest, all sectors) + `atlas_universe_stocks` (for tier/index membership/industry)

**Layout (no sidebar, full width):**

**Commentary block:** "X of Y stocks are investable today. Entry triggers active: N. Top sectors by investable density: ..."

**Filter bar:**
- Sector (multi-select, all sectors)
- Industry (multi-select, more granular than sector)
- Tier (multi-select: Large / Mid / Small / Micro)
- Index membership (multi-select: Nifty 50 / Nifty 100 / Nifty 500)
- RS State (multi-select)
- Momentum State (multi-select)
- Risk State (multi-select)
- Investable only (toggle)
- Has entry trigger (toggle: Transition / Breakout / Proximity)
- Has exit trigger (toggle)
- Changed this week (toggle: any state change since last week)

**Table columns:**
- Symbol | Company | Sector | Tier | Index badges
- RS State | Momentum State | Risk State | Volume State
- Δ (state change this week, with ↑↓→)
- Investable (✓/✗)
- RS Score (3M) | RS Percentile (within tier)
- Momentum (EMA-10 ratio)
- Extension % (from 200 EMA)
- Drawdown % (past 252 days)
- Entry triggers | Exit trigger count
- Position Size % (if investable)

All columns sortable. Search by symbol/company. CSV export. Click row → `/stocks/[symbol]`.
Temporal toggle for RS and return columns: **1W | 1M | 3M**.

---

### 7.5 `/etfs` — ETFs Screener

**Data sources:** `atlas_etf_states_daily` + `atlas_etf_decisions_daily` + `atlas_etf_metrics_daily` + `atlas_universe_etfs`

Same pattern as `/stocks`. Filter bar includes Theme (Broad/Sectoral/Thematic), Linked Sector, RS State, Momentum State, Risk State, Investable only, Has entry trigger, Has exit trigger, Changed this week.

Table columns (same as stocks screener minus tier/index, plus Theme column).

---

### 7.6 `/funds` — Funds Screener

**Data sources:** `atlas_fund_states_daily` + `atlas_fund_decisions_daily` + `atlas_fund_metrics_daily` + `atlas_universe_funds` + `atlas_fund_lens_monthly`

**Layout (no sidebar, full width):**

**Commentary block:** "X of Y funds are Recommended. Y have active entry triggers. Z in Reduce/Exit state. Category breakdown: [Large Cap: X Recommended, Y Hold...]"

**Category summary strip (above table):** Compact row of category badges showing Recommended count per MF category. Click a category → filters table to that category.

**Filter bar:**
- MF Category (multi-select)
- AMC (multi-select)
- Recommendation (multi-select: Recommended / Hold / Reduce / Exit)
- NAV State (multi-select)
- Composition State (multi-select: Aligned / Mixed / Misaligned)
- Holdings State (multi-select)
- Has entry trigger (toggle)
- Has exit trigger (toggle)
- Changed this week (toggle)

**Table columns:**
- Fund Name | MF Category | AMC
- Recommendation badge
- Δ recommendation change
- Weeks in state
- NAV State | Composition State | Holdings State
- Aligned AUM % (from `atlas_fund_lens_monthly`)
- Strong Holdings % (from `atlas_fund_lens_monthly`)
- 3M Return | 6M Return | 12M Return
- RS vs Category Benchmark (3M)
- RS Percentile (within category)
- Entry / Add / Reduce / Exit trigger badges

All sortable. Search by fund name. CSV export. Click row → `/funds/[mstar_id]`.
Temporal toggle on return columns: **1M | 3M | 6M | 1Y**.

---

### 7.7 Instrument Detail Pages

All three detail pages follow the same two-section structure: **Decision** at top, **History** below. Layout: contextual left sidebar + main content.

---

#### `/stocks/[symbol]` — Stock Detail

**Data sources:** `atlas_stock_states_daily` + `atlas_stock_decisions_daily` + `atlas_stock_metrics_daily` + `atlas_universe_stocks` + `atlas_sector_states_daily` (sector context)

**Breadcrumb:** Sectors → [Sector Name] → [Symbol]

**Instrument header:**
- Symbol (large, JetBrains Mono) + Company name + Sector badge + Tier badge + Index membership badges (Nifty 50 / 100 / 500 if applicable)
- Current price (if available) + 1D return
- `data_as_of` timestamp

---

**Section 1 — Decision:**

**Verdict block (most prominent element):**
- Large verdict: **Investable** (forest background) or **Not Investable** (terracotta background)
- Position size: `position_size_pct` — shown with breakdown tooltip: `base_size × market_multiplier × risk_multiplier = final_size`. E.g. "3% base × 1.0 market × 0.8 risk = 2.4%"

**Gate grid (6 gates):**
Each gate on its own row: gate name + ⓘ tooltip | pass (✓ forest) / fail (✗ terracotta)
- Market Gate (passes if regime is Risk-On or Constructive)
- Sector Gate (passes if sector state is Overweight or Neutral)
- Strength Gate (passes if RS state in Leader/Strong/Emerging)
- Direction Gate (passes if momentum state in Accelerating/Improving)
- Risk Gate (passes if risk state is Low or Normal)
- Volume Gate (passes if volume state is Accumulation or Steady-Buying)

**Entry trigger block (shown always — active triggers colored, inactive muted):**
- Transition Trigger (✓/✗) + ⓘ explaining what constitutes a transition
- Breakout Trigger (✓/✗) + ⓘ explaining breakout definition
- Proximity Pass (✓/✗) — "Within 5% of 20-EMA" — the entry quality qualifier

**Weinstein / Stage analysis block:**
- Above 30-week MA: ✓/✗
- 30-week MA slope (4-week): value + direction arrow + ⓘ explaining Weinstein stage model
- Stage 1 Base Qualifies: ✓/✗ + ⓘ explaining what Stage 1 base means

**Exit trigger grid (6 exits, independent):**
Compact two-column grid. Active exits in terracotta, inactive in muted ink-tertiary.
- Exit: Market Risk-Off | Exit: Sector Avoid | Exit: RS Deterioration | Exit: Momentum Collapse | Exit: Volume Distribution | Exit: Stop Loss (ATR-based)

**ATR-based stop reference:**
- ATR (21-day): `atr_21` value
- Implied stop distance: shown as % below current price (if price available)
- ⓘ explaining ATR stop calculation from methodology §13.4

**Commentary block:** Deterministic verdict paragraph. Explains which gates failed and why, whether any triggers are active, what the exit triggers mean in context.

---

**Section 2 — History:**

All history charts have temporal toggle **1W | 1M | 3M | 6M** and benchmark overlay selector.

**State timeline (top of history):**
Horizontal strip showing state transition history — one lane per state dimension (RS State / Momentum State / Risk State / Volume State), colored by state value. Same date x-axis for all four lanes. Temporal toggle applies. Hover shows exact state + date.

**Four metric sparklines (one card each):**

*RS Score card:*
- Line chart: RS score over time (vs. tier benchmark)
- Overlay option: RS vs. NIFTY500
- Gold numéraire RS toggle: show INR vs. Gold-denominated RS
- RS Percentile line (0–100 within tier) on secondary axis
- Temporal toggle

*Momentum card:*
- EMA-10 ratio over time (primary)
- EMA-20 ratio (secondary line)
- "At 20D high" / "At 20D low" events marked as dots on the line
- Temporal toggle

*Risk card:*
- Extension % (from 200 EMA) over time — positive = extended above, negative = below
- Realized volatility (63-day) as bar chart
- Drawdown ratio (252-day) as a separate line
- Horizontal reference line at 0% extension
- Temporal toggle

*Volume card:*
- Volume expansion ratio over time (avg 20D / avg 252D)
- Effort ratio (63-day)
- Raw volume bars (avg_volume_20) if price data available
- Temporal toggle

**Gate history table:**
Compact table showing, for each trading day in the selected range, which gates passed/failed. Columns: Date | Market | Sector | Strength | Direction | Risk | Volume | Investable. Color-coded. Shows how investability has changed over time. Sortable by date.

---

#### `/etfs/[symbol]` — ETF Detail

Same structure as stock detail with these differences:
- 5 gates (no Volume Gate — volume is informational for ETFs)
- 5 exit triggers (no Volume Distribution exit)
- Theme badge instead of Tier badge
- Linked Sector badge if Sectoral/Thematic ETF
- No Stage 1 base analysis section
- Volume section is labeled "Informational" — volume data shown but not gate-relevant

All other sections (decision, history, sparklines, gate history, temporal controls, benchmark overlay) are identical.

---

#### `/funds/[mstar_id]` — Fund Detail

**Data sources:** `atlas_fund_states_daily` + `atlas_fund_decisions_daily` + `atlas_fund_metrics_daily` + `atlas_fund_lens_monthly` + `atlas_universe_funds` + `atlas_fund_category_benchmark_map`

**Breadcrumb:** Funds → [Category] → [Fund Name]

**Instrument header:**
- Fund name (large) + MF Category badge + AMC
- Category benchmark: shown as "Benchmark: [benchmark_name]" (from `atlas_fund_category_benchmark_map`)
- NAV: latest value + 1-day change
- `data_as_of` + Lens disclosure lag warning: "Composition/holdings as of [last_disclosed_date] — [N] days old" if lag > 30 days

---

**Section 1 — Decision:**

**Recommendation verdict (most prominent):**
- Large recommendation badge: Recommended (forest) / Hold (slate) / Reduce (ochre) / Exit (terracotta)
- Weeks in current state: "Recommended for 6 weeks"
- Previous recommendation: "Previously: Hold" (from `last_week_recommendation`)

**4-gate grid:**
Each gate: name + ⓘ | pass/fail
- Performance Gate (NAV state ∈ Leader/Strong/Emerging NAV)
- Sectors Gate (composition_state ∈ Aligned/Mixed)
- Holdings Gate (holdings_state ∈ Strong-Holdings/Decent)
- Market Gate (regime not Risk-Off)

**Trigger grid (4 transition triggers):**
Active = colored, inactive = muted:
- Entry Trigger (recommendation became Recommended this week)
- Exit Trigger (recommendation became Exit this week)
- Reduce Trigger (recommendation became Reduce this week)
- Add Trigger (recommendation upgraded but not yet Recommended)

**4 exit condition flags:**
- Exit: Market Risk-Off
- Exit: Composition Misaligned
- Exit: Holdings Weak
- Exit: NAV Deterioration

**Commentary block:** Deterministic paragraph on recommendation rationale — which lenses are aligned, which are failing, weeks in state, and what trigger would change the recommendation.

---

**Three-lens detail cards (below decision):**

*Lens 1 — NAV Performance:*
- NAV state badge + ⓘ
- RS vs. category benchmark: 1M / 3M / 6M / 12M return comparison (instrument vs. benchmark), all as colored ±% numbers
- RS percentile within category: "Top 23% of [Category Name] funds"
- Risk: realized_vol_63, drawdown_ratio_252
- Temporal toggle on all return metrics

*Lens 2 — Sector Composition (from `atlas_fund_lens_monthly`):*
- Composition state badge (Aligned / Mixed / Misaligned) + ⓘ explaining thresholds
- Donut chart: AUM split — Overweight/Neutral sectors (forest) vs. Underweight sectors (ochre) vs. Avoid sectors (terracotta)
- Aligned AUM %: `aligned_aum_pct` — large number
- Avoid AUM %: `avoid_aum_pct` — shown in terracotta
- Sector Concentration: `sector_concentration` — top 3 sectors as % of AUM — ⓘ explains why concentration matters
- Disclosure lag indicator: "Data as of [last_disclosed_date]"

*Lens 3 — Holdings Quality (from `atlas_fund_lens_monthly`):*
- Holdings state badge (Strong-Holdings / Decent / Weak-Holdings) + ⓘ
- Stacked bar chart: AUM in Strong states (forest) | Unknown (ink-tertiary) | Weak states (terracotta)
  - Strong AUM %: `strong_aum_pct`
  - Unknown AUM %: `unknown_aum_pct` (stocks outside our universe — ⓘ explains this)
  - Weak AUM %: `weak_aum_pct`
- Holdings Concentration: `holdings_concentration` — top 10 holdings as % of AUM
- Disclosure lag indicator

---

**Section 2 — History:**

All history charts have temporal toggle **1M | 3M | 6M | 1Y** and benchmark overlay selector (default: category benchmark).

**Recommendation history strip:**
Horizontal timeline showing recommendation changes over time (colored segments). Transition trigger events marked with dots. Temporal toggle.

**NAV performance chart:**
Line chart — fund NAV indexed to 100 at start of selected range. Benchmark overlay line. 1M/3M/6M/1Y return vs. benchmark shown as a ±% badge.

**Three-lens history (monthly cadence, from `atlas_fund_lens_monthly`):**
For each month in the last 12 months:
- NAV state
- Composition state
- Holdings state
Shown as a three-lane colored timeline (one lane per lens). Hover shows exact values and metrics for that month.

**Metric sparklines:**
- RS percentile (within category) over time
- Realized volatility over time
- Drawdown ratio over time
- Aligned AUM % over time (monthly, from lens history)

---

### 7.8 `/health` — System Health

**Data sources:** `atlas_run_log` + `atlas_validation_results` + quarantine tables

**Layout (no sidebar, full width):**

**Current run status block:**
- Status badge of last run (SUCCESS / FAILED / PARTIAL / RUNNING)
- Business date, started_at, completed_at, total duration
- Rows written, rows quarantined

**Stage timing breakdown:**
Table showing each of the 9 pipeline stages with their execution time in seconds. Visual bar chart for comparison.

**Validation tier matrix:**
Grid — last 10 runs × 4 validation tiers (T1/T2/T3/T4) — green checkmarks / red crosses. Immediately shows if any tier has been persistently failing.

**Last 30 runs table:**
Columns: Date | Status | Duration | Rows Written | Quarantined | T1 | T2 | T3 | T4 | Failure Stage
Click row → see full validation results for that run.

**Validation failure drill-down (when a run row is clicked):**
All failed checks from `atlas_validation_results` for that run — check name, tier, instrument (if applicable), expected vs. actual value, deviation %.

---

### 7.9 `/thresholds` — Threshold Catalog

**Data sources:** `atlas_thresholds` + `atlas_threshold_history`

**Layout (no sidebar, full width):**

Read-only in M6. Threshold editing deferred to M7.

**Threshold table grouped by category:**
Categories: RS | Momentum | Risk | Volume | Gate | Sector | Regime | Fund | Decision

Each threshold row:
- Threshold key (JetBrains Mono) | Description | Current value | Min allowed | Max allowed | Units | Methodology section reference (linked ⓘ)
- Last modified by + date

**Threshold history:**
Click any threshold row → expand to show `atlas_threshold_history` for that key — old value → new value, changed by, reason, whether a reclassify was triggered.

---

## 8. Data Layer Architecture

**Pattern:** Every page is a Next.js Server Component. Data fetched at render time using `postgres` npm package. No `useEffect`, no client-side fetch, no SWR.

```
src/
  lib/
    db.ts                        — postgres client (server-only)
    tooltips.ts                  — all ⓘ tooltip content in one place
    queries/
      regime.ts                  — market regime queries (current + history)
      sectors.ts                 — sector state + metrics queries
      stocks.ts                  — stock state + decision + metrics queries
      etfs.ts                    — ETF state + decision + metrics queries
      funds.ts                   — fund state + decision + metrics + lens queries
      benchmarks.ts              — benchmark returns cache queries
      health.ts                  — run log + validation queries
      thresholds.ts              — threshold + history queries
    commentary/
      regime.ts                  — generateRegimeCommentary(regime, breadth)
      sectors.ts                 — generateSectorsCommentary(sectors)
      sector.ts                  — generateSectorCommentary(sector, metrics)
      stock.ts                   — generateStockCommentary(stock, decision, metrics)
      etf.ts                     — generateEtfCommentary(etf, decision, metrics)
      fund.ts                    — generateFundCommentary(fund, decision, lens)
  components/
    InfoTooltip.tsx              — universal ⓘ tooltip (Radix)
    StateBadge.tsx               — colored state badge
    Sparkline.tsx                — single-metric SVG sparkline
    LineChart.tsx                — Recharts line chart with benchmark overlay
    StateTimeline.tsx            — horizontal state transition strip
    GateGrid.tsx                 — pass/fail gate grid (stocks/ETFs/funds)
    TriggerBadge.tsx             — entry/exit/add/reduce trigger badge
    Commentary.tsx               — deterministic analysis paragraph block
    SectorBubbleChart.tsx        — configurable bubble chart (Recharts)
    SectorHeatmap.tsx            — sector rotation heatmap grid
    DataTable.tsx                — sortable/filterable/exportable table
    ContextSidebar.tsx           — contextual left sidebar
    TimeRangeToggle.tsx          — 1W/1M/3M/6M time range buttons
    BenchmarkSelector.tsx        — benchmark overlay dropdown
    DeltaBadge.tsx               — ↑↓→ state change indicator
    GlobalSearch.tsx             — cross-instrument search (Client Component)
    HealthDot.tsx                — system health status dot in nav
```

**Auth middleware (`middleware.ts`):** Password gate. Reads `ATLAS_PASSWORD` env var. Redirects unauthenticated requests to `/login`. Simple form — submit password → set httpOnly cookie → redirect to `/`. Applies to all routes except `/login`.

**`GlobalSearch.tsx` is the only Client Component** — needs interactivity for the search dropdown. All other components are Server Components or pure presentational RSCs.

---

## 9. Key DB Tables and Their Usage

| Table | Used on |
|---|---|
| `atlas_market_regime_daily` | `/` |
| `atlas_sector_states_daily` | `/`, `/sectors`, `/sectors/[slug]` |
| `atlas_sector_metrics_daily` | `/sectors`, `/sectors/[slug]` |
| `atlas_sector_master` | `/sectors`, `/sectors/[slug]`, sidebar |
| `atlas_stock_states_daily` | `/stocks`, `/stocks/[symbol]`, `/sectors/[slug]` |
| `atlas_stock_decisions_daily` | `/stocks`, `/stocks/[symbol]`, `/sectors/[slug]` |
| `atlas_stock_metrics_daily` | `/stocks`, `/stocks/[symbol]` |
| `atlas_etf_states_daily` | `/etfs`, `/etfs/[symbol]`, `/sectors/[slug]` |
| `atlas_etf_decisions_daily` | `/etfs`, `/etfs/[symbol]`, `/sectors/[slug]` |
| `atlas_etf_metrics_daily` | `/etfs`, `/etfs/[symbol]` |
| `atlas_fund_states_daily` | `/funds`, `/funds/[mstar_id]`, `/sectors/[slug]` |
| `atlas_fund_decisions_daily` | `/funds`, `/funds/[mstar_id]`, `/sectors/[slug]` |
| `atlas_fund_metrics_daily` | `/funds`, `/funds/[mstar_id]` |
| `atlas_fund_lens_monthly` | `/funds`, `/funds/[mstar_id]`, `/sectors/[slug]` |
| `atlas_universe_stocks` | `/stocks`, `/stocks/[symbol]` (tier, index membership, industry) |
| `atlas_universe_etfs` | `/etfs`, `/etfs/[symbol]` (theme, linked sector) |
| `atlas_universe_funds` | `/funds`, `/funds/[mstar_id]` (category, AMC, benchmark) |
| `atlas_benchmark_master` | All pages (benchmark names for selectors) |
| `atlas_benchmark_returns_cache` | All return charts (benchmark overlay data) |
| `atlas_fund_category_benchmark_map` | `/funds/[mstar_id]` (category benchmark) |
| `atlas_thresholds` | `/thresholds`, ⓘ tooltips throughout |
| `atlas_threshold_history` | `/thresholds` (history drill-down) |
| `atlas_run_log` | `/health`, top nav health dot |
| `atlas_validation_results` | `/health` (failure drill-down) |

**Query pattern for current state:** `WHERE date = (SELECT MAX(date) FROM <table>)`

**Query pattern for history:** `WHERE date >= NOW() - INTERVAL '<n> months'` with appropriate `n` per temporal toggle (1W = 7 days, 1M = 30 days, 3M = 90 days, 6M = 180 days)

---

## 10. State Reference

### Stock / ETF states

| Dimension | Values |
|---|---|
| RS State | Leader, Strong, Emerging, Average, Consolidating, Weak, Laggard, INSUFFICIENT_HISTORY, ILLIQUID, DISLOCATION_SUSPENDED |
| Momentum State | Accelerating, Improving, Flat, Deteriorating, Collapsing, + suspended variants |
| Risk State | Low, Normal, Elevated, High, Below Trend |
| Volume State | Accumulation, Steady-Buying, Neutral, Distribution, Heavy Distribution (informational for ETFs) |

### Sector states

| State | Meaning |
|---|---|
| Overweight | Express sector — strong RS and momentum |
| Neutral | Hold current exposure |
| Underweight | Reduce, do not add |
| Avoid | No exposure |

### Fund states

| Lens | Values |
|---|---|
| NAV State | Leader NAV, Strong NAV, Emerging NAV, Average NAV, Weak NAV, Laggard NAV + suspended |
| Composition State | Aligned, Mixed, Misaligned |
| Holdings State | Strong-Holdings, Decent, Weak-Holdings |

### Regime states

| State | Deployment |
|---|---|
| Risk-On | 1.0× |
| Constructive | 0.7× |
| Cautious | 0.4× |
| Risk-Off | 0.0× |
| DISLOCATION_SUSPENDED | 0.0× |

---

## 11. Deferred to Later Milestones

- **M7:** Supabase Auth (replace env-var password gate)
- **M7:** Threshold editing UI (currently read-only at `/thresholds`)
- Fund holdings detail (individual stock weights within a fund) — no `atlas_fund_holdings` table in v0; only aggregate lens metrics available
- "Funds that hold this stock" cross-reference — requires holdings table (M7+)
- Real-time data updates / streaming
- Client-facing investor surface (DS PDF surface 17)
- Portfolio tracking, transaction history, P&L
- Alert / notification system (email/Slack on state changes)
- Mobile-first layout (desktop-first for M6; advisors use large screens)
- Threshold tuning UI with reclassify trigger
