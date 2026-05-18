# Phase 7: Query Layer Rewire — Approach

**Date:** 2026-05-19  
**Branch:** feat/atlas-consolidation  
**Plan:** Phase 7 (Tasks 7.1–7.5) of atlas-signal-consolidation.md

## Scope

13 files in `frontend/src/lib/queries/` have legacy table references. This phase rewires them to the unified views without touching JSX.

## File-by-file plan

### Task 7.1 — `stocks.ts`
- Legacy: `atlas_stock_states_daily` (s), `atlas_stock_decisions_daily` (d), `atlas_cts_signals_daily` (cts)
- Target: `atlas_stock_signal_unified` (su) — provides engine_state, rs_state, momentum_state, is_investable, within_state_rank, rs_rank_12m, weinstein_gate_pass, dwell_days, close_vs_sma_50/150/200, sma_200_slope, volume_ratio_50d, distribution_days
- Gate columns (history_gate_pass, liquidity_gate_pass, strength_gate, direction_gate, risk_gate, volume_gate, sector_gate, market_gate, transition_trigger, breakout_trigger, exit_*): replace with `TRUE AS <col>` per spec
- CTS columns (stage, is_ppc, is_npc, is_contraction, trigger_level, ppc_strength, signal_date, cts_conviction_score, cts_action_confidence): replace with NULL literals
- `days_in_state`: use `su.dwell_days` directly (integer, no CURRENT_DATE arithmetic)
- `getStockStateHistory()`: point at `atlas_stock_signal_unified` for rs_state + momentum_state; risk_state and volume_state return NULL (not in view — these are deprecated gate columns, return NULL::text)
- 3 SQL statements affected

### Task 7.2 — `sectors.ts`
- Legacy: `atlas_sector_states_daily` (s) in `getSectorsWithMomentum`, `getSectorStateHistory`, `getSectorMetricHistory`, `getBreadthWaterfallData`, `getDaysInStateForAllSectors`
- `atlas_cts_sector_pivot_daily` in `getSectorCTSPivot`
- Target: `atlas_sector_signal_unified` for sector_state
- `getSectorCTSPivot()`: return empty array (CTS cut; add comment)
- `getBreadthWaterfallData()`: rs_state available in `atlas_stock_signal_unified`; rewrite to use unified view
- `getDaysInStateForAllSectors()`: use `atlas_sector_signal_unified`
- 5 SQL statements affected

### Task 7.3 — `sector-deep-dive.ts`
- Legacy: `atlas_stock_states_daily` (s) + `atlas_stock_decisions_daily` (d) in `getStocksInSector`, `getTopPicksBySector`; `atlas_sector_states_daily` in `getSectorSnapshotByName`
- Target: `atlas_stock_signal_unified`, `atlas_sector_signal_unified`
- Gate columns: TRUE AS <col>
- 3 SQL statements affected

### Task 7.4 — `sector-funds.ts`
- Legacy: `atlas_fund_states_daily` (fs) + `atlas_fund_decisions_daily` (fd) in `getSectorFunds`
- Target: `atlas_fund_signal_unified` — exposes mstar_id, date, composition_state, holdings_state, nav_state (via LEFT JOIN), recommendation
- Gate columns (performance_gate, sectors_gate, stocks_gate, market_gate, entry_trigger, exit_trigger): TRUE AS <col>
- 1 SQL statement affected

### Task 7.5 — `funds.ts`
- Legacy: `atlas_fund_states_daily` (fs) in `getAllFunds`, `getFundMaster`; `atlas_stock_states_daily` in `getFundHoldings`
- `getFundDecisionHistory` reads from `atlas_fund_decisions_daily` — no signal data, skip rewire (pure decision log)
- Target: `atlas_fund_signal_unified` for composition_state, holdings_state, nav_state, recommendation; `atlas_stock_signal_unified` for stock states in holdings
- Gate columns: TRUE AS <col>
- 3 SQL statements affected

### Task 7.2b — `etfs.ts`
- Legacy: `atlas_etf_states_daily` (s) in `getAllETFs`, `getETFByTicker`, `getLinkedETFsForSector`, `getETFStateHistory`; `atlas_stock_states_daily` in `getETFHoldings`
- Target: `atlas_etf_signal_unified` for ETF states; `atlas_stock_signal_unified` for holding stock states
- Gate columns: TRUE AS <col>
- State column `risk_state` not in view: return NULL::text
- `state_since_date` not in view; use `su.dwell_days` for days_in_state
- 5 SQL statements affected

### Task 7.5b — `conviction.ts`
- Legacy: `atlas_stock_conviction_daily` in `getStockConviction`, `getConvictionBreakdown`; `mv_top_conviction_daily` in `getConvictionMap`, `getTopConvictionByTier`
- Target: `atlas_stock_signal_unified` for within_state_rank
- `getStockConviction`: return within_state_rank as conviction_score, tier derived from rs_rank_12m tier expression
- `getConvictionBreakdown`: return null (no breakdown available from view)  
- `getConvictionMap` + `getTopConvictionByTier`: read from `atlas_stock_signal_unified`
- 3 SQL statements affected (getConvictionBreakdown becomes a stub)

### Residual files — `global.ts`, `us-stocks.ts`, `us-etfs.ts`, `us-sectors.ts`, `instruments.ts`, `health.ts`
- `global.ts`: uses `global_atlas.atlas_etf_states_daily` — that is the global schema, not the Indian atlas schema. No Indian unified view applies here. These are US/Global ETF states, not subject to this rewire. SKIP.
- `us-stocks.ts`: uses `us_atlas.atlas_stock_states_daily` — US schema only. SKIP.
- `us-etfs.ts`: uses `us_atlas.atlas_etf_states_daily` — US schema only. SKIP.
- `us-sectors.ts`: uses `us_atlas.atlas_stock_states_daily` — US schema only. SKIP.
- `instruments.ts`: uses `atlas.atlas_stock_states_daily` for rs_state picker lookup. Rewire to `atlas_stock_signal_unified`.
- `health.ts`: references are in TRACKED_TABLES constant for health monitoring (metadata, not signal queries). Keep as-is — burn-in monitoring.

## Column mapping decisions

| Legacy | View column |
|---|---|
| `s.state_since_date` | `su.dwell_days` (integer days count) |
| `s.history_gate_pass` | `TRUE AS history_gate_pass` |
| `s.liquidity_gate_pass` | `TRUE AS liquidity_gate_pass` |
| `d.strength_gate` | `TRUE AS strength_gate` |
| `d.direction_gate` | `TRUE AS direction_gate` |
| `d.risk_gate` | `TRUE AS risk_gate` |
| `d.volume_gate` | `TRUE AS volume_gate` |
| `d.sector_gate` | `TRUE AS sector_gate` |
| `d.market_gate` | `TRUE AS market_gate` |
| `d.transition_trigger` | `TRUE AS transition_trigger` |
| `d.breakout_trigger` | `TRUE AS breakout_trigger` |
| `d.exit_*` | `NULL::boolean AS exit_*` |
| `s.risk_state` | `NULL::text AS risk_state` |
| `s.volume_state` | `NULL::text AS volume_state` |
| CTS columns | `NULL::text / NULL::boolean / NULL::int` |
| `fd.performance_gate` | `TRUE AS performance_gate` |
| `fd.sectors_gate` | `TRUE AS sectors_gate` |
| `fd.stocks_gate` | `TRUE AS stocks_gate` |
| `fd.entry_trigger` | `NULL::boolean AS entry_trigger` |
| `fd.exit_trigger` | `NULL::boolean AS exit_trigger` |

## Approach justification

- Exit triggers return NULL (not TRUE) — they represent signals that need the CTS engine; returning TRUE would be wrong semantically. The consumers render exit flags visually; NULL means "unknown" which is safe.
- Gate columns return TRUE — these are availability/quality gates; absent data = pass (conservative, not blocking).
- All 4 unified views are already created by Phase 1/3; no migration needed here.
- `atlas_fund_decisions_daily` is kept for `getFundDecisionHistory` (historical decision log, not a signal read).
- US/global schema tables are out of scope — no `*_signal_unified` view in those schemas.

## Commit plan (5 commits)
1. `feat(frontend): stocks queries route through atlas_stock_signal_unified`
2. `feat(frontend): sector queries through unified view`
3. `feat(frontend): fund queries through unified view (nav_state retained)`
4. `feat(frontend): ETF queries through unified view`
5. `feat(frontend): residual queries through unified view; conviction → within_state_rank`
