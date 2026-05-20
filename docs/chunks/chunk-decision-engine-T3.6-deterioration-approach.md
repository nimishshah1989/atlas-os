# Chunk: Decision Engine Task 3.6 — Deterioration Surfacing

## Data scale
- `atlas_stock_signal_unified`: ~2K rows (one per stock, live snapshot). Under 1K in portfolio (≤30 holdings). SQL join approach.
- `strategy_fm_custom_portfolios.instruments`: JSONB array, ≤30 elements.
- `atlas_portfolio_policy`: single-digit rows.

## Key findings from codebase exploration

### engine_state availability
`getStaticPortfolioById` in `portfolios.ts` does NOT expose `engine_state`. The LATERAL join in the instruments subquery only fetches from `atlas_universe_stocks` (symbol, sector, in_nifty_100, in_nifty_500). I must extend the subquery with a second LATERAL join to `atlas_stock_signal_unified` to fetch `engine_state` per holding.

### Entry price / hard_stop_pct
No entry price, cost basis, or return-since-entry data exists anywhere in:
- `strategy_fm_custom_portfolios.instruments` JSONB (fields: instrument_id, instrument_type, weight_pct, target_weight_pct)
- Any joinable table checked (no trades table, no entry_price column found)

Decision: `hard_stop_pct` rule CANNOT be evaluated. The DeteriorationPanel will honestly label it "n/a — entry price not tracked" rather than fabricate a return-since-entry.

### EffectivePolicy shape
`getEffectivePolicy` returns `EffectivePolicy | null` where each field is `PolicyFieldValue = { value: string | string[] | boolean | null, source: 'inherited' | 'overridden' }`. Access pattern: `policy.state_exit_full.value` (a string).

### Regime worklist
`TodayWorklist` + `regime-scorecard.ts` query `mv_deterioration_watch` (cross-portfolio). This is UNTOUCHED. The new `DeteriorationPanel` is per-portfolio and policy-driven.

### Portfolio page LOC
Currently 223 LOC (≤250 limit). The new section will add ~10 lines (section + DeteriorationPanel call).

## Chosen approach

### `policy-deterioration.ts` (pure function)
```
findDeterioration(holdings: DeteriHolding[], policy: DeteriPolicy): DeteriItem[]
```
- Accepts a narrow type: each holding has `instrument_id`, `symbol`, `weight_pct`, `engine_state | null`.
- Policy params: `state_exit_trim: string | null`, `state_exit_full: string | null`.
- For each holding: match engine_state against state_exit_full (full exit) and state_exit_trim (trim).
- `hard_stop_pct`: not evaluated (no entry price). Not included in return type.
- Returns array of `DeteriItem` with `instrument_id`, `symbol`, `weight_pct`, `engine_state`, `rule: 'full_exit' | 'trim'`, `reason: string`.
- Mutual exclusivity: a stock in state_exit_full has that state, which cannot be in buy_states (exit states and buy states are disjoint by policy design). Test asserts this explicitly.

### `portfolios.ts` extension
Extend `StaticInstrument` to add `engine_state: string | null`. Extend the instruments subquery with a second LATERAL join to `atlas_stock_signal_unified` on `instrument_id`.

### `DeteriorationPanel.tsx`
Client component. Renders a table of deteriorating holdings. Each row: LinkedTicker, reason badge (full exit / trim), tooltip with explanation, current weight. Empty state: calm "No holdings hitting an exit rule."

### Portfolio page modification
Add a section after the current-vs-target section (or inside it). ~8-10 lines. Page will stay ≤250 LOC target (was 223; new section adds ≈10 = 233).

## Edge cases
- `engine_state = null`: not matched → not deteriorating (honest)
- `state_exit_trim = null` (policy field value null): skip trim check
- `state_exit_full = null`: skip full-exit check
- Same holding cannot be both trim and full-exit simultaneously (state is one value)
- Mutual exclusivity with buy_states: by policy definition, state_exit_full/trim are different states from buy_states (e.g. stage_3/stage_4 vs stage_2a/2b). Tested explicitly.

## Test plan
- `policy-deterioration.test.ts` covering:
  1. full-exit state → surfaces with full-exit reason
  2. trim state → surfaces with trim reason
  3. healthy state (stage_2) → not surfaced
  4. null engine_state → not surfaced
  5. null policy fields → no evaluation
  6. mutual exclusivity: full-exit holding's state not in buy_states
  7. empty holdings → empty result
- `DeteriorationPanel.test.tsx`:
  1. renders deteriorating rows
  2. empty state when none

## Runtime
Pure TS function: sub-millisecond. DB query addition: single LATERAL join on a ~2K-row table, indexed on instrument_id. Negligible.
