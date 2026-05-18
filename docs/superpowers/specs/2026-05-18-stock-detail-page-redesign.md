# Stock Detail Page Redesign — IC-Validated Content

**Status:** DRAFT
**Date:** 2026-05-18
**Branch:** feat/atlas-strategy-lab
**Page:** `frontend/src/app/stocks/[symbol]/page.tsx`

## Why this page

The state engine + component validator are populated on EC2. The current stock detail page renders from the OLD `atlas_stock_states_daily` (whose states the morning's validator showed are mostly decorative or anti-predictive — `history_gate_pass` IR -0.89, `liquidity_gate_pass` IR -1.11). Fund managers see green-tick badges with implied long actions backed by zero or negative IC.

This rewrite consumes `atlas_stock_state_daily` (new state engine output) + `atlas_component_validation` (per-tier IC status) instead. Every badge on the page is gated by `atlas_component_validation.status` for its specific tier.

## What stays

- `frontend/src/app/stocks/[symbol]/page.tsx` shell (Suspense, params, notFound).
- `IntradayStockBadge` component (live data).
- The Javeri DESIGN.md visual system — no color/typography/spacing changes. Same warm ivory paper, teal #1D9E75, sentence-case copy, Lucide icons.
- Hit rate row (legit OOS evidence).
- Metric / state history charts (informational context, even when underlying states are decorative).

## What drops

| Drop | Reason |
|---|---|
| `history_gate_pass` green-tick badge with "favours long" implication | Validated_inverse: IR -0.89, anti-predictive |
| `liquidity_gate_pass` green-tick badge with "favours long" implication | Validated_inverse: IR -1.11 |
| `weinstein_gate_pass` green-tick | Decorative: IR +0.18 |
| `stage1_base_qualifies` (old, not the new Stage 1) | Weak sign-inverted: IR -0.34 |
| Generic "Stage 2" label from `weinstein_gate_pass` | Will be replaced by new master state |
| Volume "Accumulation" / "Distribution" binary badge | Per-tier IC validation: both decorative (IR 0.00) |
| ATR "Contracting" / "Expanding" binary badge | Per-tier IC validation: both decorative (IR 0.01) |
| RS "Average" badge with implied action | Per-tier IC validation: decorative (IR 0.02) |
| 4 equal-weighted snapshot tiles for RS / momentum / risk / volume | They're not equally predictive; visual equality misleads |

## What's added

### 1. Master State Card (top of page, replaces snapshot tiles)

```
┌─ ANANTRAJ — TDPOWERSYS ──────────────────────── ₹1,247.50 ▴ +2.3% ──┐
│                                                                       │
│ STAGE 2C MATURE                                                       │
│ Day 134 of 89 (large-cap median, p75=152)                            │
│                                                                       │
│ ⚠️ LATE — extension risk rising                                       │
│ Action: tighten trailing stop; no add-ons                            │
│                                                                       │
│ Ranked #3 of 27 Stage 2C stocks today                                │
│ within_state_rank = 0.4×freshness(0.12) + 0.3×rs(0.92)                │
│                  + 0.3×realized_vol(0.88) = 0.62                      │
└───────────────────────────────────────────────────────────────────────┘
```

Data sources:
- `atlas_stock_state_daily` (state, dwell_days, dwell_percentile, urgency_score, within_state_rank)
- `atlas_state_dwell_statistics` for cohort median + p75 reference values
- `atlas_universe_stocks` for cohort key (large_cap/mid_cap/small_cap)

Tooltip on state name: full classification rule + which thresholds fired ("close > sma_50 > sma_150 > sma_200 ✓; sma_200 slope > 0 ✓; close >= 1.00 × max(close_60d-1) ✓; rs_rank_12m × 100 ≥ 80 ✓; days_in_stage_2 > 126 (mature) ✓").

### 2. Component Validation Row (replaces decorative badges)

For each component shown, render with treatment from `atlas_component_validation.status`:

```
RS LEADER                  ⭐ validated · IR +0.62 · Q5-Q1 +5.5%
Realized vol 87th pct      ⭐ validated · IR +0.55 · Q5-Q1 +1.4%  
OBV slope: -0.0125/day     ▸ continuous (binary tier decorative; chart below)
ATR contraction: 0.85      ▸ continuous (binary tier decorative; gauge below)
Stage 2C dwell: 134/89     ⭐ validated · cohort late
```

Each "validated" badge: full green, with `?` tooltip showing the IC numbers.
Each "validated_inverse" badge: orange tone, tooltip starts with "Historically anti-predictive at 63d..."
Each "weak" badge: grey with asterisk, tooltip "Weakly predictive (IR 0.25), informational only."
Each "decorative" tier: replaced with continuous numeric display (no badge).

### 3. Within-State Peer Comparison

Sortable mini-table of the 27 Stage 2C stocks (or whatever current state cohort), ranked by within_state_rank. Shows where THIS stock sits among its peers. Tooltip on each rank column explains the underlying metric.

### 4. OBV Continuous Chart

50-day sparkline of On-Balance Volume. Zero-crossing highlighted. Tooltip:

> OBV slope -0.0125/day (50-day). Crossed below zero on 2024-10-15.
> At 63d horizon, continuous OBV slope has IR -0.43 in this universe
> (validated_inverse). For a held Stage 2 stock, falling OBV is a topping
> warning even though cross-sectionally falling-OBV stocks outperformed.

### 5. ATR Contraction Gauge

Horizontal gauge 0.0 → 2.0, with 1.0 line highlighted. Current value displayed.

> ATR contraction ratio = atr_14 / atr_14_252d_avg.
> Currently 0.85 → volatility CONTRACTING (15% below long-term average).
> Validated: IR -0.48 at 63d (Minervini VCP). Sub-1.0 = base-forming.

### 6. Dwell Timeline (252-day strip)

Visual 252-day strip showing what state this stock has been in each day, color-coded:
- Stage 1: light grey
- Stage 2A: bright green
- Stage 2B: green
- Stage 2C: amber-green
- Stage 3: amber
- Stage 4: red
- Uninvestable: black hash

Tooltip on each day shows transition rationale.

### 7. Per-Component Validation Mini-Scorecard (bottom)

Small panel showing, for THIS stock TODAY, the validation status of every component badge currently rendered. Fund manager can audit at a glance which signals are real vs informational.

## Components to create / modify

### New components

| File | Responsibility | LOC budget |
|---|---|---|
| `frontend/src/components/stocks/MasterStateCard.tsx` | Top card with state + dwell + urgency + within-state rank | ~150 |
| `frontend/src/components/stocks/ComponentValidationRow.tsx` | Single row showing a component badge with status-aware rendering | ~100 |
| `frontend/src/components/stocks/WithinStatePeers.tsx` | Sortable mini-table of cohort peers | ~120 |
| `frontend/src/components/stocks/OBVContinuousChart.tsx` | 50-day OBV sparkline with zero-cross | ~80 |
| `frontend/src/components/stocks/ATRContractionGauge.tsx` | 0-2 gauge with 1.0 line | ~80 |
| `frontend/src/components/stocks/DwellTimeline.tsx` | 252-day state strip | ~120 |
| `frontend/src/components/stocks/ComponentScorecard.tsx` | Bottom panel summarizing all component statuses | ~80 |
| `frontend/src/components/ui/ValidatedBadge.tsx` | Re-usable: takes `{status, badge_name, ic_ir, q5_q1, implied_action}` and renders per the 4-status rule | ~80 |

### Modified components

| File | Change |
|---|---|
| `frontend/src/app/stocks/[symbol]/page.tsx` | Replace `StockSnapshotTiles` with `MasterStateCard`. Add new components below in order. Remove `ConvictionBreakdownPanel` once `WithinStatePeers` + `ComponentScorecard` ship (panel becomes redundant). |
| `frontend/src/components/stocks/StockSnapshotTiles.tsx` | DEPRECATE — replaced by `MasterStateCard` |
| `frontend/src/components/stocks/StockDeepDiveBody.tsx` | Keep but slim down — remove redundant state badges that now live in MasterStateCard |

### New DB queries

| File | Function | What it returns |
|---|---|---|
| `frontend/src/lib/queries/states.ts` (NEW) | `getStockState(instrument_id)` | Latest row from `atlas_stock_state_daily` |
| `frontend/src/lib/queries/states.ts` | `getCohortBaseline(cohort_key, state)` | Row from `atlas_state_dwell_statistics` |
| `frontend/src/lib/queries/states.ts` | `getWithinStatePeers(state, date)` | Top 30 stocks in same state on same date, ordered by within_state_rank |
| `frontend/src/lib/queries/states.ts` | `getStateHistory(instrument_id, days)` | Last N rows from `atlas_stock_state_daily` for the timeline |
| `frontend/src/lib/queries/component_validation.ts` (NEW) | `getComponentValidations()` | All active rows from `atlas_component_validation` (cached) |
| `frontend/src/lib/queries/stocks.ts` (MODIFY) | Add `getStockOBVSeries(instrument_id, days)` | 50-day OBV series for sparkline |
| `frontend/src/lib/queries/stocks.ts` | Add `getStockATRContraction(instrument_id)` | Current atr_14 / atr_14_252d_avg ratio |

## Data flow (page-render path)

```
page.tsx (server component):
  await Promise.all([
    getStockBySymbol(symbol)                    -- existing
    getStockState(instrument_id)                -- NEW
    getCohortBaseline(cohort, state)            -- NEW
    getWithinStatePeers(state, today)           -- NEW
    getStateHistory(instrument_id, 252)         -- NEW (replaces getStockStateHistory pattern)
    getStockOBVSeries(instrument_id, 50)        -- NEW
    getStockATRContraction(instrument_id)       -- NEW
    getComponentValidations()                   -- NEW (cached at app start)
    getHitRateForStock(instrument_id, 20)       -- existing
  ])

  Pass to:
    <MasterStateCard {...state, cohortBaseline, peerRank} />
    <ComponentValidationRow rs={state.rs_rank_12m_tier} validation={validations.rs} />
    ... etc per component
    <WithinStatePeers peers={withinStatePeers} highlight={instrument_id} />
    <OBVContinuousChart series={obvSeries} />
    <ATRContractionGauge ratio={atrContraction} />
    <DwellTimeline history={stateHistory} />
    <ComponentScorecard stock={state} validations={validations} />
```

## DESIGN.md adherence

- Colors strictly from existing Tailwind tokens (`signal-pos`, `signal-neg`, `signal-warn`, `paper-*`, `ink-*`, `teal`).
- "validated_inverse" uses `signal-warn` (existing token) rather than a new orange.
- All caps used only for tier labels (LEADER, ELEVATED) per existing copy rule.
- Sentence case for all body / button copy.
- Lucide icons at semantic colors (already imported across components).
- Tooltips use existing tooltip component from `frontend/src/components/ui/`.

## Definition of done

1. `frontend/src/app/stocks/[symbol]/page.tsx` renders without any of the four dropped gates.
2. Every badge on the page reads `atlas_component_validation.status` for its specific tier and renders per the 4-status rule.
3. Master state card shows state + dwell + urgency + within-state-rank for ANANTRAJ on a real visit.
4. OBV continuous chart + ATR contraction gauge both render with live data.
5. Dwell timeline shows the 252-day state history correctly color-coded.
6. Mobile-responsive (DESIGN.md req).
7. All TypeScript types from queries flow correctly to component props.
8. `.design-approved.json` exists (required by PreToolUse hook for frontend code).
9. `pm2 restart atlas-frontend` deploys to atlas.jslwealth.in:3001.

## What this page does NOT do

- Not yet wired to recommendations engine (that's Phase 4 — when STATE-ENGINE-V1 promotes to leaderboard).
- Doesn't show ETF/MF/sector aggregation (separate page redesigns).
- Doesn't have an "admin override" — fund manager can see why a state is what it is via tooltip, can't override.
- Doesn't yet show drift status of underlying signals — that's the admin dashboard.

## Implementation order (subagent-driven workflow)

1. Write `frontend/src/lib/queries/states.ts` + tests.
2. Write `frontend/src/lib/queries/component_validation.ts` + tests.
3. Write reusable `ValidatedBadge` component + Storybook story (or Playwright snapshot).
4. Build `MasterStateCard` (top of page).
5. Build `ComponentValidationRow` + `ComponentScorecard`.
6. Build `OBVContinuousChart` + `ATRContractionGauge`.
7. Build `WithinStatePeers` + `DwellTimeline`.
8. Wire `page.tsx` to use all new components; remove dropped imports.
9. Run `npm run build` to verify type safety + ESLint.
10. Generate `.design-approved.json` (visual mockup via design binary OR Playwright screenshot of dev server).
11. `pm2 restart atlas-frontend` on EC2.
12. Visual smoke test on atlas.jslwealth.in/stocks/ANANTRAJ.

## Open questions for the user

1. **The four dropped gates** are currently shown across MANY pages (stocks list filters, sector drilldowns, conviction breakdown). Drop everywhere or only on this page first?
2. **Master state card should be sticky** when scrolling (so the action stays visible)? Or just at the top?
3. **Dwell timeline: 252 days or longer?** 252 = 1 trading year; 504 = 2 years (matches our validation window). 252 keeps it compact.
