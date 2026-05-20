# Approach: Portfolio QA Fixes A1–A5

## Summary
Five display-only defects on the `/portfolios/[id]` page.

## A1 — Composition table shows UUIDs
- `CompositionView.tsx` `StaticComposition` renders `inst.instrument_id` raw.
- The query already returns `symbol` on each instrument (LATERAL join in `getStaticPortfolioById`).
- Fix: update `StaticInstrument` type in `CompositionView.tsx` to include `symbol: string | null`, render `<LinkedTicker symbol={inst.symbol} />` for stocks and `inst.symbol ?? inst.instrument_id` for non-stocks. Rename column header "ID / Ticker" → "Ticker".

## A2 — 4-decimal numbers in PolicyPanel and breach messages
- `PolicyPanel.tsx` `formatValue` for `pct` kind just does `{raw}%` — raw is `"5.0000"` from DB.
- `policy-compliance.ts` `checkCashFloor` uses `.toFixed(4)`.
- Fix: use existing `formatThreshold` from `format-number.ts` for pct fields (it trims trailing zeros, keeps min 2 decimals → "5.00", need to trim further to max 1 decimal). Add `formatPct` and `formatRank` helpers to `format-number.ts`. Fix the breach message in `policy-compliance.ts`.

## A3 — Raw enum strings
- `PolicyPanel.tsx` `state_exit_trim` / `state_exit_full` / `instrument_universe` are `'text'` kind → just `String(raw)`.
- `buy_states` renders chips with raw stage strings.
- `DeteriorationPanel.tsx` renders `{item.engine_state}` directly.
- Fix: add `STAGE_LABEL` and `INSTRUMENT_UNIVERSE_LABEL` maps to `frontend/src/lib/stage-labels.ts` (new file). Apply in `PolicyPanel.tsx`, `DeteriorationPanel.tsx`. `buy_states` chips in `PolicyPanel.tsx` already show raw values.

## A4 — Max Drawdown shows "+0.00%"
- `fmtPct` in `page.tsx` returns `+0.00%` when `latest_max_drawdown` is `"0.0000"` (zero string, not null).
- Fix: treat zero drawdown as null/missing (drawdown of exactly 0 means no backtest ran). Change `fmtPct` to also return `'—'` when `n === 0` for the drawdown case, or more precisely: pass the raw value through a guard that also checks for zero. Simplest surgical fix: rename `fmtPct` to a general helper and add a `fmtDrawdown` that returns `'—'` for zero.

## A5 — Dev jargon in empty states
- `EquityCurveChart.tsx` (shared in `components/charts/`) line 80: `"Backtest equity series unavailable in v0 — coming with M16 paper-trader hookup."` 
- `DrawdownChart.tsx` line 69: `"No drawdown data — paper trading not yet active."` (this one is fine, no jargon)
- `page.tsx` line 170: `"Paper trading for Rule-Based portfolios connects in M16."` (out of scope but noted)
- Fix: update the two chart components' empty state text. Also fix `page.tsx` line 170 (it's in the files touched).

## Files to modify
- `frontend/src/app/portfolios/[id]/CompositionView.tsx` — A1
- `frontend/src/lib/format-number.ts` — A2 (add formatPct, formatRank)
- `frontend/src/lib/policy-compliance.ts` — A2 (breach message formatting)
- `frontend/src/lib/stage-labels.ts` — A3 (new shared label map)
- `frontend/src/components/portfolio/PolicyPanel.tsx` — A2, A3
- `frontend/src/components/portfolio/DeteriorationPanel.tsx` — A3
- `frontend/src/components/portfolio/CurrentVsTarget.tsx` — A2 (breach messages, none needed directly — breach comes from compliance.ts)
- `frontend/src/components/charts/EquityCurveChart.tsx` — A5
- `frontend/src/app/portfolios/[id]/page.tsx` — A4, A5

## Tests to add/update
- `CompositionView` test for ticker rendering
- `PolicyPanel` test for formatted pct values and label translation
- Update `EquityCurveChart` test to match new empty-state text
- `DeteriorationPanel` test for human-readable state labels
