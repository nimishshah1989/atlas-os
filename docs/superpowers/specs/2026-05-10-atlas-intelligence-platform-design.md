# Atlas OS — Intelligence Platform Design Spec
**Date:** 2026-05-10  
**Status:** CEO review ✓ | Design review ✓ | Ready for implementation plan  
**Scope:** Stocks, ETFs, Funds, Sectors, Regime pages + shared design system  

---

## 1. Philosophy and Success Criteria

Atlas OS is not a dashboard. It is an intelligence tool built on a single philosophy: **price and volume data, processed through relative strength and momentum states, produces the best investment decisions across any time horizon** — intraday to multi-year.

The tool serves one unified view. A single fund manager uses the same screens whether constructing a PMS portfolio, evaluating MF distribution, or managing RA/RIA allocations. The time horizon and risk tolerance are variables controlled by the manager through filters and period selectors — not by separate modes or views.

**Success KPI:** The tool generates alpha with lower risk than benchmarks for different investor types across different horizons, with minimal dependency on any external system. A fund manager should be able to make 90% of decisions without leaving Atlas.

**Data coverage target:** >90% of computed backend metrics are surfaced in the UI. Current state is ~20% for stocks and ETFs, 0% for funds and indices. This spec closes that gap.

---

## 2. Core Design Principles

### 2a. No Black Boxes
Every metric, chip, bar, and number has a tooltip (`MetricTooltip`) that explains:
- What it is (plain English, one sentence)
- How it is calculated (formula or description)
- What a high/low value means for decision-making
- Historical median for context

### 2b. State + Value Together
State chips never appear alone. They always show the most relevant scalar alongside:
- RS State → RS pctile: **`Leader · 89`**
- Momentum State → period return: **`Accel · +3.2%`**
- Risk State → realized vol: **`Low · 28%`**
- Volume State → volume ratio: **`Accum · 1.4×`**

Implementation: `StateValuePair` component (chip left, scalar right, same line, monospaced scalar).

### 2c. All Time Periods, Both Benchmarks
Period selector (1W / 1M / 3M / 6M / 1Y) lives in every page header and drives:
- Return columns (shows the selected period's return)
- RS pctile column (switches to `rs_pctile_1w/1m/3m` for those periods; for 6M and 1Y, falls back to `rs_pctile_3m` with a "(3M)" label suffix indicating the closest available window)
- Bubble chart Y-axis

Benchmark selector (Nifty 500 ₹ / Gold) drives RS comparative columns.

State chips do **not** change with period — they are point-in-time classifications, not period-based. A subtle "fixed" indicator in the column header communicates this.

Period and benchmark are URL params (`?period=3M&benchmark=NIFTY500`) for shareability.

### 2d. Everything Is Clickable and Cross-Navigating
- Every ticker → instrument deep dive
- Every sector name → sector page
- Every state chip → filters screener to that state
- Every metric tile → filters screener to that dimension
- Every bubble → instrument deep dive
- Every ENTER label → shows investable stocks in that sector
- Every breadth number → stocks screener filtered to that state

### 2e. Deterministic Commentary
Every page has a `CommentaryBlock` — a rule-based synthesis panel that reads current data and produces a 3-5 sentence narrative answering: what does this data mean right now? What does history say about this setup? What should I watch for?

These are NOT AI-generated. Same input always produces same output. Every sentence is traceable to a specific data point or historical query. The commentary is one of the most visible surfaces — it must be accurate and honest, including when the signal is weak or ambiguous.

### 2f. Easy to Extend
The design system is built so that adding a column, changing a metric, or adding a new commentary rule is isolated:
- New screener column = one object in a `COLUMN_CONFIG` array
- New commentary rule = one condition in the `buildCommentary()` function
- New metric tile = one tile definition in `MetricTileRow`
- New tooltip = one entry in `METRIC_DEFINITIONS` config

---

## 3. Design System — New Shared Components

All of these live in `frontend/src/components/ui/` and `frontend/src/lib/`.

### Chart Color Token Map

**Library split:** Bubble charts (Stocks, ETF, Funds, Sectors) use **Recharts** `ScatterChart` — they update the existing `stockColor()` function to return `CHART_COLORS` values. New D3 components (RRGChart, BreadthWaterfall, StateJourneyTimeline, MarketTreemap) use `CHART_COLORS` via `.attr('fill', CHART_COLORS.rs[state])`. All charts MUST use these exact hex values — sourced from `globals.css` design tokens, NOT from Tailwind's default color palette:

```typescript
// lib/chart-colors.ts — single source of truth for all D3 charts
export const CHART_COLORS = {
  // RS state colors (bubble chart, screener chips)
  rs: {
    Leader:       '#2F6B43',  // --signal-pos (forest green)
    Strong:       '#1D9E75',  // --teal (product extension)
    Emerging:     '#25394A',  // --accent (slate)
    Consolidating:'#B8860B',  // --signal-warn (ochre)
    Average:      '#9A8F82',  // --ink-4
    Weak:         '#B0492C',  // --signal-neg (terracotta)
    Laggard:      '#8B3520',  // --signal-neg darkened
  },
  // Momentum state (trajectory arrows, heatmap)
  momentum: {
    Accelerating:  '#2F6B43',
    Improving:     '#1D9E75',
    Flat:          '#9A8F82',
    Deteriorating: '#B8860B',
    Collapsing:    '#B0492C',
  },
  // Regime context (ForwardReturnChart regime bands)
  regime: {
    'Risk-On':    '#2F6B43',  // forest green fill, opacity 0.15
    'Cautious':   '#B8860B',  // ochre fill, opacity 0.15
    'Risk-Off':   '#B0492C',  // terracotta fill, opacity 0.15
  },
  // Chart infrastructure
  axisLine:     '#C2B8A8',  // --paper-rule
  axisText:     '#9A8F82',  // --ink-4
  gridLine:     '#DDD3BF',  // --ink-rule (dashed)
  background:   '#F8F4EC',  // --paper
}
```

**Sprint 1 color fix:** `StockBubbleChart.tsx` (stocks/ and sectors/) currently use wrong Tailwind hex in `stockColor()` (`#f59e0b` for Consolidating, `#0ea5e9` for Emerging, `#94a3b8` for Average, `#ef4444` for Weak/Laggard). Update to `CHART_COLORS` values. Also fix `RSPctileBar` + `PosSizeBar` inline style hex in `stock-formatters.tsx`. Note: these are **Recharts** components, not D3 — the fix is a function update, not a library migration.

### `StateValuePair.tsx`
```
Props: state, stateKind ('rs'|'momentum'|'risk'|'volume'), value, valueColor
Renders: [StateChip] [scalar value]
Used in: all screener tables, deep dive headers
```
Visual anatomy (DESIGN.md tokens):
```
Container: inline-flex, items-center, gap-1.5  (6px gap)
  [StateChip: existing pattern — 10px Inter 600, uppercase, 2px radius, tinted bg/text by state]
  [scalar: JetBrains Mono 12px, tabular-nums, color = valueColor or inherit from chip]
```

### `InstrumentPageShell.tsx`
```
Props: title, stats[], period, benchmark, availableBenchmarks, children
Renders: header band with title + stats summary + TimeRangeToggle + BenchmarkSelector
Used in: stocks, etfs, funds, sectors pages
```
Replaces the copy-pasted header pattern across 3 pages.

### `MetricTileRow.tsx`
```
Props: tiles[] (kind: 'number'|'chip'|'gate'|'bar', label, value, color, onClick)
Renders: responsive grid of KPI tiles, each clickable
Used in: top of all 4 instrument pages
```
Replaces hardcoded `StockSnapshotTiles` which is stocks-specific.
Visual anatomy (DESIGN.md tokens):
```
Grid: flex flex-wrap gap-3 (wraps at breakpoints)
Each tile: 1px --paper-rule border, 2px radius, px-4 py-3, cursor-pointer
  hover: bg-paper-soft (no shadow, no transform — DESIGN.md motion rules)
  active: bg-paper-deep
  Eyebrow label: font-sans text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-tertiary
  Primary value: font-mono text-xl font-medium text-ink-primary tabular-nums (kind='number')
              or existing StateChip (kind='chip')
              or PosSizeBar (kind='bar')
  Delta text: font-mono text-[11px] text-signal-pos/neg mt-0.5 (sign-colored)
  Min width: 120px. Max: 180px. At <768px: 4 tiles per row → 2 per row
```

### `MetricTooltip.tsx`
```
Props: metricKey (looks up METRIC_DEFINITIONS config)
Renders: (i) icon with popover on hover showing definition + formula + context
Used in: every table column header, every metric tile
```

### `CommentaryBlock.tsx`
```
Props: commentary (CommentaryOutput object with lines[], insightCards[], actionSignal)
Renders: text block with teal left-border + 1-3 insight cards below
Used in: stocks, etfs, funds, sectors pages
```
Visual anatomy (DESIGN.md tokens):
```
Container: border-l-[3px] border-teal pl-3 py-1
Commentary lines: font-sans text-[13px] leading-[1.5] text-ink-secondary
  — each line separated by mt-1
Action signal (if present): font-sans text-xs font-semibold text-teal mt-2 uppercase tracking-wider
Insight cards (below, gap-2): 1px --paper-rule border, 2px radius, px-3 py-2
  Eyebrow: font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary
  Value: font-mono text-sm font-medium text-ink-primary
  Label: font-sans text-[11px] text-ink-secondary mt-0.5
```

### `ForwardReturnChart.tsx`
```
Props: filterState (active screener filter combination), instrumentType ('stock'|'etf'|'fund')
Note: no 'period' prop — chart always renders all 4 forward windows (1M/3M/6M/1Y) simultaneously as a grouped box-whisker. Period selector on the parent page does NOT affect this chart.
Renders: box-whisker chart (approved in DESIGN.md) of historical forward returns for stocks matching this filter, 4 grouped windows side by side (1M/3M/6M/1Y), regime background bands at opacity 0.12
Data: reads from atlas_forward_return_precompute via filter_hash lookup; on-demand fallback if hash not found
Used in: stocks page Band 3, ETF page Band 3
```

### `StateJourneyTimeline.tsx`
```
Props: ticker, instrumentType, years (default 5)
Renders: horizontal multi-lane timeline (4 lanes: RS/Mom/Risk/Vol) with price chart overlay
Annotations: event markers (COVID, rate cycles, elections, budget dates) as vertical lines
Regime bands: shaded background per regime state
Used in: stock deep dive, ETF deep dive, fund deep dive history tab
```

### `RRGChart.tsx` (Relative Rotation Graph)
```
Props: sectors[] with {name, rs_score, rs_momentum, momentum_state, constituent_count}
  rs_score: sourced from atlas_sector_metrics_daily.bottomup_rs_3m_nifty500 (normalized around 0 for chart centering)
  rs_momentum: computed via self-join CTE (bottomup_rs_3m_nifty500_today - bottomup_rs_3m_nifty500_20d_ago)
Renders: D3 scatter chart, 4 quadrants (Leading=top-right / Weakening=bottom-right / Improving=top-left / Lagging=bottom-left)
Each sector: dot + 4-week trailing arrow showing direction
Click: navigates to sector deep dive
Used in: sectors page (Rotation View tab)
```

### `BreadthWaterfall.tsx`
```
Props: breadthHistory[], regimeHistory[], events[]
Renders: dual-line chart (breadth % + index price) with regime-shaded background + event markers
Used in: sectors page, regime page enhancements, sector deep dive
```

### `MarketTreemap.tsx`
```
Props: stocks[] (with sector, market_cap, rs_state)
Renders: D3 treemap, outer = sector, inner = stocks, size = market cap, color = RS state
Click sector: zoom in; click stock: navigate to deep dive
Used in: stocks page (new "Market Map" view)
```

### `StateTransitionCard.tsx`
```
Props: transitions[] ({sector, from_state, to_state, days_ago, direction})
Renders: compact list of recent sector state upgrades/downgrades
Used in: sectors page header area
```

### `screener-utils.tsx` (lib)
```
Exports: SortTh, SortIcon, stateRank() (currently duplicated in 3 screeners)
```

### `bubble-chart-utils.ts` (lib)
```
Exports: QUADRANT_CONFIGS, RS_STATE_COLOR, bubbleTooltipFormatter, logScale()
```

### `METRIC_DEFINITIONS` config (lib)
```
A single config object keyed by metric name.
Each entry: { label, description, formula, highMeans, lowMeans, historicalMedian }
All MetricTooltip components look up this config.
Adding a new metric = one object in this file.
```

### `EVENT_LIBRARY` config (lib)
```
Named market events with dates and descriptions.
Used by StateJourneyTimeline and BreadthWaterfall for annotation.
Events: COVID crash, 2022 rate hike cycle, Adani crisis, 2024 election, Budget dates (annual), 
        Global events (Fed pivots, China slowdowns, SVB collapse)
Maintained as a config file — never hardcoded in components.
```

---

## 4. Stocks Page

### Structure: 4 bands

**Band 1 — 8 Metric Tiles (MetricTileRow)**
| Tile | Data source | Click action |
|---|---|---|
| INVESTABLE | count of is_investable=true | Filters screener to investable |
| LEADER / STRONG | count of rs_state in (Leader,Strong) | Filters screener to those states |
| IMPROVING MOM | count of momentum_state in (Accelerating,Improving) | Filters screener |
| ABOVE 30W MA | count of above_30w_ma=true | Filters screener |
| VOL EXPANDING | count of volume_state IN ('Accumulation','Steady-Buying') | Filters screener to those states |
| MEDIAN RS PCTILE | median rs_pctile_3m across universe | No filter |
| MEDIAN {period} RET | median return for selected period | No filter |
| MEDIAN VOL 63D | median realized_vol_63 | No filter |

All tiles show delta vs prior week in small secondary text. All have MetricTooltip.

**Band 2 — Stock Bubble Chart (left 65%) + Intelligence Panel (right 35%)**

*Bubble chart:*
- X axis: realized_vol_63 (annualised %)
- Y axis: return for selected period (ret_1w / ret_1m / ret_3m / ret_6m / ret_12m)
- Bubble size: avg_volume_20 (log-scaled within cohort)
- Colour: RS state (Leader=dark green, Strong=teal, Emerging=blue, Consolidating=amber, Average=slate, Weak/Laggard=red)
- Responsive container (aspect-ratio: 16/9, min 360px)
- Period selector drives Y axis
- Benchmark selector drives colour semantics (₹ RS vs Gold RS)
- Quadrant labels: Quality Uptrend (low vol, positive return) / High Beta (high vol, positive return) / Quiet Drift (low vol, negative return) / Danger Zone (high vol, negative return)
- Quadrant divider: dynamic median volatility of current cohort
- Hover: quick-peek panel slides in showing ticker, all 4 state chips with values, key numbers, "Open →" link
- Click: navigate to stock deep dive
- Cohort filter (N50 / N100 / N500 / All) syncs with screener

*Intelligence Panel (right side) — stacking order top to bottom:*
1. CommentaryBlock: 4-5 sentences on current market breadth, leadership quality, regime context, historical forward return for current conditions — appears FIRST so the synthesis orients the data below
2. RS State Distribution: horizontal stacked bar + list with count and % for each state, bars clickable to filter screener
3. Momentum Distribution: Accelerating/Improving/Flat/Deteriorating/Collapsing bars with counts
4. Investable Today: top 3-4 stocks passing all 6 gates, shown as mini cards (ticker, sector, RS pctile, period return, size %) — appears last as the call-to-action conclusion

**Band 3 — Forward Return Distribution (collapsible, collapsed by default)** *(ships Sprint 5 — show "Historical signal coming soon" placeholder in Sprints 1-4)*
A `ForwardReturnChart` showing: for all stocks currently passing the active screener filters, what were the historical 1M / 3M / 6M / 1Y forward returns? Box-whisker per period, coloured by regime (green = Risk-On, amber = Cautious, red = Risk-Off). Shows median, IQR, hit rate (% positive). Updates as user changes filters. Answers: "if this signal has worked before, what has it produced?"

**Band 4 — Screener Table**

Columns:
| Column | Data | Notes |
|---|---|---|
| TICKER + Name | — | Links to deep dive |
| SECTOR | sector | Clickable → sector page |
| RS STATE | StateValuePair(rs_state, rs_pctile) | Chip + pctile number |
| MOM | StateValuePair(momentum_state, ret_period) | Chip + selected period return |
| RISK | StateValuePair(risk_state, realized_vol_63) | Chip + vol % |
| VOL | StateValuePair(volume_state, volume_expansion) | Chip + ratio |
| {period} RET | ret_1w / ret_1m / ret_3m / ret_6m / ret_12m | Selected by period toggle |
| RS ₹ | rs_pctile_{period} — falls back to `rs_pctile_3m` with "(3M)" label for 6M/1Y | Bar visualization |
| RS GOLD | `rs_{period}_tier_gold` (stocks table column name) — signed number, color-coded; DB only has 1w/1m/3m variants; for 6M/1Y period selector use `rs_3m_tier_gold` with "(3M)" label; null shown as `—` |
| EXTENSION | extension_pct | % above/below EMA 200 |
| VOL 63D | realized_vol_63 | Annualised % |
| DRAWDOWN | drawdown_ratio_252 | vs benchmark drawdown |
| DAYS IN STATE | computed: days since last rs_state change | Integer |
| GATES | 6 dots (history, liquidity, weinstein, stage1, strength, direction) — history/liquidity/weinstein/stage1 from `atlas_stock_states_daily`; strength/direction from `atlas_stock_decisions_daily` (requires JOIN) | Green/grey per gate pass |
| DEPLOY % | position_size_pct | Bar visualization |
| DECISION | derived from states + gates | ENTER / WATCH / PASS / EXIT |
| + | Add to portfolio | Icon button |

All column headers have MetricTooltip. Table supports column show/hide. Screener has:
- Search (ticker or name)
- Sector filter (dropdown)
- Period selector (syncs with page)
- Benchmark selector (syncs with page)
- Filter chips: All / N50 / N100 / N500 / Large / Mid / Small / Investable / Leader / Strong / Breakout / Exit Flag
- Sort on any column
- Expandable row: click chevron → shows compact StateJourneyTimeline (last 90 days, 4 states)

**Stock deep dive page — additions to existing:**
- StateJourneyTimeline: 5Y view with price overlay, event markers, regime bands
- CommentaryBlock: days in state + transition probability + sector context + regime fit + "last 5 similar setups returned..."
- RS pctile chart gets regime overlay (shaded bands matching regime state on each date)
- State heatmap range becomes user-selectable (1M / 3M / 6M / 1Y / 3Y / 5Y)
- All 4 state chips in header become StateValuePair

---

## 5. ETF Page

### Structure: 4 bands (mirrors stocks pattern)

**Band 1 — 7 Metric Tiles**
INVESTABLE ETFs · LEADER/STRONG · BROAD ETFs (42) · SECTORAL ETFs (95) · THEMATIC (43) · MEDIAN {period} RET · MEDIAN RS PCTILE

**Band 2 — Bubble Chart + Intelligence Panel**
- X: realized_vol_63
- Y: selected-period return
- Size: effort_ratio_63 (volume quality proxy)
- Colour: RS state
- Filter chips: All / Broad / Sectoral / Thematic / Investable

Intelligence panel:
- Theme Distribution breakdown (Broad/Sectoral/Thematic/International/Gold) with investable count per theme
- Gold vs ₹ RS comparison: which benchmark is rewarding more right now, with historical context
- CommentaryBlock: cross-theme RS narrative, defensive vs equity signal, investable count context

**Band 3 — Forward Return Distribution (collapsible, collapsed by default)** *(ships Sprint 5 — placeholder in Sprints 1-4)* (same pattern as stocks, ETF-filtered)

**Band 4 — Screener**
| Column | Data |
|---|---|
| TICKER + Name | Links to ETF deep dive |
| THEME | ThemeBadge (Broad/Sectoral/Thematic) |
| RS STATE | StateValuePair(rs_state, rs_pctile) |
| MOMENTUM | StateValuePair(momentum_state, ret_period) |
| RISK | StateValuePair(risk_state, realized_vol_63) |
| VOL | StateValuePair(volume_state, volume_expansion) — volume_state is computed for ETFs; include chip |
| {period} RET | period-selected return |
| RS ₹ | `rs_{period}_benchmark` (ETF DB column name, distinct from stocks' `rs_{period}_tier`) — color bar |
| RS GOLD | `rs_{period}_benchmark_gold` (ETF DB column name, distinct from stocks' `rs_{period}_tier_gold`) — ETF DB only stores 1w/1m/3m Gold variants; 6M/1Y period selector shows `—` (no Gold data at those windows) |
| RS PCTILE | `rs_pctile_{period}`, bar |
| EXTENSION | extension_pct |
| REALIZED VOL | realized_vol_63 |
| DRAWDOWN RATIO | drawdown_ratio_252 |
| VOL EXPANSION | volume_expansion, ratio |
| EFFORT RATIO | effort_ratio_63 |
| GATES | 3 dots (history, liquidity, weinstein) |
| DEPLOY % | position_size_pct, bar |
| DECISION | ENTER / WATCH / PASS |
| + | Add to portfolio |

**ETF deep dive — additions:**
StateJourneyTimeline (5Y), CommentaryBlock with benchmark comparison context, regime overlay on RS charts.

---

## 6. Funds Page — New, Built from Scratch

Full backend exists (4 tables, ~60 columns). Zero frontend today.

### Structure: 4 bands

**Band 1 — 7 Metric Tiles**
RECOMMENDED (18) · HOLD (64) · LEADER/STRONG NAV (82) · ALIGNED COMPOSITION (112) · STRONG HOLDINGS (94) · MEDIAN {period} RET · MEDIAN RS PCTILE
Note: nav_state DB values carry ` NAV` suffix (e.g., `'Leader NAV'`, `'Strong NAV'`) — filter using exact values, not bare `'Leader'`/`'Strong'`

**Period selector note:** `atlas_fund_metrics_daily` has `ret_1m / ret_3m / ret_6m / ret_12m` only — no `ret_1w`. The Funds page period selector is **1M / 3M / 6M / 1Y** (omit 1W). Similarly, `rs_{period}_category` exists for 1m/3m/6m only; for 1Y period selector, fall back to `rs_6m_category` with "(6M)" label. All screener columns show `—` for any missing period.

**Band 2 — Bubble Chart + Intelligence Panel**
- X: realized_vol_63
- Y: selected-period return (ret_1m / ret_3m / ret_6m / ret_12m)
- Size: drawdown_ratio_252 (inverted: larger bubble = lower drawdown = better risk profile)
- Colour: nav_state (values: `'Leader NAV'`/`'Strong NAV'`/`'Average NAV'`/`'Weak NAV'`/`'Laggard NAV'`/`'Emerging NAV'` — strip ` NAV` suffix for color-map lookup against the standard RS state color table)
- Filter chips: All / Equity / Hybrid / Debt / Large Cap / Mid Cap / Flexi Cap / Recommended

Intelligence panel:
- NAV State Distribution: bars per state with count + %
- Category performance: which categories are leading on RS pctile
- CommentaryBlock: fund universe quality, recommendation distribution context, historical forward return for current Recommended funds

**Band 3 — Forward Return Distribution (collapsible, collapsed by default)** *(ships Sprint 5 — placeholder in Sprints 1-4)* (filtered to Recommended funds historically)

**Band 4 — Screener**
| Column | Data |
|---|---|
| FUND NAME + AMC | mstar_id lookup, links to fund deep dive |
| CATEGORY | Large Cap / Mid Cap / Flexi Cap / etc |
| NAV STATE | StateValuePair(nav_state, rs_pctile) |
| COMPOSITION | Inline 3-segment bar (aligned=green, avoid=red, neutral=grey) + composition_state label |
| HOLDINGS | Inline 3-segment bar (strong=green, weak=red, unknown=grey) + holdings_state label |
| {period} RET | ret_1m / ret_3m / ret_6m / ret_12m |
| RS vs CATEGORY | rs_{period}_category, signed |
| RS PCTILE | rs_pctile_{period}, bar |
| REALIZED VOL | realized_vol_63 |
| DRAWDOWN RATIO | drawdown_ratio_252 |
| WEEKS IN STATE | weeks_in_current_state |
| GATES | 4 dots (performance, sectors, stocks, market) |
| RECOMMENDATION | chip (Recommended/Hold/Reduce/Exit) + trigger flag if entry/exit triggered this week; `DISLOCATION_SUSPENDED` state shown as grey chip with tooltip "Market dislocation — recommendation suspended" |
| + | Add to portfolio |

**Fund deep dive:**
- Lens 1: NAV state journey timeline, RS pctile vs category chart
- Lens 2: Composition detail — aligned sectors vs avoid sectors, concentration
- Lens 3: Holdings breakdown — % in Leader/Strong/Average/Weak stocks by AUM, top holdings RS states
- Decision history: was this fund Recommended → Hold → Reduce over time? Timeline view
- CommentaryBlock: weeks in state, all 4 gates status, entry/exit trigger context

---

## 7. Sectors Page — Additive on Existing

Current: bubble chart + decision table + heatmap. All kept. New: tab navigation + 2 new views + enhancements.

### Tab Navigation
`[Rotation Matrix] [Decision Table] [State History] [Relative Rotation Graph]`

**Header — Sector Transitions Card (always visible above tabs)**
Auto-detects sector state changes in last 1W and 1M:
> "Banking: Neutral → Overweight 12 days ago · IT: Overweight → Neutral 5 days ago · FMCG: beginning Improving trajectory"
Clickable entries navigate to that sector's decision table row.

**Tab 1 — Rotation Matrix (existing, enhanced)**
- Bubble trajectory arrows: ghost position from 4W ago → current position, arrow shows direction
- Richer hover tooltip: RS number, breadth %, leadership concentration bar, top 2 investable stocks in sector, mini 4-week state sparkline
- State chips on bubbles are clickable → filters decision table

**Tab 2 — Decision Table (existing, enhanced)**
- Add columns: ret_1w, ret_6m, trend sparkline (RS pctile 30D), DAYS IN STATE
- State chips → StateValuePair
- ENTER badge → hover shows top 3 investable stocks in that sector
- All columns have MetricTooltip
- CommentaryBlock above table: rotation signal narrative + pattern match + action signal

**Tab 3 — State History (existing, enhanced)**
- Shows `bottomup_rs_state` (Leader/Strong/etc. — column name in `atlas_sector_states_daily`, not `rs_state`) alongside Overweight/Neutral decisions
- Range selector: 1M / 3M / 6M / 1Y / 3Y — not hardcoded
- Event markers: vertical lines for COVID crash, 2022 rate cycle, 2023 Adani, 2024 election, Budget dates

**Tab 4 — Relative Rotation Graph (new)**
X axis: `bottomup_rs_3m_nifty500` — the sector's bottom-up RS vs Nifty 500 (from `atlas_sector_metrics_daily`). Normalized around 0 for chart centering.
Y axis: RS momentum — computed as `(bottomup_rs_3m_nifty500_today - bottomup_rs_3m_nifty500_20d_ago)`. Self-join in the sectors query CTE. New sectors with <20 days of history will have NULL rs_momentum and are excluded from the RRG with an "insufficient history" note.
Quadrants: Leading (top-right, high RS + rising momentum) / Weakening (bottom-right, high RS + falling momentum) / Improving (top-left, low RS + rising momentum) / Lagging (bottom-left, low RS + falling momentum)
Each sector: labelled dot + 4-week trailing arrow showing trajectory direction
Bubble size: constituent count
Colour: momentum_state
Click: sector deep dive
This is the institutional rotation tool — tells you which sectors to enter, hold, and exit in one view.

**Sector deep dive — additions**
- BreadthWaterfall chart: % Leader/Strong within sector over 2-3Y, regime bands, event markers. The leading indicator for early sector rotation detection.
- Top-down vs bottom-up reconciliation panel: explicit panel when divergence_flag=true, explaining the conflict with both signals and what to watch for convergence
- Constituent count shown prominently with "small sample" warning if <10 stocks
- SectorStocksTab uses full InstrumentScreener component pre-filtered to sector — not a separate simplified component

---

## 8. Regime Page — Targeted Additions

**Route:** `/` (root — this is the app homepage, not `/regime`)  
Current regime page is the strongest in the product. Additions only.

**Duration context (prominent)**
"In Cautious regime for 23 days" shown in the header band alongside the regime state. Historical median duration for this regime state shown as comparison: "median: 31 days · longest: 94 days · shortest: 4 days"

**Historical Precedents Card**
"Last 3 times we were in Cautious regime with breadth at this level (pct_above_ema_50 between 40-50%):
- Mar 2023: regime lasted 14 more days, Nifty 500 returned +2.1% over next 3M
- Sep 2022: regime lasted 31 more days, Nifty 500 returned −3.4% over next 3M
- Jun 2020: regime lasted 8 more days, Nifty 500 returned +18.2% over next 3M
Median forward 3M: +2.1%. Distribution is wide — regime exit timing matters more than direction."

**Transition Signal Card**
Rule-based early warning: "3 of 5 early-warning breadth signals have triggered (McClellan summation declining 5+ days, new highs declining, pct_above_ema_20 < pct_above_ema_50). Historical false-positive rate at this reading: 22%. Monitor for confirmation over next 5-7 sessions."

**BreadthWaterfall enhancement**
Add named event markers to existing breadth charts (COVID, rate cycles, election dates). The charts already exist — this is annotation only.

**Regime-to-screener links**
Breadth numbers (e.g., "214 stocks in Accumulation state") link to the stocks screener filtered to that state. Makes regime page a navigation hub.

---

## 9. Historical Intelligence Layer

### 9a. Forward Return Distribution
**Location:** Stocks page Band 3, ETF page Band 3, accessible from any screener via "Historical Signal" button  
**How it works:** For the current active filter combination (e.g., rs_state=Leader, momentum_state=Accelerating, risk_state=Low, weinstein_gate_pass=true), query all historical dates when these criteria were met, then compute forward returns at 1M/3M/6M/1Y from each such date. Render as box-whisker chart (approved in DESIGN.md) broken by regime context.  
**What it answers:** "If I act on this signal today, what has it historically produced — and does it matter what regime we're in?"

### 9b. State Journey Timeline
**Location:** Every instrument deep dive, History tab  
**How it works:** Query `atlas_stock_states_daily` (or ETF/fund equivalent) for last 5-10 years. Render as 4 horizontal color lanes (RS/Momentum/Risk/Volume) with price chart overlay. Event markers from EVENT_LIBRARY config. Regime shading from regime history.  
**What it answers:** "How has this instrument behaved through full market cycles? When did it lead, when did it lag, what does it do in Risk-Off?"

### 9c. State Transition Probability
**Location:** CommentaryBlock data source, stock deep dive, sector deep dive  
**How it works:** Precomputed (or query-time) Markov transition matrix from state history. For any current state (or state combination), what is the historical probability of each next state, and what is the forward return distribution conditional on that transition?  
**What it answers:** "Given that this stock is in Leader state today, where does it typically go next, and what return has that transition historically produced?"  
**Powers:** The "last 5 times Leader state transitioned to X" commentary sentences.

### 9d. Breadth Waterfall
**Location:** Sectors page (sector-level), Regime page (market-level), Sector deep dive (sector-level)  
**How it works:** Time series of % stocks in Leader/Strong state, overlaid with index price, regime bands (shaded), and EVENT_LIBRARY vertical markers.  
**What it answers:** "Is breadth leading or lagging price? Is deterioration starting? What has this breadth reading historically preceded?"

### 9e. Market Structure Treemap
**Location:** Stocks page (additional view, accessible via view toggle above Band 2 — ships in Sprint 5)  
**Sprint 2 impact:** The stocks page layout should reserve a view toggle slot above the bubble chart (two-option toggle: "Bubble Chart" / "Market Map"). The Market Map slot shows a "Coming soon" placeholder in Sprints 2-4. The placeholder avoids a layout revision when Sprint 5 ships.  
**How it works:** D3 treemap. Outer = sector (size = constituent count). Inner = stocks (size = `position_size_pct`, colour = RS state). Click sector → zoom to constituents. Click stock → deep dive.  
**What it answers:** "Where is strength and weakness concentrated in the market right now? In one visual."

### 9f. Event Library
A static config file (`lib/event-library.ts`) containing named market events with start/end dates, description, and type tag:
```
{ id: 'covid-crash-2020', name: 'COVID Crash', start: '2020-02-20', end: '2020-03-23', type: 'crash' }
{ id: 'rate-hike-2022', name: '2022 Rate Hike Cycle', start: '2022-06-01', end: '2023-02-15', type: 'macro' }
{ id: 'adani-crisis-2023', name: 'Adani Crisis', start: '2023-01-24', end: '2023-03-01', type: 'event' }
{ id: 'election-2024', name: '2024 General Election', start: '2024-04-01', end: '2024-06-04', type: 'event' }
// Budget dates annually, Fed pivot dates, etc.
```
All chart annotations read from this config. Adding a new event = one line in this file.

---

## 10. Commentary Engine

Every `CommentaryBlock` is driven by a `buildCommentary(instrumentType, data)` function that:
1. Evaluates a condition tree against current data
2. Selects the appropriate template strings
3. Interpolates actual data values
4. Returns `{ lines[], insightCards[], actionSignal }`

**Stocks page commentary conditions (examples):**
- investable_count < 20 AND regime in (Cautious, Risk-Off) → "Breadth is critically narrow. Not a time to initiate new positions."
- pct_leader_strong > 30 AND improving_mom_pct > 50 → "Market breadth is healthy and expanding. Offensive positioning is supported."
- median_rs_pctile < 40 → "Most stocks are underperforming their benchmark. Be selective — only the highest RS pctile names warrant attention."
- leader_count trending down for 10+ days → "Leadership is deteriorating. Watch for further narrowing before reducing equity exposure."

**Historical context card conditions:**
- investable_count drops below threshold → queries: "last N times investable count was at this level in this regime, forward 3M return was X"
- sector breadth declining N consecutive days → "sector exhaustion signal historically precedes rotation within 2-3 weeks"

**Sector page commentary conditions:**
- Any sector crosses from Neutral to Overweight in last 5 days → "Rotation signal detected. [Sector] upgraded."
- 3+ sectors in Leading quadrant simultaneously → "Broad leadership. Offensive sector allocation supported."
- Leading sector trajectory arrows pointing bottom-left → "Leadership is rotating out. Reduce overweights, await new leaders."

The commentary is always honest about signal quality. Weak or ambiguous signals are stated as such — not inflated.

---

## 11. Interaction States

All components must implement four states. Design system convention: all skeletons use `bg-paper-rule/20 animate-pulse rounded-sm`. Error states use `text-signal-neg`. Empty states have warmth + a primary action.

| Component | LOADING | EMPTY | ERROR | NOTES |
|---|---|---|---|---|
| MetricTileRow | Skeleton block per tile (same size as tile) | `—` value with no delta | `—` value with tooltip "data unavailable" | Never show 0 for unavailable data |
| Bubble chart (Stocks/ETF/Funds/Sectors) | Shimmer overlay on chart canvas + "Loading..." text centered | "No stocks match the current filters." + Reset filters link | "Could not load data. Refresh to retry." | Empty = filter state, not data absence |
| IntelligencePanel CommentaryBlock | Skeleton 4 lines (60%/80%/70%/50% widths) with teal left border | "Insufficient data for commentary." (no card, no border) | "Commentary unavailable." | Never show partial sentences |
| StateJourneyTimeline | Skeleton 4 horizontal lanes | "No state history available for this instrument." | "Could not load history." | Min 90 days of data needed to render |
| ForwardReturnChart | "Computing historical distribution..." with subtle spinner (Band 3 expanded state) | "Insufficient historical data (N={N}) for this filter combination." if N<10 | "Historical data unavailable." | Band 3 remains collapsed if data unavailable |
| RRGChart | Skeleton dots for each sector | "Add at least 3 sectors with 20+ days of history to view the rotation graph." | "Could not render rotation graph." | NULL rs_momentum sectors excluded silently |
| Screener table | Skeleton rows (10 rows, staggered widths) | "No results match the current filter." + "Clear filters" secondary button | "Could not load data. Refresh to retry." | Skeleton rows match density of live rows |
| CommentaryInsightCard | Skeleton card | Omit card (don't render empty card) | Omit card | Cards are additive — never show empty card shell |

**Empty state for full page (no pipeline data — first load):** Show page layout skeleton (band structure visible but all content areas are shimmer placeholders). Below the header band, a warm inline notice:

```
Data is computed nightly and updates automatically.
Next run: tonight at 8:00 PM IST.
```

— `font-sans text-sm text-ink-secondary`, centered in the content area, no icon, no button. The layout skeleton ensures the user understands what will appear. Do NOT show "Run the nightly pipeline" — that is engineer language, not fund manager language.

---

## 12. Cross-Navigation Map

| From | To | Action |
|---|---|---|
| Any ticker in any screener | Instrument deep dive | Click ticker |
| Any sector name in screener | Sector page | Click sector name |
| Metric tile (e.g., LEADER/STRONG) | Screener filtered to that state | Click tile |
| RS State chip | Screener filtered to that state | Click chip |
| ENTER label in sector table | Sector deep dive → Stocks tab | Click ENTER |
| ENTER label hover | Popover showing top 3 investable stocks in that sector | Hover |
| Bubble in any chart | Instrument deep dive | Click bubble |
| Breadth numbers on regime page | Stocks screener filtered to that state | Click number |
| Sector in stock deep dive | Sector page | Click sector name |
| + button in any screener row | Portfolio builder with instrument pre-selected | Click + |
| State chip in sector transitions card | Sector decision table row | Click |

---

## 13. Data Coverage After This Build

| Instrument | Computed cols | Currently displayed | After this spec |
|---|---|---|---|
| Stocks metrics | ~43 | ~8 (~19%) | ~38 (~88%) |
| Stocks states | 11 | 8 (73%) | 11 (100%) |
| ETF metrics | ~35 | ~9 (~26%) | ~31 (~89%) |
| ETF states | 10 | 5 (50%) | 10 (100%) |
| Fund metrics | ~16 | 0 (0%) | ~15 (94%) |
| Fund states | 9 | 0 (0%) | 9 (100%) |
| Fund decisions | 18 | 0 (0%) | 16 (89%) |
| Sector metrics | 16 | ~10 (63%) | 15 (94%) |
| Sector states | 9 | 8 (89%) | 9 (100%) |
| Regime | 31 | ~25 (81%) | 28 (90%) |

**Target: >90% average coverage across all instrument types. This spec achieves it.**

---

## 14. Build Sequence

### Sprint 1 — Design System Foundation
*No page rebuilds. All additive. Existing pages still work throughout.*
- [ ] METRIC_DEFINITIONS config (all metrics, formulas, descriptions)
- [ ] EVENT_LIBRARY config
- [ ] `lib/state-segment-utils.ts` — extract `buildSegments()` from existing `StateTimeline.tsx` into shared util (used by StateJourneyTimeline and StateTimeline)
- [ ] `lib/chart-colors.ts` — canonical CHART_COLORS constant (Section 3)
- [ ] **Bubble chart color fix (Sprint 1, not Sprint 2):** update `stockColor()` in `StockBubbleChart.tsx` (stocks/) and `StockBubbleChart.tsx` (sectors/) to use `CHART_COLORS` token map. Also fix `RSPctileBar` and `PosSizeBar` inline `style` hex values in `stock-formatters.tsx`. Note: existing bubble charts use **Recharts** `ScatterChart` (not D3) — color fix is a function update, not a library migration.
- [ ] `StateValuePair` component (wraps existing `RSStateChip` / `MomentumChip` / `RiskChip` from `stock-formatters.tsx`)
- [ ] `MetricTooltip` component — wraps existing `InfoTooltip.tsx` (same Radix primitive, adds `metricKey` → `METRIC_DEFINITIONS` lookup). Do NOT re-implement the Radix layer.
- [ ] `CommentaryBlock.tsx` — rename/replace existing `Commentary.tsx` (12-line stub). Add teal border anatomy, insight cards, action signal. Migrate existing callers from `text: string` → `CommentaryOutput` type.
- [ ] `InstrumentPageShell` + `MetricTileRow` (replace copy-pasted header bands)
- [ ] `screener-utils.tsx` — extract `SortTh`, `SortIcon`, `stateRank()` duplicated in StockScreener + ETFScreener
- [ ] URL-driven period + benchmark (lift from component state to URL params)
- [ ] URL param validation: allowlist check for `?period` and `?benchmark` in all Page server components
- [ ] Bubble chart responsive sizing fix (aspect-ratio container, not hardcoded height)
- [ ] **Portfolio monitoring bug fix:** diagnose and fix equity curve + drawdown chart empty data in `/portfolios/[id]`
- [ ] **Migration 026:** Add `state_since_date DATE` column to `atlas_stock_states_daily`. Backfill from history (nightly job populates going forward). This gates Sprint 2's days_in_state column.

### Sprint 2 — Stocks + ETF Page Upgrade
- [ ] Stocks screener: add 8 new columns (ret_1w, ret_6m, vol_63, extension, drawdown, gold RS, days_in_state, gates)
- [ ] Stocks screener: column show/hide (settings popover, localStorage `atlas-column-prefs-stocks` key)
- [ ] Stocks screener: sector filter dropdown
- [ ] Stocks screener: StateValuePair on all state chips
- [ ] Stocks screener: expandable row → StateJourneyTimeline (90D compact variant). Fetches on row-expand via `/api/states-compact?symbol=X&days=90`. **Debounce:** 300ms `setTimeout` before firing; cancel on collapse. Compact variant: 4 state lanes, no price overlay, no event markers. Indexed on (instrument_id, date) — query fast.
- [ ] Stocks intelligence panel: RS state distribution, momentum distribution, investable cards
- [ ] Stocks CommentaryBlock: `buildCommentary(instrumentType, aggregates: PageAggregates)` — condition array pattern. `aggregates` comes from the **same** Band 1 page query (no second DB query). `CommentaryInput` type: `{ investable_count, pct_leader_strong, median_rs_pctile, leader_count_trend, regime_state, ... }`
- [ ] Stocks CommentaryBlock: unit tests for every condition branch in `tests/lib/commentary/stocks.test.ts`
- [ ] days_in_state: **precompute-first**. `getAllStocks()` reads `s.state_since_date` column (Migration 026). `days_in_state = CURRENT_DATE - s.state_since_date`. If `state_since_date` IS NULL (pre-backfill), show `—`. No CTE fallback in the hot query path.
- [ ] ETF screener: same column additions, StateValuePair, expandable row (same 300ms debounce), column show/hide (`atlas-column-prefs-etfs`)
- [ ] ETF CommentaryBlock (same condition array pattern)
- [ ] Metric tiles (Band 1) full implementation for both pages

### Sprint 3 — Sectors Page Upgrade
- [ ] Tab navigation (Rotation Matrix / Decision Table / State History / RRG)
- [ ] StateTransitionCard above tabs
- [ ] RRGChart component + data query
  - RRG X-axis = `bottomup_rs_3m_nifty500` (already in DB)
  - RRG Y-axis = rs_momentum = self-join on `atlas_sector_metrics_daily` at T vs T-20, compute delta. Add to sectors query as a CTE, not a separate endpoint.
- [ ] BreadthWaterfall component + event annotations
- [ ] Sector decision table: StateValuePair, new columns, ENTER hover popover
- [ ] State history: range selector, event markers
- [ ] Sector deep dive: reconciliation panel, breadth waterfall
- [ ] Sector CommentaryBlock

### Sprint 4 — Funds Page
- [ ] **Pre-flight:** Verify `mstar_id` is populated in `atlas_universe_funds` table — this is the fund deep dive route key (`/funds/[mstar_id]`). If unpopulated, use `scheme_name` slug as fallback route key.
- [ ] Funds page shell with all 4 bands
- [ ] Funds screener with all columns
- [ ] Funds bubble chart
- [ ] Fund deep dive: 3-lens view, decision history timeline
- [ ] Fund CommentaryBlock (condition array pattern, same as stocks)

### Sprint 5 — Regime Page + Historical Intelligence
- [ ] Regime: duration context, precedents card, transition signal card, event annotations
- [ ] ForwardReturnChart component + data query
- [ ] StateJourneyTimeline (5Y) in stock + ETF + fund deep dives
- [ ] MarketTreemap component
- [ ] State transition probability queries

### Sprint 6 — Polish
- [ ] Deep dive history tab range selectors (not hardcoded 6M)
- [ ] All remaining MetricTooltip integrations
- [ ] Add to Portfolio integration from screener rows
- [ ] Cross-navigation audit (every path in section 12 tested)
- [ ] Commentary engine: edge cases, ambiguous signals, honest weak-signal messaging

---

## 15. Responsive & Accessibility Conventions

**Desktop-first.** All pages target 1280px+ primary. Responsive behavior (MetricTileRow wrap at <768px, bubble chart min-width 360px) is specified per component; anything not specified defers to implementer judgment.

**Color encoding.** State chips use color + text label — text is the primary signal, color is reinforcement. Bubble charts use color for RS state; the hover tooltip always shows the text state name, satisfying WCAG minimum (color is not the only conveyor of information).

**Keyboard and focus.** Interactive elements (clickable bubbles, metric tiles, screener chips, state chips) must:
- Be reachable via Tab
- Show `:focus-visible` ring (Tailwind `focus-visible:ring-2 focus-visible:ring-teal/60`)
- Trigger the same action on Enter/Space as on click
- Bubble chart: arrow keys navigate between bubbles when chart has focus; Enter opens deep dive

**ARIA.** Screener table uses `role="grid"`. Metric tiles use `aria-label="{label}: {value}"`. State chips use `aria-label="{state} state"`. All icon-only buttons (+ button, chevron) require `aria-label`.

---

## 16. What We Are Explicitly Not Building

- Separate modes or views per investor type (PMS / MF / RA) — single unified view
- AI-generated commentary — all commentary is deterministic rule-based
- Real-time streaming data — daily computed data is the foundation
- Intraday charts or tick data
- External data integrations (Bloomberg, news feeds) in this spec
- Mobile-first redesign — desktop-first, mobile-responsive remains the priority

---

## 17. ForwardReturnDistribution — Precompute Schema

The `ForwardReturnChart` requires historical forward returns for arbitrary filter combinations.
On-demand computation against 10Y × 1000+ stocks is too slow for interactive use. This section
defines the precompute approach agreed during CEO review.

### Precompute table

```sql
CREATE TABLE atlas.atlas_forward_return_precompute (
    filter_hash        VARCHAR(16)   NOT NULL,  -- SHA-256 prefix (16 hex chars = 64 bits entropy)
    period             VARCHAR(4)    NOT NULL,  -- '1M', '3M', '6M', '1Y'
    instrument_type    VARCHAR(8)    NOT NULL,  -- 'stock', 'etf', 'fund'
    regime             VARCHAR(20),             -- NULL = all regimes, or specific regime
    sample_count       INTEGER       NOT NULL,
    median_return      NUMERIC(10,4),
    p25_return         NUMERIC(10,4),
    p75_return         NUMERIC(10,4),
    hit_rate_pct       NUMERIC(6,2),           -- % of occurrences with positive return
    last_occurrence    DATE,
    computed_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (filter_hash, period, instrument_type, regime)
);
CREATE INDEX atlas_forward_return_precompute_computed_at_idx
    ON atlas.atlas_forward_return_precompute (computed_at);  -- nightly job staleness scan
```

### Filter hash definition

The filter combination is serialized as a canonically sorted JSON string. Key ordering must be deterministic:
```python
import hashlib, json

def compute_filter_hash(filters: dict) -> str:
    # Sort keys alphabetically for canonical serialization
    canonical = json.dumps(filters, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]  # 16-char prefix = 64 bits; sufficient for ~175 precomputed combinations

# Example:
filters = {'momentum_state': 'Accelerating', 'rs_state': 'Leader', 'risk_state': 'Low'}
hash = compute_filter_hash(filters)  # always same value regardless of key insertion order
```

Minimum sample gate: if `sample_count < 10`, do not display distribution. Show "Insufficient historical data (N={sample_count}) for this filter combination" in the chart area.

### Nightly precompute job

`atlas/compute/forward_return_cache.py` — runs nightly after states pipeline:
1. Enumerate "common" filter combinations: all single-state filters (7 RS × 5 Mom × 5 Risk = 175; Risk states: Low/Normal/Elevated/High/Below Trend) + common multi-state combinations used in practice
2. For each combination: query `atlas_stock_states_daily` for all historical dates matching, join with `atlas_stock_metrics_daily` at T+21, T+63, T+126, T+252 for forward returns
3. Compute distribution stats (p25, median, p75, hit rate)
4. Upsert into `atlas_forward_return_precompute`

On-demand fallback: if `filter_hash` not found in precompute table, compute on-demand with a 5-second timeout. Return empty chart with "Computing historical distribution..." message if timeout exceeded. **Concurrency limit:** the Python fallback computation must use a DB-backed semaphore (`SELECT pg_try_advisory_lock(12345)`) — only one on-demand computation runs at a time on the t3.large. Concurrent requests wait and retry the precompute table lookup after 2 seconds (the first caller populates it). This prevents two simultaneous on-demand calls from saturating the 2 vCPUs and starving page loads.

### Sprint task

This requires Migration 026 + the nightly job. Both must ship in Sprint 5, migrate-first.

---

## 18. Open Questions for Review

1. ~~**Forward Return Distribution chart** — data query strategy.~~ **RESOLVED (CEO review):** Section 17 defines the precompute table schema, nightly job, filter hash function, and on-demand fallback. Migration 026 required in Sprint 5.

2. **Market Structure Treemap** — market cap data: stocks currently do not have market cap in the Atlas DB. **Decision: use `position_size_pct` as bubble size for v1.** This reflects the strategy's conviction weighting, which is arguably more useful than raw market cap for a relative-strength tool. Market cap can be added in a future migration if needed.

3. **Commentary engine ownership** — **Decision: hybrid.** `getCommentaryContext(instrumentType, currentState)` is called in the **Page server component** (RSC), not in an API route or client component. Its output is passed as props to `CommentaryBlock` (a client component). Historical context cards arrive fully-formed at SSR time — no client-side DB queries, no hydration mismatch. Current-data sentences are computed client-side from page props already in memory.

4. **Days in state** — **RESOLVED (eng review):** precompute-first. Migration 026 adds `state_since_date DATE` column to `atlas_stock_states_daily`. The nightly pipeline writes this column alongside the state classification. `getAllStocks()` reads `CURRENT_DATE - s.state_since_date AS days_in_state`. If `state_since_date` IS NULL (pre-backfill stocks), show `—`. No hot-path CTE. The CTE approach (LAG scan over full history) was rejected because 1000+ stocks × 2Y of daily data = ~500K rows per page load — unacceptable on a t3.large.

5. **State Journey Timeline — 5Y data volume** — 5 years × 250 trading days = 1,250 rows per instrument. For the screener's expandable row (90-day version), 90 rows. Both are fast. The 5Y version in deep dives should use a lazy-load pattern (loads when History tab is selected, not on page mount).

6. **Band 3 default state** — **RESOLVED (design review):** collapsed by default. Band 3 renders a compact `"Historical Signal ▸"` expand trigger below the screener. Clicking expands the `ForwardReturnChart`. This keeps the primary Band 2 content as the focus and avoids a loading spinner on every page load, since the distribution computation has latency.

7. **Bubble chart benchmark coloring** — **RESOLVED (design review):** bubble color **always** uses `rs_state` (₹ benchmark classification), regardless of benchmark selector position. When benchmark = Gold, only the screener columns change (RS Gold column, RS pctile bar). No special gold coloring logic in the bubble chart. Rationale: rs_state is the primary signal; gold benchmark is a comparative filter, not a reclassification.

8. **Column show/hide localStorage key** — **RESOLVED (design review):** use key `atlas-column-prefs-${pageId}` where `pageId` is `'stocks' | 'etfs' | 'funds' | 'sectors'`. Stored as `string[]` of hidden column keys. Default: all columns visible. Per-page isolation; no shared state across pages.

9. **Commentary data sharing** — **RESOLVED (eng review):** `buildCommentary(instrumentType, aggregates: PageAggregates)` receives pre-fetched Band 1 aggregates. The Page server component runs ONE aggregation query; the result populates both Band 1 MetricTileRow tiles AND `CommentaryBlock`. No second DB hit. `PageAggregates` type carries: `investable_count`, `pct_leader_strong`, `median_rs_pctile`, `leader_count_trend`, `regime_state`, and any instrument-type-specific counts.

10. **Bubble chart library clarification** — **RESOLVED (eng review):** Existing bubble charts (StockBubbleChart, ETF equivalent) use **Recharts** `ScatterChart` — not D3. Sprint 1 color fix is a function update to `stockColor()` inside those Recharts components. New components (RRGChart, BreadthWaterfall, StateJourneyTimeline, MarketTreemap) use **D3**. The spec's Chart Color Token Map applies to both via `CHART_COLORS` constant.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR | 8 scope proposals, 5 accepted, 2 deferred, 1 skipped |
| Codex Review | — | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | CLEAR (PLAN) | 8 issues found, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR (FULL) | score: 5/10 → 9/10, 8 decisions |
| DX Review | — | Developer experience | 0 | — | — |

- **VERDICT:** CEO + DESIGN + ENG CLEARED — spec ready for implementation plan (`/writing-plans`)
