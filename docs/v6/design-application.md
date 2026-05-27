# Atlas v6 — Design Application (canonical)

_Application of DESIGN.md + existing v6 design plan to the 14 priority v6 pages.
This document is the locked source of truth for the v6 frontend build._

**Parent documents** (canonical, do not modify here):
- [`DESIGN.md`](../../DESIGN.md) — Atlas Javeri Securities Design System v1.0
- [`~/.gstack/projects/atlas-os/design-plans/2026-05-24-atlas-v6-design-plan.html`](file:///Users/nimishshah/.gstack/projects/atlas-os/design-plans/2026-05-24-atlas-v6-design-plan.html) — 642-line v6 Phase 6 design plan

**Audience**: Bhavin + fund managers. Sophisticated, time-poor, decision-driven.
Not retail. Not Bloomberg-dense. Not Morningstar-dry. Sophisticated but not complex.

---

## 1. Three-layer vertical pattern (every page)

```
Layer 1 — Verdict          (1 second)
  ✓ Grade chip (AAA/AA/A/BBB/BB/B/failed-gate) OR ConvictionTape ribbon
  ✓ HEADLINE NUMBER visible alongside the shape
  ✓ Every number has an InfoTooltip (definition + significance)

Layer 2 — Thesis           (5 seconds)
  ✓ Bullet points ONLY — no paragraphs, ever
  ✓ Action verb in CAPS+bold at top: **BUY** / **HOLD** / **ACCUMULATE** /
    **TRIM** / **AVOID** / **WATCH**
  ✓ Every number bolded inside bullets
  ✓ Names actual sector / cohort / benchmark explicitly
  ✓ 3-5 bullets, 10-25 words each

Layer 3 — Substantiation   (5 minutes)
  ✓ v2 viz reused: RRG, DwellTimeline, Bubble, OBV, ATR
  ✓ MultiBenchmarkRSWaterfall (new)
  ✓ MultiTenureReturnsTable (new)
  ✓ Cell-rule drill-down with predicates in plain English
  ✓ Every technical number has a 1-sentence deterministic translation
```

## 2. Bubble chart standard (Funds + ETFs + Sectors)

```
X-axis: Risk
  - Funds:    3y σ (annualized monthly returns)
  - ETFs:     252d realized σ
  - Sectors:  sector vol_regime σ
  (Recomputes per selected tenure)

Y-axis: Return
  - Funds:    3y CAGR
  - ETFs:     252d total return
  - Sectors:  sector relative return vs selected benchmark
  (Recomputes per selected tenure + benchmark)

Size: AUM (log10-normalized, radius 4-32px)

Color: Atlas state
  ● deep green = Atlas Leader (top quartile composite)
  ● green       = Standard (middle 50%)
  ● amber       = Watch (borderline)
  ● red         = Atlas Avoid (bottom quartile)
```

**Reading**: top-right + deep-green = sweet spot. Bottom-left + red = evacuate.
Hover → ELI5 one-line. Click → detail page.

## 3. The four mandatory directives

### 3.1 Temporal toggle [1m 3m 6m 12m]

Every chart, bubble, table top-right:
```
[1m]  [3m]  [6m]  [12m]
```
Default: **6m**. Persisted per page in localStorage. When tenure changes,
chart data recomputes. Bubble axes refresh, RRG plots refresh, waterfall
refreshes, returns tables highlight selected tenure column.

### 3.2 Benchmark toggle [Nifty 50 / Nifty 500 / Gold]

On every RS-flavored view (RRG, MultiBenchmarkRSWaterfall, sector return
columns):
```
[vs Nifty 50]  [vs Nifty 500]  [vs Gold]
```
Default: **Nifty 500**. Persisted. Gold availability gracefully detected
from `public.de_index_ohlcv` — if no Gold series, hide the option.

### 3.3 Column chooser (every data table)

Settings icon top-right of each table → modal with grouped checkboxes:
- Returns (1d, 1w, 1m, 3m, 6m, 12m abs / rel)
- Risk (60d σ, 252d σ, downside vol, beta, max drawdown)
- Technicals (RSI, distance from EMA20/50/200, dist 52w high/low)
- Atlas signals (cell verdicts, ConvictionTape segments, IC, fric-adj, q)
- Benchmarks (vs Nifty 50, vs Nifty 500, vs Gold)

Default visible: 5-7 conservative columns per page. Selection persists per
page in localStorage. "Reset to default" button.

### 3.4 Short-horizon return columns

Always visible (not optional):
- **Stocks**: `1d` + `1w` returns
- **ETFs**: `1w` return
- **Funds**: `1w` NAV change
- **Sectors**: `1w sector return` + `1w breadth Δ`

## 4. Plain-English thesis registry (19 archetypes)

Build at `frontend/src/lib/eli5/thesis.ts`:

```typescript
export type ThesisBullets = {
  action: 'BUY' | 'HOLD' | 'ACCUMULATE' | 'TRIM' | 'AVOID' | 'WATCH'
  bullets: string[]  // each 10-25 words, **N%** for bolded numbers
}

generateThesis(input: {
  archetype: string
  cap_tier: 'Large' | 'Mid' | 'Small'
  tenure: '1m' | '3m' | '6m' | '12m'
  direction: 'POSITIVE' | 'NEGATIVE'
  ic: number
  fric_adj_excess: number
  sector_name?: string
  sector_rank?: number
  sector_breadth_pos?: number
  vs_cohort_pp?: number
  vs_nifty500_pp?: number
  vs_nifty50_pp?: number
  vs_gold_pp?: number
  vol_60d_vs_avg?: number
  hit_rate_pct?: number
}): ThesisBullets
```

Archetype templates (all 19, each with POSITIVE + NEGATIVE variants where applicable):

| # | Archetype | Action verb (POS) | Lead line |
|---|---|---|---|
| 1 | sector_relative_leadership | **BUY** | "Top-ranked Mid-cap in **#{sector_rank}**-of-30 strongest sector ({sector_name})" |
| 2 | quality_momentum | **HOLD** | "Sustained {cap_tier}-cap leader — **{vs_cohort_pp}pp** above cohort, volatility {vol_60d_vs_avg} below average" |
| 3 | bab_low_beta | **ACCUMULATE** | "Low-beta survivor with positive momentum — risk-adjusted alpha" |
| 4 | mean_reversion | **BUY** (dip) | "Leader pulled back **{dd_pct}%** from 52w high — buyable dip" |
| 5 | liquidity_expansion | **ACCUMULATE** | "Rising turnover (z-score **{vol_z}**) + positive RS — institutional interest" |
| 6 | inflection | **WATCH→BUY** | "Just crossed above SMA200, RS rank accelerating" |
| 7 | consolidation_breakout | **BUY** | "Low-vol base + close at new {n}-day high — breakout setup" |
| 8 | structural | **HOLD** | "10+ year leader, multi-year ascending trend, top-decile RS" |
| 9 | deep_value | **BUY** (long-term) | "Multi-year drawdown + still listed + recovery accelerating" |
| 10 | low_vol_carry | **HOLD** | "Low-volatility {cap_tier}-cap with stable returns — defensive carry" |
| 11 | breakout_with_pullback | **BUY** | "At 52w high recently + small pullback — momentum continuation" |
| 12 | idio_high_RS | **BUY** | "High idiosyncratic vol + top-quartile RS — alpha-rich" |
| 13 | obv_thrust | **ACCUMULATE** | "On-balance volume thrust + positive RS — accumulation" |
| 14 | mean_reversion_overbought | **TRIM** | "RSI {rsi} + **{dist_sma200_pct}%** above 200d SMA — stretched" |
| 15 | distribution | **TRIM** | "Volume z-score high + RS deteriorating — distribution at top" |
| 16 | volatility_spike | **WATCH** | "Vol regime expanding + RS falling — caution" |
| 17 | breakdown | **AVOID** | "Close below 252d-low band + negative 12m RS" |
| 18 | sector_drag | **AVOID** | "{sector_name} sector ranked **{sector_rank}**-of-30 weakest, breadth narrow" |
| 19 | sector_breakdown | **AVOID** | "Strong stock in weakening sector — fading leader" |

Each template includes 3-5 bullets total. Numbers bolded in markdown.

## 5. Component inventory

### v2 viz components to REUSE (no modification)

| Component | File | Where used in v6 |
|---|---|---|
| RRGChart | `components/sectors/RRGChart.tsx` | sector list page, stock detail Overview tab |
| SectorBubbleChart | `components/sectors/SectorBubbleChart.tsx` | sector list page, sector detail |
| StockBubbleChart | `components/stocks/StockBubbleChart.tsx` | sector detail constituents |
| ETFBubbleChart | `components/etfs/ETFBubbleChart.tsx` | ETF list (replaced by BubbleRiskReturnChart) |
| DwellTimeline | `components/stocks/DwellTimeline.tsx` | stock detail Overview tab |
| OBVContinuousChart | `components/stocks/OBVContinuousChart.tsx` | stock detail Technicals tab |
| ATRContractionGauge | `components/stocks/ATRContractionGauge.tsx` | stock detail Technicals tab |
| WithinStatePeers | `components/stocks/WithinStatePeers.tsx` | stock detail Overview tab |
| MasterStateCard | `components/stocks/MasterStateCard.tsx` | stock detail header (alternative to ConvictionTape header) |
| ComponentScorecard | `components/stocks/ComponentScorecard.tsx` | reusable layer breakdown |
| HitRateRow | `components/stocks/HitRateRow.tsx` | stock detail Rule tab |

### v6 components to ADD

| Component | Purpose |
|---|---|
| `TenureToggle` | Shared [1m 3m 6m 12m] segmented control with localStorage persistence |
| `BenchmarkToggle` | Shared [Nifty 50 / Nifty 500 / Gold] toggle with persistence |
| `ColumnChooser` + `useColumnPreferences` hook | Per-table column visibility manager |
| `MultiBenchmarkRSWaterfall` | Nested signed-bar waterfall (Stock → Cohort → Nifty 500 → Nifty 50 → Gold) |
| `MultiTenureReturnsTable` | 1d/1w/1m/3m/6m/12m × (abs + rel + EMA distance) matrix |
| `BubbleRiskReturnChart` | D3-based risk/return bubble, log-AUM size, Atlas-state color |
| `AuditTrailTab` | 7-section provenance chain renderer |
| `ClosedLoopDiagram` | SVG closed-loop methodology diagram, clickable nodes, cadence badges |
| `SectorBreadthPanel` | 3 EMA gauges + concentration + dispersion |
| `IndustrySnapshot` | 4-6 stat callouts for fund + ETF list pages |
| `SignatureMatrix` | Grade × category grid for fund + ETF list pages |
| `ThesisBullets` | Renders ThesisBullets type with action-verb chip + bolded numbers |
| `RankDecompositionCards` | 4-layer card breakdown for fund/ETF detail |
| `GradeChip` | AAA/AA/A/BBB/BB/B chip (verify if exists; extend) |
| `InfoTooltip` (extend existing) | Hover with definition + deterministic translation |

---

## 6. Per-page layout specs

### 6.1 `/matrix` — the soul page

**Layer 1 (header)**:
- Eyebrow: `DECISION MATRIX` (UPPERCASE, ink-3, letter-spacing 0.22em)
- H1 serif: "Today's matrix"
- Subhead: "**11 of 22** cells firing this snapshot · {snapshot_date}"

**Layer 2 (grid hero)**:
- 3 rows (tiers) × 8 columns (4 tenures × 2 directions) = 24 tiles
- Each tile (160×120):
  ```
  ┌──────────────────────────────────┐
  │ Mid · 12m · POSITIVE       [AA]  │  ← grade chip (top-right)
  │                                   │
  │ Quality Momentum                  │  ← archetype label (serif 14px)
  │                                   │
  │ IC +0.45 · fric-adj +93.6% ⓘ    │  ← mono number row, ⓘ = InfoTooltip
  │ 3/3 windows · 624 obs            │  ← stability + sample size
  └──────────────────────────────────┘
  ```
- Color gradient: deep-green (top quartile) → green → amber → red (bottom)
- Failed-gate tiles: paper-deep fill, ink-4 text, "no signal" microcopy
- Click any tile → `/matrix/[cell]`

**Layer 3 (below grid)**:
- Methodology footer link
- Cross-cell stats: total candidates tested, surviving BH-FDR
- Last refreshed timestamp from `atlas_provenance_log`

### 6.2 `/v6/today` — landing dashboard

Three-column responsive grid (above ladder):

```
┌──────────────────┬──────────────────┬──────────────────┐
│ Today's matrix   │ Current regime   │ Top conviction   │
│ (mini 24-cell)   │ + 12w strip      │ (5 stocks at     │
│ → /matrix        │ → /regime        │  Atlas Leader)    │
└──────────────────┴──────────────────┴──────────────────┘
```

Below:
- Sector ladder snapshot (top 5)
- Recent signal_calls in plain English (last 10 with timestamps)

### 6.3 `/v6/stocks` (list)

**Layer 1**:
- Eyebrow + H1 ("Stock universe · 750 instruments")
- Subhead: "{date_as_of} · {atlas_leader_count} Atlas Leaders · {avoid_count} Avoid"

**Layer 2 (filter row + bubble)**:
- Filter chips: tier (Large/Mid/Small), sector (multi-select), action verb
- Tenure toggle [1m 3m 6m 12m]
- Benchmark toggle [Nifty 50 / Nifty 500 / Gold]
- BubbleRiskReturnChart (risk-X, return-Y, log-mcap size, Atlas-state color)

**Layer 3 (ranked table)**:
Column chooser top-right. Default columns:
- Symbol (LinkedTicker)
- Name (truncated, hover full)
- Sector (LinkedSector)
- Tier badge
- ConvictionTape (4 segments)
- 1d return
- 1w return
- 6m return (highlighted = matches tenure toggle)
- Atlas action verb chip
- Thesis bullet (1 line, smaller font)

Optional columns (via chooser): IC, fric-adj, hit rate, beta, σ, dist from EMA200, RSI, RS vs each benchmark.

### 6.4 `/v6/stocks/[iid]` — stock detail (THE deepest page)

**Hero** (Layers 1+2):
```
RELIANCE INDUSTRIES                                  [AAA]
Reliance Industries Ltd. · Energy · Large-cap
─────────────────────────────────────────────────────────
[Tenure: 6m] [Benchmark: Nifty 500]

  Conviction tape:  1m ●●○○○  3m ●●●●○  6m ●●●●●  12m ●●●●●
                    (green)   (green)   (green)   (green)

  Action: **HOLD or ACCUMULATE on dips**

  • Sustained Large-cap leader, ranked **#2** in the
    Energy sector
  • Outperformed Nifty 500 by **+8.4pp** and Nifty 50
    by **+11.2pp** over the last 12 months
  • Volatility **18%** below its 60-day average — quiet
    compounding, not euphoria
  • The Atlas rule that fired (Quality Momentum) has hit
    **78%** of the time historically
  • **HOLD or ACCUMULATE** on dips up to **-6%** from spot
```

**Tabs** (default: Overview):

1. **Overview**:
   - MultiBenchmarkRSWaterfall (with tenure + benchmark toggles)
   - RRGChart (this stock + sector + 5 peers)
   - DwellTimeline (12m state transitions)
   - MultiTenureReturnsTable (1d/1w/1m/3m/6m/12m × abs+rel+EMA-distance)
   - WithinStatePeers (other stocks firing the same rule)
2. **Technicals**:
   - OBVContinuousChart
   - ATRContractionGauge
   - EMA panel (close vs EMA20/50/200, 252d, optional log scale)
   - RSI + Bollinger position (sparkbars)
3. **Rule**:
   - Cell + rule_dsl predicates in plain English
   - Per-window backtest sparklines (W1/W2/W3)
   - HitRateRow
   - Cross-rule check (which top-5 ensemble rules also fired)
4. **Audit trail** (the transparency tab):
   - 7-section provenance chain (see §7.1 below)

### 6.5 `/v6/etfs` and `/v6/funds` (list pages)

Top → bottom:

**Section 1: Industry snapshot** (4-6 callout cards)
- Total count · Atlas Leaders · Atlas Avoid
- Top category by composite (with median)
- Weakest category
- AMC leaderboard (funds only) — top 3 by Atlas Leader count

**Section 2: BubbleRiskReturnChart** (with tenure + benchmark toggles)

**Section 3: SignatureMatrix** (grade × category mini-grid)
- Rows: grades AAA / AA / A / BBB / BB / B
- Columns: categories (broad / sector / thematic / commodity for ETFs;
  Large Cap / Mid Cap / Small Cap / Flexi / Multi / ELSS / Hybrid for funds)
- Cells: count + click-to-filter

**Section 4: Ranked table** (with column chooser):
- Each row:
  - Grade chip
  - ConvictionTape (where applicable; ETFs: POS/NEUTRAL only; funds: full)
  - Name (LinkedFund/LinkedETF)
  - 2-sentence description in smaller font:
    > *"[Name] — [category], ₹[AUM]Cr AUM. Holdings tilt [top-sector] (X%); holdings-conviction [hc_score]/100. Atlas ranks **[grade]** in [category]."*
  - Composite score (mono) + Δ rank arrow
  - Layer scores as small sparkbars

### 6.6 `/v6/funds/[code]` and `/v6/etfs/[iid]` (detail pages)

**Hero** (Layers 1+2): same pattern as stock detail.

**Tabs**:

1. **Overview**:
   - RankDecompositionCards (4 layers horizontal):
     ```
     Layer 1 — Risk-adjusted return (50% weight)        Score 78/100
       ↳ 3y Sharpe 1.42 (top quartile)
       ↳ 3y Sortino 1.81
       ↳ Alpha vs Nifty 500: +3.2%
       ↳ Max drawdown: -22% (manageable)
     ```
   - MultiBenchmarkRSWaterfall
   - 3y rolling Sharpe series (sparkbar with annotations)
2. **Holdings**:
   - Top-20 holdings table (LinkedTicker per row, each holding's Atlas
     verdict + sector + weight)
   - Sector tilt bar comparison vs benchmark
   - Holdings-conviction histogram
3. **Audit trail**: 7-section provenance chain

### 6.7 `/v6/sectors` (list)

**Section 1: Industry overview** ("Today's sector map")
- Rotating in (top 3) / rotating out (top 3)
- Market breadth %
- Concentration distribution (narrow-led count vs broad-led count)

**Section 2**: RRGChart (all 30 sectors plotted in 4 quadrants)

**Section 3**: BubbleRiskReturnChart (sectors as bubbles)

**Section 4**: 30-row ranked ladder
- Rank + 5-bar strength + arrow (↗→↘)
- Sector name (LinkedSector)
- Thesis bullets (2-3 lines, smaller font, action verb)
- Right column mono stats: rank Δ, breadth %, vol regime σ

### 6.8 `/v6/sectors/[name]` (sector detail)

**Hero** (Layers 1+2): sector name, current rank, ConvictionTape, action verb

**Sections**:
1. **SectorBreadthPanel**:
   - 3 EMA gauges (% constituents above EMA20 / EMA50 / EMA200)
   - Concentration indicator: top-3 contribution to 6m return → "Narrow leadership ⚠" / "Broad participation ✓" / "Distributed"
   - Sector dispersion σ
2. **SectorBubbleChart** filtered to this sector's constituents
3. **Constituent table** (sortable, column chooser, ConvictionTape per row, thesis bullets)

### 6.9 `/regime` — market regime page

**Hero**:
- Large regime label (Risk-On / Elevated / Below-Trend / Risk-Off)
- One deterministic sentence ("Risk-On — Mid-cap quality-momentum cells fire strongest; defensive sectors out of favor")
- 12-week regime journey strip (colored timeline)

**Sections**:
- Breadth gauge + vol regime σ + cross-sector breadth (reuse v2 patterns)
- "Cells favored under this regime" list (clickable to matrix)
- Regime classifier explainer (small section)

### 6.10 `/methodology` — interactive closed loop

**Hero**: ClosedLoopDiagram (SVG, animated)
```
       ┌──────────────────────┐
       │  Methodology         │
       │  re-validation       │ ← quarterly
       │ (drift detection)    │
       └──────┬───────────────┘
              ↑
   ┌──────────┴─────────────────────┐
   │                                 │
┌──┴────┐  ┌────────┐  ┌──────────┐  │
│Raw    │→ │Daily   │→ │Cell-rule │  │
│data   │  │feature │  │sweep     │  │
└───────┘  │compute │  │(WF+FDR)  │ ← quarterly
           └───┬────┘  └────┬─────┘
               │            │
               ↓            ↓
         ┌──────────┐  ┌─────────────┐
         │Scorecard │  │ Top-1 +     │
         │(daily)   │  │ top-5 per   │
         └─────┬────┘  │ cell        │
               │       └─────┬───────┘
               └────┬────────┘
                    ↓
        ┌──────────────────────┐
        │Daily conviction tape │ ← daily IST midnight
        │evaluation            │
        └──────────┬───────────┘
                   ↓
        ┌──────────────────────────┐
        │Fund/ETF aggregation     │ ← daily
        │(holdings-weighted)      │
        └──────────┬──────────────┘
                   ↓
        ┌──────────────────────┐
        │Regime monitoring     │ ← continuous
        │(vol, breadth, σ)     │
        └──────────┬───────────┘
                   ↓ feeds back ↑
```

Each node:
- Clickable → drilldown explainer panel
- Cadence badge: daily / weekly / monthly / quarterly (color-coded)
- "Last run" timestamp from `atlas_provenance_log`

**Below the diagram**:
1. Walk-forward window viz (animated 3-OOS-window explainer)
2. Regime classifier explainer (4 states + triggers)
3. BH-FDR multiple-testing explainer (6,144 rules → 21 survive)
4. Drift detection explainer (rolling IC threshold)
5. "Today's pipeline state" — live timeline of jobs that ran today

---

## 7. New component specs (deep)

### 7.1 AuditTrailTab — 7-section provenance chain

Tab title: **"How this decision was made"**

```
Section 1 — Input data
  • Raw OHLCV: 252 days from public.de_equity_ohlcv
    (instrument_id #abc-123, dates 2025-05-22 to 2026-05-22)
  • Universe membership: in atlas.atlas_universe_stocks
    since 2018-04-12 (effective_to: null = active)
  • Sector: Energy (from atlas.atlas_sector_master)

Section 2 — Daily computation pipeline
  • Cap-tier classification: trailing 60d median (close × volume)
    = ₹2,847.2 Cr → Large (universe terciled per date)
  • 60-feature scorecard computed for snapshot 2026-05-22
    (atlas.atlas_scorecard_daily row id #xyz)
  • Source: atlas/features/scorecard_writer.py @ commit b056229
  • Run timestamp: 2026-05-25 08:47:08 IST

Section 3 — Cell-rule evaluation
  For (Large, 12m, POSITIVE), the top-5 ensemble was tested:
   ✓ LE_L12m_vz252_10 (liquidity_expansion)        FIRED  rank 1
   ✗ QM_L12m_rs12m_topd_lowvol_18                  did not fire
   ✗ BAB_L12m_beta_70_wt_90                        did not fire
   ✗ SRL2_L12m_rk95_sc3                            did not fire
   ✗ SRL2_L12m_rk95_sc5                            did not fire

Section 4 — Predicates met by this stock today
  • log_med_tv_60d = 16.92 (required ≥ 16.5 ✓)
    ↳ Daily turnover is well above the mega-liquid floor.
  • volume_zscore_252d = 1.14 (required ≥ 1.0 ✓)
    ↳ Recent volume is 1.14σ above its 12-month average — institutional accumulation.
  • rs_residual_12m in top decile (required ✓)
    ↳ Among the top 10% of stocks by 12-month relative strength.

Section 5 — Rule's track record (this rule, not this stock)
  • Information Coefficient: +0.376
    ↳ Exceptional — top 5% of all rules tested across the matrix.
  • Cross-cell BH-FDR q-value: 0.000003
    ↳ Vanishingly small chance this signal is random noise. Robust under
      multiple-testing correction across 6,144 candidate rules.
  • Per-window backtest (3 OOS windows, walk-forward):
      W1 (2022-23): +18.4% excess, 218 obs, consistent ✓
      W2 (2023-24): +8.2% excess, 156 obs, consistent ✓
      W3 (2024-25): -2.1% excess, 92 obs, less consistent
    ↳ 2 of 3 windows positive — solid base rate with one weaker recent window.
  • Hit rate (3-yr lookback): 67% positive friction-adjusted excess
  • Methodology lock ref: DEEP_SEARCH_V2_2026-05-24

Section 6 — Cross-rule consistency check (top-5 ensemble)
  • 1 of 5 ensemble rules fires on this stock today
    ↳ This is a single-archetype signal, not a multi-archetype confirmation.
      Slightly lower conviction than stocks where 3+ rules align.

Section 7 — Conviction verdict
  • Verdict: POSITIVE
  • Stored: atlas.atlas_conviction_daily on 2026-05-22 (row id #conv-456)
  • Re-evaluated nightly at 00:30 IST
  • Next regime re-validation: 2026-08-24
```

Every number with a `↳` line = deterministic translation in plain English.
Every section foldable. Default state: section 7 expanded, others collapsed.

### 7.2 MultiBenchmarkRSWaterfall

```
Relative strength · 12m view              [1m][3m][6m][●12m]   [Nifty 50][●Nifty 500][Gold]
─────────────────────────────────────────────────────────────────────────────────────────────
Reliance Industries           ████████████████████████████████░░░  +18.4%
                              Stock total return over 12 months.

  └ vs Large-cap cohort       ░░░░░░░░░░░░░░░░░░██████████████░░░  +6.8pp
                              Reliance beat the Large-cap cohort by 6.8 percentage points.

    └ vs Nifty 500            ░░░░░░░░░░░░░░░░░░░░████████████░░░  +8.4pp
                              Large-cap cohort beat Nifty 500 by +1.6pp; Reliance adds +6.8pp on top.

      └ vs Nifty 50           ░░░░░░░░░░░░░░░░░░░░░░░██████████░░  +11.2pp
                              Stock total active alpha vs Nifty 50 — full attribution chain.

      └ vs Gold               ░░░░░░░░░░░░░░░░░░██████████████░░░  +14.6pp
                              Equity outperformance — risk-on regime confirmed in real terms.

─────────────────────────────────────────────────────────────────────────────────────────────
Attribution chain summary
Nifty 500 beat Nifty 50 by **+2.8pp** → Large-cap cohort added **+1.6pp** → Reliance added
**+6.8pp** on top. Total active alpha vs Nifty 50: **+11.2pp** (+1.6pp from cohort + +6.8pp
from stock selection + +2.8pp benchmark composition).
```

Bars: forest-green (positive) or terracotta (negative), 70% fill opacity, 1px
border at full color. Width scaled to magnitude. Numbers right-aligned mono.

### 7.3 ClosedLoopDiagram (methodology page)

Animated SVG. Each node is a clickable rect with:
- Title (Source Serif 4, 14px)
- Cadence badge (small pill, color-coded: daily=green, weekly=teal, monthly=ochre, quarterly=slate)
- Last-run timestamp (mono 10px ink-3)

Arrows: hairline curves with subtle gradient flow animation (3s loop).

Click any node → side panel slides in from right with:
- What this step does (1 paragraph plain English)
- Input data tables
- Output data tables
- Code module reference
- Last 7 run timestamps
- Avg duration

### 7.4 SectorBreadthPanel

```
Banking · breadth depth                     [1m][3m][●6m][12m]
─────────────────────────────────────────────────────────────

Above EMA20:    74% of 38 constituents     [▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░]  ↗ rising
Above EMA50:    66%                         [▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░]  ↗ rising
Above EMA200:   58%                         [▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░]  → flat

Concentration: top-3 contribution to 6m return = 38%       [✓ Broad participation]
                                                            Healthy distribution of leaders.

Sector dispersion σ: 0.18  (6m)            consensus → stockpicker's    [moderate]
```

3-bar dial with percentage text + trend arrow. Concentration badge: green for
broad (<40% top-3), amber for distributed (40-65%), red for narrow (>65%).

### 7.5 BubbleRiskReturnChart

D3-based scatter with:
- Axes: risk (X), return (Y) — both recompute per selected tenure
- Bubbles: radius = log10(aum_cr+1) × 6, min 4px max 32px
- Color: signal-pos (deep green), signal-pos at 70% (green), signal-warn (amber), signal-neg (red)
- Hover: tooltip card (paper-soft, hairline border, 280×120) with name, composite, ELI5 1-liner
- Click: navigates to detail page
- Quadrant labels at corners: "Top-right: low risk + high return" etc.

---

## 8. Interaction state coverage table

| Feature | Loading | Empty | Error | Success | Partial |
|---|---|---|---|---|---|
| Matrix tile | Shimmer 24-cell grid | "No cells passed gate" + methodology link | "Cell data unavailable" + retry button | Full grade chip + number row | Failed-gate tile state (paper-deep, ink-4) |
| ConvictionTape | Shimmer ribbon | "No verdict yet" muted ribbon | Red banner + retry | 4 colored segments with dots | Mix of POSITIVE/NEUTRAL/NEGATIVE |
| Bubble chart | Skeleton grid | "No instruments match filters" + reset CTA | "Chart failed to render" + reload | All bubbles rendered | "Showing 34 of 50 — 16 lack AUM data" footer |
| MultiBenchmarkRSWaterfall | Skeleton 4 rows | "No benchmark data for this stock" | Inline error per missing benchmark | All 4-5 rows render | "Gold benchmark unavailable" — hide row |
| AuditTrailTab | Skeleton sections | n/a (always populated when on detail page) | "Audit data unavailable for this date" | All 7 sections render | "Section 5 data incomplete — partial backtest" |
| Closed-loop diagram | Skeleton SVG | n/a (always has nodes) | "Pipeline log unavailable" — diagram still renders | Live timestamps | Some nodes missing last-run timestamps |
| MultiTenureReturnsTable | Shimmer rows | "No returns data" | "Returns calc failed" | All cells filled | Cells with missing data → "—" with tooltip |
| SectorBreadthPanel | Skeleton 3 dials | n/a | Inline error | All 3 dials | "EMA200 data unavailable for new sectors" |

Every state has DESIGN.md voice — sentence case, factual, no exclamations.

---

## 9. User journey storyboard (fund-manager flow)

**Scene 1: 9:00 AM IST, Bhavin opens the dashboard**
- Lands on `/` or `/v6/today`
- Sees: regime label + 5 top conviction calls + sector ladder snapshot
- Mental state: time-poor, scanning for actionable moves
- Plan must surface: "what's NEW today" (signal_calls in last 24h), regime change if any

**Scene 2: 9:02 AM, drills into a conviction call**
- Clicks the top conviction → `/v6/stocks/[iid]`
- Sees: ConvictionTape + thesis bullets + Action verb
- Mental state: "Do I buy this?"
- Plan must surface: clear action verb + thesis bullets in 5 seconds

**Scene 3: 9:05 AM, validates the call**
- Scrolls to MultiBenchmarkRSWaterfall
- Wants to see: vs Mid-cap cohort, vs Nifty 500, vs Nifty 50
- Mental state: "Is this real alpha or just cohort drift?"
- Plan must surface: attribution chain with bolded numbers + deterministic translation

**Scene 4: 9:08 AM, checks the rule's track record**
- Clicks "Rule" tab
- Sees: rule predicates in plain English + per-window backtest + hit rate
- Mental state: "Has this signal actually worked?"
- Plan must surface: hit rate prominently + per-window stability

**Scene 5: 9:12 AM, paranoia check**
- Clicks "Audit trail" tab
- Sees: 7-section provenance chain
- Mental state: "Where does this number come from? Can I trust the data?"
- Plan must surface: complete traceability, every number with translation

**Scene 6: 9:18 AM, checks the sector context**
- Clicks the sector pill at top of stock page → `/v6/sectors/[name]`
- Sees: SectorBreadthPanel — is rotation narrow or broad?
- Mental state: "Is this stock alone or is the sector behind it?"
- Plan must surface: concentration indicator + breadth gauges

**Scene 7: 9:25 AM, fund flow check**
- Goes to `/v6/funds` to see which mutual funds hold this name
- Filters by funds holding the stock
- Mental state: "Who else likes this?"
- Plan must surface: holdings drill-down with per-holding Atlas verdicts

**Scene 8: 9:32 AM, methodology question from a colleague**
- Goes to `/methodology` to show how the system works
- Sees: ClosedLoopDiagram + live cadence timestamps
- Mental state: "I need to explain this in 60 seconds"
- Plan must surface: visual closed loop + plain English at each node

---

## 10. Voice rules (from DESIGN.md, applied to v6 copy)

- Sentence case for UI; UPPERCASE only for eyebrows + grade chips
- No emoji, anywhere
- Short, declarative, factual. 6-14 word sentences. No FOMO.
- "Color is a verb" — every color = action, status, or grade
- Banned words: explore, discover, unleash, supercharge, elevate, journey, dive in
- Preferred verbs: holdings, exposure, NAV, AUM, XIRR, drawdown, allocation, folio
- Numbers plain. The data is the drama.

---

## 11. Accessibility commitments

- Color contrast ≥ 4.5:1 for body text (DESIGN.md ink-2 on paper passes)
- Color contrast ≥ 3:1 for large text and UI components
- Every grade chip and signal pill has a screen-reader label
- Every bubble has aria-label = "{name}, composite {score}, {state}"
- Tab order follows visual hierarchy (header → primary content → sidebars)
- Skip-to-main-content link present
- Tenure / benchmark / column-chooser toggles fully keyboard-operable
- Touch targets ≥ 44×44 px on table actions
- Tables have `<caption>` and `<thead>` semantics

---

## 12. Responsive notes (desktop-first per CEO-accepted-risk O2)

- Primary viewport: 1280-1440 desktop
- Secondary: 1024 tablet (some tables collapse columns)
- Mobile (≤768px): nav becomes hamburger; tables collapse to card layout per row; tabs become accordion sections
- Polish for mobile in v1.1, not v1

---

## 13. Acceptance criteria (per page)

Every v6 page MUST:
- [ ] 3-layer pattern visible (verdict + thesis bullets + substantiation)
- [ ] InfoTooltip on every technical term (zero naked jargon)
- [ ] Numbers bolded inside thesis bullets
- [ ] CAPS+bold action verb at top of thesis
- [ ] Temporal toggle on every chart (default 6m, persisted)
- [ ] Benchmark toggle on RS views (default Nifty 500)
- [ ] Column chooser on every table with sensible defaults
- [ ] 1d + 1w columns visible by default (stocks); 1w on ETFs/funds/sectors
- [ ] v2 viz components imported where applicable
- [ ] Audit trail tab on detail pages
- [ ] Plain-English deterministic translation alongside every technical number
- [ ] DESIGN.md tokens only; no new color tokens introduced
- [ ] Indian ₹/lakh/crore formatting; +/- on percentages; green/red signed values
- [ ] Sentence case; UPPERCASE only eyebrows/grade chips; no emoji
- [ ] All 5 interaction states specified
- [ ] Fund-manager-critic sign-off

---

## 14. NOT in scope (this build)

- Real-time price ticking (snap to overnight + intraday updates only)
- Customizable dashboards / saved views (v1.1)
- Notifications / alerts (TODOS.md: deferred)
- Mobile design polish (desktop-first per CEO-accepted-risk O2)
- US / Global pages (already exist under `/us` and `/global`, not v6 scope)
- Admin pages (already exist under `/admin`, not v6 scope)
- Watchlist (deferred to v1.1)

---

## 15. What already exists (reuse, don't rebuild)

- DESIGN.md tokens + voice rules
- 642-line v6 Phase 6 design plan (regime chip states, decision badge mapping)
- 11 v2 viz components (RRG, Bubble, DwellTimeline, OBV, ATR, etc.)
- v2 InfoTooltip + MetricTooltip patterns
- v2 LinkedTicker / LinkedSector / LinkedETF / LinkedFund primitives
- v2 page header pattern (eyebrow + serif H1 + subhead)
- v2 grade-chip styling (per DESIGN.md grade-chips section)
- v2 ColumnChooser pattern (if not present, build per acceptance criteria above)
- Tailwind v4 @theme tokens (paper-*, ink-*, signal-*)
- v6 query modules at `frontend/src/lib/queries/v6/*.ts` (just shipped)

---

_Document version 1.0 · 2026-05-26 · Locked for v6 build_
