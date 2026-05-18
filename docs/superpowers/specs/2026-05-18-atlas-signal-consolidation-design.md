# Atlas Signal Consolidation — Single Source of Truth Design

**Date:** 2026-05-18
**Branch:** feat/atlas-strategy-lab
**Anchors:** [State Engine spec](2026-05-18-atlas-state-engine-design.md), [Stock Detail Redesign spec](2026-05-18-stock-detail-page-redesign.md), [Phase 2 IC audit](../../audits/state-engine-phase2-ic-2026-05.md)

## Problem

Atlas has two parallel signal systems writing to the same pages:

1. **Legacy** — `atlas_stock_states_daily` with categorical states (`rs_state`, `momentum_state`, `risk_state`, `volume_state`) and 7 boolean gates (history/liquidity/weinstein/strength/direction/risk/volume). Most of these are decorative or anti-predictive by IC.
2. **IC-validated state engine** — `atlas_stock_state_daily` with one Weinstein 4-stage composite plus per-component validation in `atlas_component_validation`.

A page like `/stocks/NESTLEIND` shows both: "Investable" (legacy) AND "Stage 4 Decline" (new engine). The fund manager cannot tell which is truth. Same contradiction echoes across sector, fund, ETF, country pages because aggregates compute top-down from the legacy table.

This spec defines the single-source-of-truth consolidation.

## Principle — five tiers

Every signal on the platform must serve one of:

1. **Tier 1: Classifier inputs** — define the state (IR > 0.4 cross-sectional)
2. **Tier 2: Within-state rankers** — order peers inside a state (per-tier IC validated within state cohort)
3. **Tier 3: Transition triggers** — cause re-classification (directional IC at short horizons)
4. **Tier 4: Continuous context** — render-only display (continuous |IR| > 0.3, tier collapse decorative)
5. **Tier 5: Cohort selectors** — bucket the universe before classification (no IC requirement; structural)

Anything that doesn't fit one of these five → cut.

## Calls (decided, not open)

1. **SP04 Conviction** — DEPRECATE. `atlas_stock_conviction_daily` becomes read-only legacy. `ConvictionCell` renamed to `WithinStateRankCell`, reads `within_state_rank` from `atlas_stock_state_daily`. SP04 rolling-IC + admin-proposal infrastructure (Stage 4a/4c) repurposes: it now monitors the *state engine's* per-classifier IC drift instead of conviction-composite drift.

2. **SP09 CTS Timing** — CUT as standalone classifier. `atlas_cts_*` tables become read-only legacy; `CTSDeepDiveCard`, `CTSGradeSummaryCards`, `CTSIndexTimingPanel`, `CTSSectorPanel`, `CTSSignalBadge`, `CTSTimingCell` deleted. The continuous PPC/NPC/Contraction values are evaluated via the existing IC engine (`compute_ic_over_window`). Each that crosses |IR| > 0.4 at a relevant horizon folds into `atlas/intelligence/states/classifier.py` as a Tier 3 transition trigger; the rest deleted.

3. **All entry/exit triggers** (`transition_trigger`, `breakout_trigger`, 6 `exit_*` columns in `atlas_stock_states_daily`) → CUT. The state engine itself defines transitions (stage_2 → stage_3 is the exit signal).

4. **All 7 legacy gate booleans** (`history_gate_pass`, `liquidity_gate_pass`, `weinstein_gate_pass`, `strength_gate`, `direction_gate`, `risk_gate`, `volume_gate`) → CUT. None survive IC; previously proven in [Phase C validator run](../../audits/state-engine-phase2-ic-2026-05.md).

5. **Legacy categorical state columns** (`rs_state`, `momentum_state`, `risk_state`, `volume_state`) → DEPRECATE. `atlas_stock_states_daily` stops being written by the nightly DAG. All UI consumers move to the bridge view or directly to `atlas_stock_state_daily`.

6. **Cross-page chips** — CUT: `StateTuple4`, `StateJourneyCompact`, `SignalCell`, `MomentumChip`, `VolumeChip`. REPLACE with `ValidatedBadge`: `RSStateChip`, `RiskChip`. KEEP: `SectorBadge`, `IntradayStockBadge`.

7. **Aggregations** — sector / fund / ETF / country state become bottom-up computations from `atlas_stock_state_daily`. Exception: fund `nav_state` is a genuinely fund-internal NAV-vs-category computation and retained, but gets its own IC validation against forward fund returns; if it fails, also cut.

## Bridge view — minimum-viable consistency layer

```sql
CREATE VIEW atlas.atlas_stock_signal_unified AS
SELECT
  s.instrument_id,
  s.date,
  -- Truth from the new engine
  s.state                                                  AS engine_state,
  s.dwell_days,
  s.urgency_score,
  s.within_state_rank,
  s.rs_rank_12m,
  -- Derived legacy column names (every old consumer keeps working)
  NOT (s.state IN ('uninvestable','stage_4'))              AS is_investable,
  CASE
    WHEN s.rs_rank_12m >= 0.90 THEN 'Leader'
    WHEN s.rs_rank_12m >= 0.70 THEN 'Strong'
    WHEN s.rs_rank_12m >= 0.30 THEN 'Average'
    WHEN s.rs_rank_12m >= 0.10 THEN 'Weak'
    ELSE 'Laggard'
  END                                                       AS rs_state,
  CASE
    WHEN s.state IN ('stage_2a','stage_2b') THEN 'Accelerating'
    WHEN s.state = 'stage_2c'               THEN 'Improving'
    WHEN s.state = 'stage_3'                THEN 'Deteriorating'
    WHEN s.state = 'stage_4'                THEN 'Collapsing'
    WHEN s.state = 'stage_1'                THEN 'Flat'
    ELSE 'Flat'
  END                                                       AS momentum_state,
  s.state IN ('stage_1','stage_2a','stage_2b','stage_2c')  AS weinstein_gate_pass,
  -- Continuous Tier 4 surfaces
  s.close_vs_sma_50, s.close_vs_sma_150, s.close_vs_sma_200,
  s.sma_200_slope, s.volume_ratio_50d, s.distribution_days
FROM atlas.atlas_stock_state_daily s
WHERE s.classifier_version = 'v2.0-validated';
```

Sector view (`atlas_sector_signal_unified`), fund view (`atlas_fund_signal_unified`), ETF view (`atlas_etf_signal_unified`) aggregate this same view bottom-up.

## Tables / scripts being deprecated

| Object | Status | Notes |
|---|---|---|
| `atlas_stock_states_daily` | Read-only legacy | Nightly write disabled; views read from `atlas_stock_state_daily` |
| `atlas_stock_conviction_daily` | Read-only legacy | Replaced by `within_state_rank` |
| `atlas_cts_stock_signals`, `atlas_cts_index_timing` | Read-only legacy | Stage column subsumed by atlas state |
| `atlas_sector_states_daily` | Replaced | New view aggregates bottom-up |
| `atlas_fund_states_daily` | Replaced | Same |
| `atlas_etf_states_daily` | Replaced | Same |
| `compute_stocks.py` legacy nightly | Disabled | Replaced by `atlas-lab states classify --persist` |
| `compute_sectors.py` legacy | Replaced | New bottom-up aggregator |
| `compute_etfs.py` (state portion) | Replaced | Same |
| `compute_funds.py` (state portion) | Replaced | Same, except nav_state retained as separate compute |
| All `*_gate_pass` writers in compute pipelines | Removed | Gates cut |

Tables stay around as read-only legacy for two weeks (rollback window), then dropped via migration.

## Files needing rewire — frontend

### Cut entirely (no replacement)
- `frontend/src/components/ui/StateTuple4.tsx`
- `frontend/src/components/ui/StateJourneyCompact.tsx`
- `frontend/src/components/stocks/SignalCell.tsx`
- `frontend/src/components/stocks/MomentumChip.tsx` (if exists; else inline)
- `frontend/src/components/stocks/VolumeChip.tsx` (if exists; else inline)
- `frontend/src/components/stocks/CTSDeepDiveCard.tsx`
- `frontend/src/components/stocks/CTSGradeSummaryCards.tsx`
- `frontend/src/components/stocks/CTSIndexTimingPanel.tsx`
- `frontend/src/components/stocks/CTSSectorPanel.tsx`
- `frontend/src/components/stocks/CTSSignalBadge.tsx`
- `frontend/src/components/stocks/CTSTimingCell.tsx`
- `frontend/src/components/stocks/StockHistoryTab.tsx` (4 separate state heatmaps — subsumed by DwellTimeline)
- All Exit Risk Flag rendering in `StockDeepDiveBody.tsx`

### Replace with state-engine equivalents
- `frontend/src/components/stocks/RSStateChip.tsx` → `ValidatedBadge` derived from `rs_rank_12m` tier
- `frontend/src/components/stocks/RiskChip.tsx` → `ValidatedBadge` derived from `realized_vol_63` tier
- `frontend/src/components/stocks/ConvictionCell.tsx` → `WithinStateRankCell` reading `within_state_rank`
- `frontend/src/components/stocks/StockScreener.tsx` — gate columns deleted, state columns replaced
- `frontend/src/components/stocks/StockOverviewTab.tsx` — Weinstein/Momentum panels removed
- `frontend/src/components/sectors/SectorOverviewTab.tsx`, `SectorStocksTab.tsx`, etc. — read bottom-up sector view
- `frontend/src/components/funds/FundPageClient.tsx`, `FundScreener.tsx`, `FundHoldingsTab.tsx` — read derived recommendation
- `frontend/src/components/etfs/ETFScreener.tsx`, `ETFBubbleChart.tsx` — same pattern
- All affected `frontend/src/lib/queries/*.ts` — point at new views

### Untouched
- `MasterStateCard`, `ComponentValidationRow`, `ComponentScorecard`, `OBVContinuousChart`, `ATRContractionGauge`, `WithinStatePeers`, `DwellTimeline`, `ValidatedBadge` (just shipped)
- `SectorBadge`, `IntradayStockBadge` (genuinely Tier 5 / non-state)
- `RegimeStrip`, intraday components for live prices

## Files needing rewire — backend

### New
- `atlas/intelligence/aggregations/sector.py` — bottom-up sector state aggregator
- `atlas/intelligence/aggregations/fund.py` — bottom-up fund composition / holdings aggregator
- `atlas/intelligence/aggregations/etf.py` — bottom-up ETF state aggregator
- `atlas/intelligence/states/ic_harness.py` — one-shot IC runner for legacy signals (CTS, nav_state, entry/exit) to validate cut-or-keep
- 4 SQL views (migration): `atlas_stock_signal_unified`, `atlas_sector_signal_unified`, `atlas_fund_signal_unified`, `atlas_etf_signal_unified`

### Modified
- `atlas/compute/stocks.py` — legacy nightly disabled (a one-liner)
- `atlas/compute/sectors.py` — replaced by bottom-up aggregator call
- `atlas/compute/etfs.py` — same
- `atlas/compute/funds.py` — composition / holdings paths replaced; nav_state retained
- `atlas/trading/cli_states.py` — `atlas-lab states classify --persist` becomes the nightly entry point
- Cron / systemd nightly DAG — disable legacy compute, enable state engine

### Removed (after rollback window expires)
- `atlas/compute/stocks.py` legacy
- All gate-computation helpers
- `atlas/agents/cts_*` (if any)
- `atlas/intelligence/conviction/*` (SP04 composite; rolling-IC infra retained but retargeted)

## Coexistence rules

- **V5-RP-TREND stays rank 1 throughout.** `atlas-lab goal-post --rank 1` must return `met:true` after every phase. The state engine work is separate from the strategy runner.
- **Burn-in for the state engine continues in parallel** — Phase 6 of the state engine plan. Consolidation work in this spec is UI / table layer, not classifier changes.
- **`atlas/trading/lab.py` (V5 baseline) is not modified by this work.**

## Sequencing

1. **Bridge views** (1 day CC). Migration creates 4 views. No table writes change. Pages keep working — but every page now reads consistent data.
2. **IC harness on legacy signals** (1 day CC). Run `atlas-lab states validate-legacy --signals cts_ppc,cts_npc,cts_contraction,nav_state,transition_trigger,breakout_trigger,exit_*`. Capture which survive into `atlas_component_validation` with `component_kind='legacy_candidate'`.
3. **Cut the dead chips** (1 day CC). Delete files, fix imports, build clean. No DB changes.
4. **Stock list + screener rewire** (2 days CC). Replace columns, delete gate row, point at new view.
5. **Sector aggregation rewrite** (2 days CC). New bottom-up `atlas_sector_signal_unified` writer + view + page rewire.
6. **Fund aggregation rewrite** (2 days CC). Same, with nav_state preserved.
7. **ETF aggregation rewrite** (1 day CC). Same.
8. **Global / portfolios / strategies pages** (1 day CC). Inherit shared cells; verify.
9. **Drop legacy tables** (1 day CC, after 2-week burn-in). Migration to drop `atlas_stock_states_daily`, `atlas_stock_conviction_daily`, `atlas_cts_*`, `atlas_sector_states_daily`, `atlas_fund_states_daily`, `atlas_etf_states_daily`.

Total: ~12 days CC. Step 1 alone (~1 day) resolves the user-visible contradiction.

## Definition of done

1. Every page on atlas.jslwealth.in displays signals derived from a single source (`atlas_stock_state_daily` or its aggregates).
2. No page shows a legacy categorical state badge whose value comes from `atlas_stock_states_daily` directly. Every signal traces back to the new engine via the bridge view or its aggregations.
3. `atlas-lab goal-post --rank 1` returns `met:true` at every checkpoint.
4. All deprecated tables are read-only or dropped; nightly DAG no longer writes to them.
5. Test coverage: every aggregator has a unit test; every bridge view has a smoke test asserting row counts and shape.
6. NESTLEIND on `/stocks/NESTLEIND` shows one state — no contradictions.

## Open questions for the user

None. All calls made.
