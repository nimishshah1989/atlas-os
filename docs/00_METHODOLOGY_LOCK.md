# Atlas — Methodology Lock

**Document:** 00_METHODOLOGY_LOCK
**Status:** v0 LOCKED — pending Bhaven Shah final sign-off
**Last updated:** 2026-05-04
**Owner:** Nimish Shah (Architect)
**Sign-offs required:** Bhaven Shah (Fund Manager), Jeet Jhaveri (Principal), Bhadresh Jhaveri (Investor Emeritus), Yash Jhaveri (CEO, Beyond)

---

## Purpose of This Document

This is the canonical specification of the Atlas methodology. Every formula, every threshold, every state classification rule, every decision rule — all of it. Engineering documents (architecture, schema, milestones) reference this document as the source of truth for *what* the system does. They specify *how* it gets built; this document specifies *what* gets built.

**Once locked, this document does not change without an explicit methodology revision process.** Changes require: written change proposal, fund manager sign-off, version bump, downstream document review.

---

## 1. Foundation — The Three Questions

Atlas exists to answer three questions for every instrument, every day:

1. **Is this instrument investable right now?**
2. **When should I enter the position?**
3. **When should I exit the position?**

Every metric, every state, every aggregation, every visualization in the platform serves one of these three questions. If a feature can't be traced back to one of them, it doesn't belong in v0.

The answers are produced by **logical rules over states**, not by weighted composite scores. Every signal is fully traceable from output back to which states it operates on, which thresholds it crosses, and what capital action follows.

---

## 2. Four Pillars — Non-Negotiable

These commitments shape every downstream design decision. Architecture decisions inconsistent with any pillar require explicit override discussion.

**Pillar 1 — Price and volume are sufficient.** All analytical signals derive from OHLCV data. Fundamentals filter candidates out (universe gates), never rank them up. Keeps the framework systematic, falsifiable, free of lookahead bias.

**Pillar 2 — Stock is the atom.** Every metric is computed at stock level. Sector, ETF, and fund metrics are derived as weighted aggregations of stock-level metrics. One math, applied recursively.

**Pillar 3 — States, not scores.** Every primitive produces a categorical state, not a weighted composite. Decisions form via logical intersections of states. Interpretable, testable, free of unfalsifiable weighting debates.

**Pillar 4 — Pre-computed, never live.** Every metric, state, aggregation computed nightly and persisted. Serving layer reads only from materialized tables. No business logic at request time.

---

## 2.5 Threshold-Driven Configuration (Fifth Operating Principle)

While the four pillars define the methodology framework, a fifth principle defines the operating model: **every numeric threshold in the framework is tunable via the database, not hardcoded in code.**

This means:

- The 7 RS states, 5 momentum states, 5 risk states, etc. are **methodology** — fixed
- The numeric values that determine which state a stock falls into (e.g., "top quintile = 0.80", "high risk extension = 40%") are **tunable** — stored in `atlas_thresholds`
- Fund manager can edit any threshold via the UI; explicit "Apply & Reclassify" action recomputes 12 years of states with new values; primitive metric values (returns, EMAs, etc.) don't change because they're not interpretation, they're measurement

The 35 tunable thresholds are catalogued in `04_THRESHOLD_CATALOG.md`. Each has a default value (the methodology's default), an allowed range (preventing nonsensical settings), a methodology section reference, and a description of what changing it affects.

In this document, threshold-controlled values appear in classification tables as the default value (for readability), with the threshold key noted in italic. For example: "Top quintile = 0.80 *(threshold: `rs_quintile_top`)*". The default value is what's seeded into `atlas_thresholds` at Atlas-M1.

The dashboard exposes these values transparently — every state pill shows what triggered it, which threshold fired, and what the current threshold value is. This is the transparency contract: classification logic is explainable down to the specific numeric comparison that produced each state.

---

## 3. Universe Definition

### 3.1 Instrument Scope

| Asset Class | Count | Definition |
|---|---|---|
| Stocks | 750 | NIFTY 500 (500 names) ∪ next 250 by 60-day median traded value |
| ETFs | 100 | Top 100 by 60-day median traded value on NSE |
| Indices | 75 | Curated from NSE's 135 (broad/sectoral/factor/thematic) |
| Mutual Funds | ~400 | Equity category, Regular plan, Growth option only |

Universe is locked at v0 start using current snapshots. Point-in-time universe history is a v2 deliverable.

### 3.2 Stock Tier Classification

Stocks are classified into four tiers for within-tier ranking:

| Tier | Criterion | Approx Count |
|---|---|---|
| Large | NIFTY 100 constituents | 100 |
| Mid | NIFTY Midcap 150 constituents | 150 |
| Small | NIFTY Smallcap 250 constituents | 250 |
| Micro | Next 250 by 60-day median traded value | 250 |

### 3.3 Pre-Classification Gates

Before any state classification runs, every instrument must pass these gates. Failures result in classification suspension, not silent defaults.

*Threshold keys: `history_min_trading_days` (default 252), `liquidity_min_traded_value_inr` (default 50,000,000 = ₹5 crore).*

| Gate | Rule | Action on Fail |
|---|---|---|
| History gate | Minimum 252 trading days of OHLCV data | `INSUFFICIENT_HISTORY` — no states classified |
| Liquidity gate | Minimum ₹5 cr trailing 60-day median daily turnover (close × volume) | `ILLIQUID` — surfaced separately, not in main output |
| Adjusted-price gate | All prices must use corporate-action-adjusted close (`price_adj`) | Validation Tier 2 fails if unadjusted close used |
| Event-day gate | Budget, RBI policy, election counting, half-sessions excluded from rolling-window denominators | Tagged in `de_trading_calendar`; volume primitive skips these |

### 3.4 Historical Scope

12 years (2014-04-01 to present). Captures two full bull-bear cycles, includes 2014–2016 Modi-rally inception, the 2018 mid/small-cap correction, COVID 2020, the 2022 rate-hike cycle, and the 2023–24 small-cap boom.

---

## 4. Time Horizons

### 4.1 Classification Horizons (drive state assignment)

Three windows. These are the windows that produce the RS state classification.

| Symbol | Trading Days | Calendar Equivalent | Role |
|---|---|---|---|
| RS_1W | 5 | ~1 week | Short-term leadership |
| RS_1M | 21 | ~1 month | Recent leadership |
| RS_3M | 63 | ~3 months | Established leadership |

### 4.2 Context Horizons (computed and surfaced, not classifying)

Three additional windows computed for every stock and surfaced in the Stock Detail view as long-window context.

| Symbol | Trading Days | Calendar Equivalent | Role |
|---|---|---|---|
| RS_6M | 126 | ~6 months | Medium-term context |
| RS_12M | 252 | ~12 months | Long-term context |
| RS_12M_1M | 231 | 12M minus most recent month | Academic momentum reference (Jegadeesh-Titman) |

### 4.3 Pulse Horizons (situational awareness)

Daily and weekly snapshots displayed in UI; not used in classification logic.

| Symbol | Trading Days | Role |
|---|---|---|
| RET_1D | 1 | Today's move |
| RET_1W | 5 | Week-to-date |
| RET_1M | 21 | Month-to-date |

---

## 5. Numéraires

Every metric is computed twice: once in INR, once with all assets re-priced in gold-equivalent units.

```
price_in_gold(asset, t) = price_inr(asset, t) / gold_price_inr(t)
```

Where `gold_price_inr(t)` is the close of GOLDBEES ETF on date `t` (proxy for INR-denominated gold price).

Every downstream metric, state, and decision is computed in both numéraires. UI defaults to INR; toggle switches all values to Gold view in one click.

**Numéraire override rule:** When INR has moved more than 2σ over the trailing quarter, the platform displays a banner suggesting the user check the Gold view for FX-distortion-adjusted interpretation.

---

## 6. Benchmarks

### 6.1 User Benchmarks (Selectable in UI)

| Benchmark | Source | Code |
|---|---|---|
| Nifty 50 | NSE | NIFTY50 |
| Nifty 500 | NSE | NIFTY500 |
| MSCI World | de_global_prices | MSCIWORLD |
| S&P 500 | de_global_prices | SP500 |
| Gold | GOLDBEES NAV | GOLD |

### 6.2 Tier Benchmarks (Drive Within-Tier RS Ranking)

| Tier | Tier Benchmark |
|---|---|
| Large | Nifty 100 |
| Mid | Nifty Midcap 150 |
| Small | Nifty Smallcap 250 |
| Micro | Custom equal-weighted index of the 250 microcap names (constructed by Atlas) |

### 6.3 Sector Benchmarks (Used for Within-Sector RS at Stock Level)

NSE sectoral indices, mapped to NSE Industry Classification sectors via `de_sector_mapping`. For each of the ~20 NSE sectors that has a tradable NIFTY sectoral index (Bank, IT, FMCG, Auto, Pharma, Metal, Energy, Realty, Media, Healthcare, etc.), Atlas uses that index as the within-sector benchmark. Sectors without a dedicated NSE sectoral index (e.g., some smaller IISL sectors) fall back to Nifty 500 as the within-sector benchmark.

The mapping is locked at Atlas-M1 via the existing `de_sector_mapping` table (`jip_sector_name`, `primary_nse_index`, `secondary_nse_indices`).

Stock-level RS optionally computed against own sector for diagnostic display in the Stock Detail view. Not used in classification (within-tier ranking remains the canonical RS).

### 6.4 Default Classification Benchmark

Within-tier RS ranking uses the **tier benchmark** for that stock's tier. This is the canonical RS used for state classification. RS against other benchmarks (Nifty 50, Nifty 500, MSCI, etc.) is computed and surfaced but not used in state classification.

---

## 7. The Four Primitives — Stock Level

Every stock, every day, gets classified along four orthogonal dimensions. The four together form a state-tuple.

### 7.1 Primitive 1 — Relative Strength

**What it measures:** Excess return of stock over benchmark across multiple windows.

**Formula:**
```
return_n(asset, t) = price_adj(asset, t) / price_adj(asset, t-n) - 1

rs_n(stock, benchmark, t) = return_n(stock, t) - return_n(benchmark, t)
```

**Computed at:** windows {1W, 1M, 3M, 6M, 12M, 12M-1M} × benchmarks {tier benchmark, Nifty 500, MSCI World, S&P 500, Gold} × numéraires {INR, Gold}.

**Within-tier ranking:** For each (window, date), compute the percentile rank of each stock's RS_n against its tier benchmark within its tier. Quintile = top 20%.

**The Seven RS States:**

Classification uses the three classification windows (1W, 1M, 3M) against the tier benchmark, in INR. Quintile is within-tier on that date. *Top quintile threshold: `rs_quintile_top` (default 0.80). Bottom quintile threshold: `rs_quintile_bottom` (default 0.20).*

| State | Rule | Meaning |
|---|---|---|
| **Leader** | Top quintile in 1W AND 1M AND 3M | Structurally dominant across all horizons |
| **Strong** | Top quintile in 1M AND 3M, NOT 1W | Long-term leader, brief consolidation |
| **Consolidating** | Top quintile in 3M only | Former leader pulling back; not yet weak |
| **Emerging** | Top quintile in 1W AND 1M, NOT 3M | Newly turning; early Stage-2 candidate |
| **Average** | Middle quintiles across all classification windows | No persistent edge |
| **Weak** | Bottom quintile in any one classification window | Showing relative weakness |
| **Laggard** | Bottom quintile in 1W AND 1M AND 3M | Persistent underperformer |

**The Weinstein Absolute-Trend Gate (mandatory precondition):**

A stock can be classified as Leader, Strong, Consolidating, or Emerging **only if both conditions hold**:

```
price > 30_week_MA(price)
AND
slope(30_week_MA, last 4 weeks) >= -0.5σ  (i.e., flat or rising)
```

If a stock would qualify by relative metrics but fails the absolute-trend gate, it is classified as **Average** instead — regardless of how strong its relative metrics are.

**The Stage-1 Base Requirement (additional precondition for Emerging):**

A stock can be classified as Emerging only if:

```
stock has been classified in {Average, Weak, Laggard} for at least 8 of the last 10 weekly closes
AND
30_week_MA has been flat (slope within ±0.5σ over trailing 4 weeks)
```

This ensures Emerging fires only on stocks emerging from a real basing pattern, not on dead-cat bounces.

---

### 7.2 Primitive 2 — RS Momentum

**What it measures:** The direction and strength of relative strength changes — distinguishes "structurally strong and improving" from "strong but rolling over."

**Formula (Bhaven's EMA-ratio approach):**

```
rs_ema_ratio(stock, benchmark, t, n) = ema_n(stock_close, t) / ema_n(benchmark_close, t)

ema_10_ratio = rs_ema_ratio with n=10
ema_20_ratio = rs_ema_ratio with n=20
```

**Computed against:** tier benchmark only (single benchmark for momentum classification).

**The Five RS Momentum States:**

| State | Rule | Meaning |
|---|---|---|
| **Accelerating** | ema_10_ratio > 1 AND ema_10_ratio > ema_20_ratio AND ema_10_ratio at 20-day high | Late-stage breakout dynamics |
| **Improving** | ema_10_ratio > 1 AND ema_10_ratio > ema_20_ratio | Strength growing at normal pace |
| **Flat** | ema_10_ratio within ±2% of 1 OR \|ema_10_ratio − ema_20_ratio\| < 1% | Strength holding steady |
| **Deteriorating** | ema_10_ratio < 1 AND ema_10_ratio < ema_20_ratio | Strength fading — caution flag |
| **Collapsing** | ema_10_ratio < 1 AND ema_10_ratio < ema_20_ratio AND ema_10_ratio at 20-day low | Rapidly weakening — exit signal |

**Why EMA-ratio:** This formulation is directly chartable (Bhaven can verify any classification by plotting two EMAs on TradingView). It lags slope-σ by ~2-3 days but is more robust to single-day outliers and earnings gaps.

---

### 7.3 Primitive 3 — Relative Risk

**What it measures:** Risk relative to benchmark across two independent dimensions: positional extension (distance from long-term mean) and volatility (realized volatility ratio). Kept independent because they tell different stories.

**Sub-Measures:**

```
extension_pct(stock, t) = (close(stock, t) - ema_200(stock, t)) / ema_200(stock, t) × 100

vol_ratio_63(stock, benchmark, t) = realized_vol(stock, 63d, t) / realized_vol(benchmark, 63d, t)

realized_vol(asset, n, t) = std(daily_returns(asset, [t-n+1, t])) × sqrt(252)

drawdown_ratio_252(stock, benchmark, t) = max_drawdown(stock, 252d, t) / max_drawdown(benchmark, 252d, t)
```

**The Five Risk States:**

*Threshold keys: `risk_extension_low_max_pct` (default 25), `risk_extension_high_min_pct` (default 40), `risk_vol_ratio_low_max` (default 1.0), `risk_vol_ratio_normal_max` (default 1.25), `risk_vol_ratio_high_min` (default 1.6).*

| State | Rule | Meaning |
|---|---|---|
| **Low** | extension_pct in [0%, 25%] AND vol_ratio_63 ≤ 1.0 | Less risky than benchmark on every dimension |
| **Normal** | extension_pct in [0%, 25%] AND vol_ratio_63 in (1.0, 1.25] | Within typical range |
| **Elevated** | extension_pct in (25%, 40%] OR vol_ratio_63 in (1.25, 1.6] | More extended OR more volatile than benchmark |
| **High** | extension_pct > 40% OR vol_ratio_63 > 1.6 | Avoid entry; stretched or volatile |
| **Below Trend** | extension_pct < 0% (price below 200-EMA) | Subsumes Weinstein gate failures |

**Note:** "Below Trend" is a terminal classification — a stock in Below Trend cannot be Leader, Strong, Consolidating, or Emerging by the Weinstein gate.

---

### 7.4 Primitive 4 — Volume

**What it measures:** Conviction behind the price action. Wyckoff's effort-vs-result, expressed quantitatively.

**Sub-Measures:**

```
volume_expansion(stock, t) = avg_volume(stock, 20d, t) / avg_volume(stock, 252d, t)

effort_ratio_63(stock, t) = 
    Σ volume(stock, d) where close(d) >= open(d) for d in [t-62, t]
    ─────────────────────────────────────────────────────────
    Σ volume(stock, d) where close(d) < open(d) for d in [t-62, t]
```

Up-day defined as close ≥ open. Down-day defined as close < open.

Days flagged in `de_trading_calendar` as half-sessions or major event days are excluded from both numerator and denominator (event-day gate).

**The Five Volume States:**

*Threshold keys: `volume_accumulation_expansion_min` (default 1.2), `volume_accumulation_effort_min` (default 1.3), `volume_distribution_effort_max` (default 0.8), `volume_heavy_distribution_effort_max` (default 0.6).*

| State | Rule | Meaning |
|---|---|---|
| **Accumulation** | volume_expansion ≥ 1.2 AND effort_ratio_63 ≥ 1.3 | Institutions buying on size |
| **Steady-Buying** | volume_expansion in [1.0, 1.2) AND effort_ratio_63 ≥ 1.1 | Normal volume, consistent buying bias |
| **Neutral** | None of the other patterns apply | No clear conviction |
| **Distribution** | effort_ratio_63 ≤ 0.8 | Selling outweighing buying |
| **Heavy Distribution** | effort_ratio_63 ≤ 0.6 AND volume_expansion ≥ 1.0 | Worst combo — institutions exiting on size |

---

### 7.5 The Stock State-Tuple

For every stock, every day, the four primitives produce a 4-tuple:

```
StockState(stock, t) = (
    rs_state,
    rs_momentum_state,
    risk_state,
    volume_state
)
```

Example: `(Strong, Improving, Normal, Accumulation)` is the textbook setup. `(Strong, Deteriorating, Elevated, Distribution)` looks similar by composite score but is fundamentally different — a name to exit.

---

## 8. ETF Classification

ETFs are tradable baskets. They share most of the stock framework but with one key difference.

### 8.1 ETF Primitives

ETFs receive **three primitives** (not four). Volume is computed but **informational only** — ETF volume is dominated by AP arbitrage flow, not directional sentiment.

| Primitive | Computed for ETFs? | Used in classification? |
|---|---|---|
| Relative Strength | Yes | Yes |
| RS Momentum | Yes | Yes |
| Relative Risk | Yes | Yes |
| Volume | Yes | No (informational only) |

ETF benchmarks are determined by ETF type — broad-market ETFs vs Nifty 500, sectoral ETFs vs the underlying NIFTY sector index, thematic ETFs vs Nifty 500.

### 8.2 ETF Theme Classification

Each ETF in the universe is tagged with one of three themes:

| Theme | Definition | Decision Gating |
|---|---|---|
| **Broad** | Tracks a broad market index (Nifty 50, Nifty 500) | Market regime gate only |
| **Sectoral** | Tracks a specific sector (Bank, IT, Pharma) | Market regime AND sector state gate |
| **Thematic** | Tracks a theme/factor (Consumption, Infra, Quality) | Market regime AND dominant-sector gate |

For thematic ETFs, the "dominant sector" is the sector with highest holdings weight per the latest Morningstar disclosure.

### 8.3 ETF State-Tuple

```
ETFState(etf, t) = (
    rs_state,
    rs_momentum_state,
    risk_state
)
```

3-tuple, not 4-tuple. Volume state is stored but not part of the decision tuple.

---

## 9. Index Metrics (No State Classification)

NIFTY indices (135 in source data, 75 selected for the curated universe) are **not tradable**. They serve two roles:

1. As benchmarks (denominators in RS calculations)
2. As top-down sector readings (Nifty Bank, Nifty IT, etc.)

Indices receive metrics but no state classification:

| Metric | Computed for Indices |
|---|---|
| Returns at all 6 windows | Yes |
| RS vs Nifty 500 | Yes |
| Volatility metrics | Yes |
| RS Momentum | Yes (informational, used in sector top-down) |
| Volume primitive | No (index volume is not meaningful) |
| State classification | No |

---

## 10. Sector Aggregation — Layer 2

Sectors are derived from constituent stocks (bottom-up) AND from official NSE sector indices (top-down). Both are persisted side-by-side.

### 10.1 Sector Taxonomy

**Source:** `de_instrument.sector` column in JIP Data Core, populated by NSE Industry Classification (IISL framework). This is the canonical sector taxonomy across the entire platform — the universal sector language used by stocks, ETFs (via constituent linkage), mutual funds (via holdings), and sector indices.

**Why this source:** NSE's official classification is already in JIP Data Core for all 2,743 instruments in `de_instrument`. AMFI categorization for mutual funds maps cleanly to it. Morningstar holdings tag at this level. Using anything else creates mapping overhead at every layer.

**Sector count:** Approximately 20–22 sectors per NSE's IISL framework. The exact list is locked as a deliverable of Atlas-M1 via:

```sql
SELECT DISTINCT sector 
FROM de_instrument 
WHERE is_active = true AND sector IS NOT NULL
ORDER BY sector;
```

The output of that query, run on the date Atlas-M1 executes, becomes `atlas_sector_master` — the immutable sector taxonomy for the build. v0 does not modify or remap NSE's sectors.

**Sub-sector granularity:** The `de_instrument.industry` column provides finer-grained classification (~50–60 industries within the ~20 sectors). v0 uses sector-level only. Industry-level aggregation is a v1 enhancement for Stock Detail view drill-down.

### 10.2 Bottom-Up Aggregation

For each NSE sector (per Section 10.1, locked from `de_instrument.sector`), take all stocks tagged to that sector from the universe of 750. Compute market-cap-weighted aggregates of every stock-level metric (RS, RS momentum, risk, volume).

```
sector_metric_bottomup(sector, metric, t) = 
    Σ (stock.metric_value × stock.market_cap_weight)
    for stock in sector.constituents
```

Where `market_cap_weight` is the stock's share of total sector market cap, computed using the latest available market cap snapshot.

### 10.3 Top-Down Aggregation

Read the official Nifty sector index value directly from `de_index_prices`. Compute the same metrics (RS, momentum, risk) on that index time series.

### 10.4 Three Breadth Measures

For each sector, three breadth measures supplement aggregation:

```
participation_50(sector, t) = 
    count(stocks in sector with close > 50_day_MA, t) / total_stocks_in_sector

participation_RS(sector, t) = 
    count(stocks in sector with rs_state ∈ {Leader, Strong, Emerging}, t) / total_stocks_in_sector

leadership_concentration(sector, t) = 
    sum(market_cap_weight) for top 5 stocks by RS_3M in sector, t
```

### 10.5 The Four Sector States

*Threshold keys: `sector_overweight_participation_min_pct` (default 50), `sector_underweight_participation_max_pct` (default 30), `sector_avoid_participation_max_pct` (default 25).*

| State | Rule | Meaning |
|---|---|---|
| **Overweight** | bottom_up.rs_state ∈ {Leader, Strong} AND bottom_up.momentum ∈ {Accelerating, Improving} AND participation_RS ≥ 50% | Buy candidates here |
| **Neutral** | None of the other patterns apply (default state) | Hold but not add |
| **Underweight** | bottom_up.rs_state = Weak OR participation_RS < 30% | No new positions; trim existing |
| **Avoid** | bottom_up.rs_state = Laggard AND participation_RS < 25% | Exit positions; do not enter |

### 10.6 Divergence Flag

If `bottom_up.state` and `top_down.state` differ by more than one rank (states ordered: Overweight > Neutral > Underweight > Avoid), raise the divergence flag for the sector.

The divergence flag is presentational in v0 — surfaced in the UI and noted in decision rationale, but does not gate decisions in v0. (The v1 enhancement adds a stricter stock-level filter when sector is flagged.)

---

## 11. Market Regime — Layer 3

Market regime answers a single question: **how aggressively should capital be deployed today?** It does not pick stocks or sectors. It dials position sizing.

### 11.1 Four Input Categories

Market regime classification draws on four orthogonal categories of market internals.

**Trend (3 measures):**
- Nifty 500 close vs EMA 50 and EMA 200 (uses EMA, not DMA, for consistency with Bhaven's anchor)
- Slope of Nifty 500 EMA 50 over trailing 21 days
- Slope of Nifty 500 EMA 200 over trailing 21 days

**Moving Average Breadth — Bhaven's Existing Practice (3 measures):**
The primary anchor. Computed across the full Nifty 500 universe.
- `pct_above_ema_20` — % of Nifty 500 stocks above their EMA 20
- `pct_above_ema_50` — % of Nifty 500 stocks above their EMA 50
- `pct_above_ema_200` — % of Nifty 500 stocks above their EMA 200

**Advance/Decline Breadth (5 measures):**
Captures daily participation more sensitively than MA breadth. Foundation for institutional regime classification (Lowry, McClellan).
- Advancing stocks count (close > previous close)
- Declining stocks count (close < previous close)
- A/D ratio (advances ÷ declines)
- A/D line — cumulative net advances (advances - declines), running sum
- A/D line slope — 21-day slope of the A/D line
- McClellan Oscillator — `EMA(net_advances, 19) − EMA(net_advances, 39)`
- McClellan Summation — running sum of McClellan Oscillator

**New Highs/Lows Breadth (4 measures):**
Highs and lows context — leadership versus capitulation.
- New 52-week highs count (stocks at 252-day rolling high)
- New 52-week lows count (stocks at 252-day rolling low)
- Net new highs (new highs minus new lows)
- New highs/lows ratio (new highs ÷ max(new lows, 1))

**Strength Breadth (2 measures):**
Atlas-specific — leverages our state classification for breadth context.
- `pct_in_strong_states` — % of Nifty 500 stocks in {Leader, Strong, Emerging} states
- `pct_weinstein_pass` — % of Nifty 500 stocks passing the Weinstein absolute-trend gate

**Volatility (1 measure):**
- India VIX (level)

**Implementation note:** All technical indicators (EMAs, McClellan Oscillator, etc.) are computed using `pandas-ta` library functions to avoid implementation drift. See `01_BACKEND_ARCHITECTURE.md` Section 5.5 for the library discipline.

**Velocity (computed on read, not stored):**
The UI displays change-over-time for breadth measures (today vs 1M ago, 3M ago) using SQL window functions against the daily series. We do not pre-compute velocity columns.

### 11.2 Why These Specific Measures

EMA 20/50/200 breadth is the existing fund-management anchor — kept primary. McClellan family adds short-term breadth shifts. A/D line captures daily participation. New highs/lows identifies leadership versus capitulation. When all families agree, the regime call is robust. When they disagree, the regime is in transition — flagged as Cautious.

### 11.3 v1 Deferrals (Documented as Known Gaps)

Three breadth families considered for v0 but deferred to v1:
- **Bullish Percent Index (Dorsey)** — requires Point & Figure box construction; complex for v0
- **Zweig Breadth Thrust** — fires too rarely (a few times per decade) to drive daily decisions
- **Volume-weighted breadth (Lowry-style buying power vs selling pressure)** — requires per-stock dollar volume aggregation; meaningful but adds compute weight
- **RSI breadth (% overbought / % oversold)** — useful context but largely correlates with MA breadth

### 11.4 The Four Market Regime States

| State | Multiplier | Rule (all conditions must hold) |
|---|---|---|
| **Risk-On** | 1.0× | Nifty 500 > EMA 200 AND pct_above_ema_50 > 60% AND VIX < 18 |
| **Constructive** | 0.7× | Nifty 500 > EMA 200 AND pct_above_ema_50 in [50%, 60%] AND VIX < 22 |
| **Cautious** | 0.4× | Nifty 500 near EMA 200 (within ±2%) OR breadth deteriorating OR VIX in [22, 28] |
| **Risk-Off** | 0.0× | Nifty 500 < EMA 200 AND pct_above_ema_50 < 40% AND VIX > 28 |

*Threshold keys: `regime_risk_on_breadth_min_pct` (default 60), `regime_constructive_breadth_min_pct` (default 50), `regime_risk_off_breadth_max_pct` (default 40), `regime_risk_on_vix_max` (default 18), `regime_constructive_vix_max` (default 22), `regime_cautious_vix_max` (default 28), `regime_near_200ema_band_pct` (default 2).*

The multiplier is the deployment dial — it scales position sizes for new entries and forces full exit when 0.

### 11.5 Dislocation Override

When trailing 5-day realized volatility of Nifty 500 exceeds 4× its 252-day median, **all classifications across the entire system are suspended**. State pills display "Dislocation — classification suspended" and decision triggers do not fire. Resumption requires 5 consecutive trading days of normalized volatility.

*Threshold key: `dislocation_vol_multiplier` (default 4.0).*

---

## 12. Mutual Fund Three-Lens Framework

Mutual funds are evaluated across three independent lenses, kept independent (no compositing). Two of the three are leading indicators of NAV underperformance.

### 12.1 Lens 1 — NAV Behavior

Treat the fund's NAV as a price series. Apply the same RS, momentum, and risk math as stocks (volume primitive does not apply — funds have AUM, not trading volume).

**Category benchmarks:**

| Fund Category | Category Benchmark |
|---|---|
| Large Cap | Nifty 100 |
| Large & Midcap | Nifty 200 |
| Mid Cap | Nifty Midcap 150 |
| Small Cap | Nifty Smallcap 250 |
| Multi-Cap / Flexi | Nifty 500 |
| ELSS | Nifty 500 |
| Sectoral / Thematic | Mapped to relevant NSE sectoral index per fund's stated mandate; fallback Nifty 500 |

**The Six NAV States** (mirror stock RS taxonomy, applied to NAV time series):

| State | Rule |
|---|---|
| Leader NAV | Top quintile in 1M AND 3M AND 6M (longer windows for funds) |
| Strong NAV | Top quintile in 3M AND 6M, not 1M |
| Emerging NAV | Top quintile in 1M only |
| Average NAV | Middle quintiles |
| Weak NAV | Bottom quintile in any window |
| Laggard NAV | Bottom quintile in 1M AND 3M AND 6M |

**Note:** Fund NAV uses longer classification windows (1M / 3M / 6M) than stock RS (1W / 1M / 3M). Funds are held longer; the relevant horizons are longer.

Fund NAV uses total-return NAV (NAV + reinvested distributions), not headline NAV.

### 12.2 Lens 2 — Sector Composition

Looks at the fund's holdings (Morningstar monthly disclosure) and asks: how aligned is the manager with the regime?

```
aligned_aum_pct(fund, t) = 
    Σ fund.weight_in_sector_i 
    where sector_i.state ∈ {Overweight, Neutral} at time t

avoid_aum_pct(fund, t) = 
    Σ fund.weight_in_sector_i
    where sector_i.state = Avoid at time t
```

**The Three Composition States:**

| State | Rule |
|---|---|
| **Aligned** | aligned_aum_pct ≥ 70% AND avoid_aum_pct < 10% |
| **Mixed** | aligned_aum_pct in [50%, 70%) OR avoid_aum_pct in [10%, 20%) |
| **Misaligned** | aligned_aum_pct < 50% OR avoid_aum_pct ≥ 20% |

Lens 2 refreshes monthly, on disclosure cycle. NAV-derived metrics (Lens 1) refresh daily.

### 12.3 Lens 3 — Holdings Quality

Same monthly holdings data, but at stock level:

```
strong_aum_pct(fund, t) = 
    Σ fund.weight_in_stock_i
    where stock_i.rs_state ∈ {Leader, Strong, Emerging} at time t

weak_aum_pct(fund, t) = 
    Σ fund.weight_in_stock_i
    where stock_i.rs_state ∈ {Weak, Laggard} at time t
```

**The Three Holdings States:**

| State | Rule |
|---|---|
| **Strong-Holdings** | strong_aum_pct ≥ 60% AND weak_aum_pct < 15% |
| **Decent** | strong_aum_pct in [40%, 60%) OR weak_aum_pct in [15%, 25%) |
| **Weak-Holdings** | strong_aum_pct < 40% OR weak_aum_pct ≥ 25% |

### 12.4 The Fund State-Tuple

```
FundState(fund, t) = (
    nav_state,           # daily refresh
    composition_state,   # monthly refresh
    holdings_state       # monthly refresh
)
```

The textbook target tuple: `(Leader NAV, Aligned, Strong-Holdings)`.

The leading-indicator value: when Lens 2 or Lens 3 deteriorates *before* Lens 1, Atlas flags the fund 30–90 days before NAV catches up.

---

## 13. The Decision Engine

Decisions flow **top-down** at decision time, even though classifications flow bottom-up at compute time.

### 13.1 The Decision Layer Stack

| Layer | Question Answered | Output |
|---|---|---|
| Layer 1: Market Regime | How aggressively should capital deploy today? | Multiplier ∈ {1.0, 0.7, 0.4, 0.0} |
| Layer 2: Sector State | Which sectors are eligible for entries? | Eligible/ineligible per sector |
| Layer 3: Stock State (4-tuple) | Does this stock individually qualify? | INVESTABLE flag |
| Layer 4: Tactical Trigger | Should I enter NOW? | TRANSITION or BREAKOUT trigger |

### 13.2 Question 1 — Investability (Stock Level)

```
INVESTABLE(stock, t) =
      stock.rs_state ∈ {Leader, Strong, Emerging}        [strength gate]
    ∧ stock.rs_momentum ∈ {Accelerating, Improving}      [direction gate]
    ∧ stock.risk_state ∈ {Low, Normal}                   [risk gate]
    ∧ stock.volume_state ∈ {Accumulation, Steady-Buying} [volume gate]
    ∧ sector(stock).state ∈ {Overweight, Neutral}        [sector gate]
    ∧ market.regime ≠ Risk-Off                           [market gate]
```

A stock that fails any gate is filtered out. Logical AND, no averaging. Typical day reduces 750 stocks to 30–80 candidates.

### 13.3 Question 2 — Entry Trigger

A candidate from the investable list becomes an entry only when one of two trigger conditions fires.

**Transition Trigger:**
```
TRANSITION_TRIGGER(stock, t) =
      INVESTABLE(stock, t)
    ∧ stock.rs_momentum transitioned from {Flat, Deteriorating} to {Improving, Accelerating}
        within last 5 trading days
    ∧ stock.volume_state = Accumulation
```

**Breakout Trigger:**
```
BREAKOUT_TRIGGER(stock, t) =
      INVESTABLE(stock, t)
    ∧ stock.close > max(stock.close, last 63 days)
    ∧ stock.volume_state = Accumulation
    ∧ |stock.close - ema_20(stock, t)| / ema_20(stock, t) ≤ 5%   [proximity gate]
```

The proximity gate ensures entry on a sane retest, not chasing an extended move.

**Position sizing:**
```
position_size(stock, t) = 
    base_size 
    × market.regime_multiplier        (1.0, 0.7, 0.4, or 0)
    × risk_state_multiplier(stock, t) (Low: 1.2, Normal: 1.0, Elevated: 0.6, High: 0)
```

### 13.4 Question 3 — Exit Triggers

Six parallel exit conditions. Any one fires, position closes. The trigger that fires determines what happens to freed capital.

| Trigger | Condition | Capital Action |
|---|---|---|
| 1 | market.regime → Risk-Off | Raise to cash |
| 2 | sector(stock).state → Avoid | Rotate to other eligible sectors |
| 3 | stock.rs_state ∈ {Average, Weak, Laggard} | Rotate within sector |
| 4 | stock.rs_momentum = Collapsing | Rotate within sector |
| 5 | stock.volume_state = Heavy Distribution | Rotate within sector |
| 6 | stock.close < entry − 3 × ATR(21) | Stock-specific stop loss; rotate within sector |

**Asymmetry note:** Six exit triggers vs. two entry triggers. Capital protection is intentionally asymmetric to deployment.

### 13.5 ETF Decisions

ETFs follow stock decision logic with two adjustments:
- INVESTABLE drops the volume gate (only 5 conditions, not 6)
- Sector gate applies to sectoral and thematic ETFs only; broad ETFs are gated by market regime alone
- Exit triggers are 5 parallel (drop the volume Heavy Distribution trigger)

### 13.6 Mutual Fund Decisions

Funds are not tactical. No daily entry/exit. Recommendations refresh weekly.

```
INVESTABLE_FUND(fund, t) =
      fund.nav_state ∈ {Leader NAV, Strong NAV, Emerging NAV}    [performance]
    ∧ fund.composition_state ∈ {Aligned, Mixed}                   [sectors]
    ∧ fund.holdings_state ∈ {Strong-Holdings, Decent}             [stocks]
    ∧ market.regime ≠ Risk-Off                                    [regime]
```

**Fund Recommendation Outputs:**

| Recommendation | Condition |
|---|---|
| Recommended for new allocation | INVESTABLE_FUND = True |
| Hold | Currently held; some lenses degrading but not all |
| Reduce | Lens 2 or Lens 3 has deteriorated to worst state |
| Exit | Two or more lenses at worst state, OR market = Risk-Off |

---

## 14. v0 Scope Boundary

### 14.1 In v0

- All four primitives at stock and ETF level
- 12-year history (2014-04-01 to present)
- Bottom-up + top-down sector aggregation with divergence flag (presentational only)
- Three-lens MF framework
- Decision engine for stocks, ETFs, and funds
- Streamlit UI: regime banner, sector heatmap, RS-Risk quadrant, universe browser, instrument detail
- Validation: 3-tier per milestone DoD plus concluding cross-system check

### 14.2 Deferred to v1 (Documented as Known Gaps)

- Narrow-leadership stock override (sector-defying entry permission)
- Star-manager fund override (genuine alpha despite Lens 2/3 deterioration)
- R² of price regression as momentum quality filter (Clenow)
- VCP base-quality detection for breakout triggers (Minervini)
- Walk-forward validation framework
- Point-in-time universe reconstruction
- Adversarial regime detection
- Backtesting and model portfolio simulation

### 14.3 Explicitly Out of Scope (Not Built)

- Fundamental confluence tags (kept out per Pillar 1)
- Credit spread overlays (out of equity scope)
- Intraday signals (weekly close is decision boundary; v0 is daily)

---

## 15. Glossary of Key Terms

| Term | Definition |
|---|---|
| Numéraire | The unit asset values are denominated in (INR or Gold) |
| Tier | Stock size classification: Large/Mid/Small/Micro |
| Tier benchmark | The benchmark used for within-tier RS ranking |
| State-tuple | The categorical state across all primitives for one instrument on one day |
| Investability | Boolean: does instrument pass all gates today |
| Entry trigger | The tactical condition that turns an investable candidate into a position |
| Deployment multiplier | Market regime's scaling factor for new position sizing |
| Divergence flag | Sector-level signal that bottom-up and top-down readings disagree |
| Lens | One of three independent fund-evaluation perspectives (NAV, composition, holdings) |
| Dislocation override | System-wide classification suspension during extreme volatility |

---

## 16. Sign-Off

This methodology is locked for v0 build pending sign-off from:

- [ ] Bhaven Shah — Fund Manager (methodology approver)
- [ ] Jeet Jhaveri — Principal (strategic approver)
- [ ] Bhadresh Jhaveri — Investor Emeritus (advisory)
- [ ] Yash Jhaveri — CEO, Beyond (advisory)

**Once signed off:** This document becomes the immutable source of truth for v0 engineering. Any methodology change requires a written change proposal and re-sign-off.

---

**Document version:** 1.0 — v0 Lock
**Last updated:** 2026-05-04
**Next review:** Pre-v1 build (post-board)
