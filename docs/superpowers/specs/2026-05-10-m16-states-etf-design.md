# M16 — Complete State Surface + ETF Intelligence

**Branch:** `feat/m16-states-etf`
**Date:** 2026-05-10
**Author:** Nimish Shah + Claude

## Problem Statement

Atlas Pillar 3 is "States, not scores." The entire platform produces a 4-tuple
`(rs_state, momentum_state, risk_state, volume_state)` for every stock and a
3-tuple `(rs_state, momentum_state, risk_state)` for every ETF. These tuples
ARE the product output — the fund manager's read on every instrument.

Current state: the stocks screener shows ONE collapsed chip (4 human labels
covering all 7 × 5 RS × momentum combinations), `risk_state` and `volume_state`
are invisible everywhere, the state heatmap is broken (wrong color keys), and
the ETF page does not exist despite `atlas_etf_states_daily` and
`atlas_etf_decisions_daily` being fully populated nightly.

Also: `StateChip` checks `rs === 'Overweight_RS'` but `atlas_stock_states_daily`
uses 7-level states (Leader/Strong/Consolidating/Emerging/Average/Weak/Laggard).
Every stock shows "↓ Weak" and `getTopPicksAcrossSectors()` returns empty.

## Scope

### P0 — Bug fixes (silent, data-corrupting)
1. Fix `StateChip` and all `rs_state === 'Overweight_RS'` checks → 7-level
2. Fix `StockHistoryTab` color maps (Overweight_RS keys → 7-level)
3. Fix `getTopPicksAcrossSectors()` SQL filter → correct RS states
4. Fix EMA ratio label: "vs Benchmark" → "Short-term Momentum (EMA10/EMA20)"

### P1 — Core product gaps
5. Stocks screener: expand to 4 sortable state columns (RS · Mom · Risk · Vol)
6. Stock detail header: 4-tuple hero (4 distinct state badges)
7. Stock detail tiles: add Risk State + Volume State tiles
8. Sectors: add `bottomup_risk_state` + `bottomup_volume_state` to query + display
9. Sectors: add constituent state distribution bar to stocks tab

### P2 — ETF page (new, full build)
10. `/etfs` — screener with 3-tuple state strips, theme classification, decisions
11. `/etfs/[ticker]` — deep-dive with gates, state history, metrics charts
12. Nav link for ETFs

### Out of scope
- Price chart (requires new `de_equity_ohlcv` query — separate milestone)
- State-dimension dropdown filters (follow-on after 4-tuple columns land)
- Breadth above 200d EMA chart (sector detail enhancement, next pass)

## Architecture

### State chip system (`stock-formatters.tsx`)

Replace single `StateChip` with:
- `RSStateChip(rs_state)` — 7-level color spectrum green→red
- `MomentumChip(momentum_state)` — 5-level green→red
- `RiskChip(risk_state)` — Low=green, Normal=slate, Elevated=amber, High=red, BelowTrend=violet
- `VolumeChip(volume_state)` — 5-level Accumulation=green → Heavy Distribution=red
- `StateTuple4({ rs, mom, risk, vol })` — horizontal 4-chip strip for headers
- `StateTuple3({ rs, mom, risk })` — for ETFs

Keep old `StateChip` but update to use 7-level logic (backward compat for
any callers not yet migrated).

### Stocks screener columns (after)
Symbol | Sector | RS State↕ | Momentum↕ | Risk↕ | Volume↕ | 3M | RS Pctile | Deploy%

### ETF data queries (`lib/queries/etfs.ts`)
- `getAllETFs()` — screener list with 3-tuple states, decisions, metrics
- `getETFByTicker(ticker)` — single ETF detail
- `getETFMetricHistory(ticker, days)` — RS pctile + EMA ratio history
- `getETFStateHistory(ticker, days)` — 3-tuple state history

### ETF pages
- `app/etfs/page.tsx` — screener shell (RSC)
- `app/etfs/[ticker]/page.tsx` — detail shell (RSC)
- `components/etfs/ETFScreener.tsx` — table with 3-tuple chips
- `components/etfs/ETFDeepDiveHeader.tsx` — ticker, name, theme badge, 3-tuple
- `components/etfs/ETFSnapshotTiles.tsx` — RS pctile, returns, Weinstein, extension %
- `components/etfs/ETFGatesPanel.tsx` — 5-gate pass/fail display
- `components/etfs/ETFOverviewTab.tsx` — RS history chart + EMA chart
- `components/etfs/ETFHistoryTab.tsx` — 3-row state heatmap + returns

### Navigation
Add "ETFs" link to existing nav between "Stocks" and "Sectors"

## Design System

Follows DESIGN.md v1.0:
- State chips: `text-[10px] font-semibold px-1.5 py-0.5 rounded-[2px]`
- All state chips use `bg-{signal}/15 text-{signal}` tinting pattern
- RS state gradient: Leader/Strong=signal-pos, Consolidating=teal, Emerging=signal-warn, Average=ink-tertiary, Weak/Laggard=signal-neg
- Risk: Low=signal-pos, Normal=ink-secondary, Elevated=signal-warn, High=signal-neg, BelowTrend=violet-600
- Volume: Accumulation/Steady-Buying=signal-pos, Neutral=ink-secondary, Distribution/Heavy=signal-neg

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 0 critical gaps, inline with existing patterns |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR | Full audit conducted, 15 gaps identified and addressed |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |
