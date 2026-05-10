# Atlas OS — Intelligence Platform Design Spec
**Date:** 2026-05-10  
**Status:** Awaiting CEO review + Design review  
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
- Volume State → volume ratio: **`Expand · 1.4×`**

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

### `StateValuePair.tsx`
```
Props: state, stateKind ('rs'|'momentum'|'risk'|'volume'), value, valueColor
Renders: [StateChip] [scalar value]
Used in: all screener tables, deep dive headers
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

### `ForwardReturnChart.tsx`
```
Props: filterState (active screener filter combination), period ('1M'|'3M'|'6M'|'1Y')
Renders: violin/box-whisker chart of historical forward returns for stocks matching this filter
Data: queries state history + subsequent returns for all matching historical periods
Used in: stocks page (below screener), ETF page
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
Props: sectors[] with {name, rs_ratio, rs_momentum, momentum_state, constituent_count}
Renders: D3 scatter chart, 4 quadrants (Leading/Weakening/Improving/Lagging)
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
| VOL EXPANDING | count of volume_state=Expanding | Filters screener |
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

*Intelligence Panel (right side):*
- RS State Distribution: horizontal stacked bar + list with count and % for each state, bars clickable to filter screener
- CommentaryBlock: 4-5 sentences on current market breadth, leadership quality, regime context, historical forward return for current conditions
- Momentum Distribution: Accelerating/Improving/Flat/Deteriorating/Collapsing bars with counts
- Investable Today: top 3-4 stocks passing all 6 gates, shown as mini cards (ticker, sector, RS pctile, period return, size %)

**Band 3 — Forward Return Distribution (collapsible)**
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
| RS ₹ | rs_pctile_{period} | Bar visualization |
| RS GOLD | rs_{period}_tier_gold | Signed number, color-coded |
| EXTENSION | extension_pct | % above/below EMA 200 |
| VOL 63D | realized_vol_63 | Annualised % |
| DRAWDOWN | drawdown_ratio_252 | vs benchmark drawdown |
| DAYS IN STATE | computed: days since last rs_state change | Integer |
| GATES | 6 dots (history, liquidity, weinstein, stage1, strength, direction) | Green/grey per gate pass |
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

**Band 3 — Forward Return Distribution** (same pattern as stocks, ETF-filtered)

**Band 4 — Screener**
| Column | Data |
|---|---|
| TICKER + Name | Links to ETF deep dive |
| THEME | ThemeBadge (Broad/Sectoral/Thematic) |
| RS STATE | StateValuePair(rs_state, rs_pctile) |
| MOMENTUM | StateValuePair(momentum_state, ret_period) |
| RISK | StateValuePair(risk_state, realized_vol_63) |
| {period} RET | period-selected return |
| RS ₹ | rs_{period}_benchmark, color bar |
| RS GOLD | rs_{period}_benchmark_gold |
| RS PCTILE | rs_pctile_{period}, bar |
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

**Band 2 — Bubble Chart + Intelligence Panel**
- X: realized_vol_63
- Y: selected-period return (ret_1m / ret_3m / ret_6m / ret_12m)
- Size: drawdown_ratio_252 (inverted: larger bubble = lower drawdown = better risk profile)
- Colour: nav_state (Leader/Strong/Average/Weak/Laggard/Emerging — same color semantic as stocks)
- Filter chips: All / Equity / Hybrid / Debt / Large Cap / Mid Cap / Flexi Cap / Recommended

Intelligence panel:
- NAV State Distribution: bars per state with count + %
- Category performance: which categories are leading on RS pctile
- CommentaryBlock: fund universe quality, recommendation distribution context, historical forward return for current Recommended funds

**Band 3 — Forward Return Distribution** (filtered to Recommended funds historically)

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
| RECOMMENDATION | chip (Recommended/Hold/Reduce/Exit) + trigger flag if entry/exit triggered this week |
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
- Shows RS states (Leader/Strong/etc.) not just Overweight/Neutral decisions
- Range selector: 1M / 3M / 6M / 1Y / 3Y — not hardcoded
- Event markers: vertical lines for COVID crash, 2022 rate cycle, 2023 Adani, 2024 election, Budget dates

**Tab 4 — Relative Rotation Graph (new)**
X axis: RS ratio vs Nifty 500 (rs_3m_benchmark normalized)
Y axis: RS momentum (4-week rate of change of RS ratio)
Quadrants: Leading (top-right) / Weakening (top-left) / Improving (bottom-right) / Lagging (bottom-left)
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
Breadth numbers (e.g., "214 stocks vol expanding") link to the stocks screener filtered to that state. Makes regime page a navigation hub.

---

## 9. Historical Intelligence Layer

### 9a. Forward Return Distribution
**Location:** Stocks page Band 3, ETF page Band 3, accessible from any screener via "Historical Signal" button  
**How it works:** For the current active filter combination (e.g., rs_state=Leader, momentum_state=Accelerating, risk_state=Low, weinstein_gate_pass=true), query all historical dates when these criteria were met, then compute forward returns at 1M/3M/6M/1Y from each such date. Render as violin or box-whisker chart broken by regime context.  
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
**Location:** Stocks page (additional view, accessible via "Market Map" tab above screener)  
**How it works:** D3 treemap. Outer = sector (size = constituent count or AUM). Inner = stocks (size = market cap, colour = RS state). Click sector → zoom to constituents. Click stock → deep dive.  
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

## 11. Cross-Navigation Map

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

## 12. Data Coverage After This Build

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

## 13. Build Sequence

### Sprint 1 — Design System Foundation
*No page rebuilds. All additive. Existing pages still work throughout.*
- [ ] METRIC_DEFINITIONS config (all metrics, formulas, descriptions)
- [ ] EVENT_LIBRARY config
- [ ] `StateValuePair` component
- [ ] `MetricTooltip` component + integration into all existing column headers
- [ ] `InstrumentPageShell` + `MetricTileRow` (replace copy-pasted header bands)
- [ ] `screener-utils.tsx` + `bubble-chart-utils.ts`
- [ ] URL-driven period + benchmark (lift from component state to URL params)
- [ ] Bubble chart responsive sizing fix (aspect-ratio container)

### Sprint 2 — Stocks + ETF Page Upgrade
- [ ] Stocks screener: add 8 new columns (ret_1w, ret_6m, vol_63, extension, drawdown, gold RS, days_in_state, gates)
- [ ] Stocks screener: sector filter dropdown
- [ ] Stocks screener: StateValuePair on all state chips
- [ ] Stocks screener: expandable row → StateJourneyTimeline (90D)
- [ ] Stocks intelligence panel: RS state distribution, momentum distribution, investable cards
- [ ] Stocks CommentaryBlock: write buildCommentary() for stocks
- [ ] ETF screener: same column additions, StateValuePair, expandable row
- [ ] ETF CommentaryBlock
- [ ] Metric tiles (Band 1) full implementation for both pages

### Sprint 3 — Sectors Page Upgrade
- [ ] Tab navigation (Rotation Matrix / Decision Table / State History / RRG)
- [ ] StateTransitionCard above tabs
- [ ] RRGChart component + data query
- [ ] BreadthWaterfall component + event annotations
- [ ] Sector decision table: StateValuePair, new columns, ENTER hover popover
- [ ] State history: range selector, event markers
- [ ] Sector deep dive: reconciliation panel, breadth waterfall
- [ ] Sector CommentaryBlock

### Sprint 4 — Funds Page
- [ ] Funds page shell with all 4 bands
- [ ] Funds screener with all columns
- [ ] Funds bubble chart
- [ ] Fund deep dive: 3-lens view, decision history timeline
- [ ] Fund CommentaryBlock

### Sprint 5 — Regime Page + Historical Intelligence
- [ ] Regime: duration context, precedents card, transition signal card, event annotations
- [ ] ForwardReturnChart component + data query
- [ ] StateJourneyTimeline (5Y) in stock + ETF + fund deep dives
- [ ] MarketTreemap component
- [ ] State transition probability queries

### Sprint 6 — Polish
- [ ] Column show/hide in screeners
- [ ] Deep dive history tab range selectors (not hardcoded 6M)
- [ ] All remaining MetricTooltip integrations
- [ ] Add to Portfolio integration from screener rows
- [ ] Cross-navigation audit (every path in section 11 tested)
- [ ] Commentary engine: edge cases, ambiguous signals, honest weak-signal messaging

---

## 14. What We Are Explicitly Not Building

- Separate modes or views per investor type (PMS / MF / RA) — single unified view
- AI-generated commentary — all commentary is deterministic rule-based
- Real-time streaming data — daily computed data is the foundation
- Intraday charts or tick data
- External data integrations (Bloomberg, news feeds) in this spec
- Mobile-first redesign — desktop-first, mobile-responsive remains the priority

---

## 15. Open Questions for Review

1. **Forward Return Distribution chart** — data query strategy: precompute nightly vs query on demand. On-demand query against 10Y state history could be slow for complex filter combinations. Recommend nightly precompute for common combinations (Leader+Accel+Low / Leader+Flat+Normal / etc.) with on-demand fallback.

2. **Market Structure Treemap** — market cap data: stocks currently do not have market cap in the Atlas DB. **Decision: use `position_size_pct` as bubble size for v1.** This reflects the strategy's conviction weighting, which is arguably more useful than raw market cap for a relative-strength tool. Market cap can be added in a future migration if needed.

3. **Commentary engine ownership** — **Decision: hybrid.** Current-data sentences run client-side (data already loaded in page props). Historical context cards (transition probabilities, forward return lookups, precedent queries) run server-side as a dedicated `getCommentaryContext(instrumentType, currentState)` async function called during page server-rendering. This avoids client-side DB queries and keeps the commentary deterministic at render time.

4. **Days in state** — computed as a subquery in `getAllStocks()`. The query logic: `MIN(date) WHERE the rs_state first became current value` using LAG window function over last 90 days of state history. This adds ~50ms to the query. Acceptable given the value.

5. **State Journey Timeline — 5Y data volume** — 5 years × 250 trading days = 1,250 rows per instrument. For the screener's expandable row (90-day version), 90 rows. Both are fast. The 5Y version in deep dives should use a lazy-load pattern (loads when History tab is selected, not on page mount).
