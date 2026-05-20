# Chunk Task 3.4 — "Act" Affordance on Stock Detail

## Data scale
Not applicable — this is a write path that inserts at most one row per click into
`atlas_portfolio_proposed_change`. No large data reads.

## Position-sizing inputs audit

### Real inputs (wired from DB/policy)
- `max_per_stock_pct`: from `getEffectivePolicy(portfolioId)` — a real policy value read
  from `atlas.atlas_portfolio_policy`.
- `regime_cap`: from `getCurrentRegime()` — `deployment_multiplier * 100` converts the
  fraction (e.g. 0.85) to whole-number percent (85). This is real data.

### Not-yet-available inputs (honest defaults used)
- `target_gap`: sector target gap requires knowing the portfolio's current sector weight
  vs its target weight. No sector-level target tracking is wired in the stock-detail page.
  Honest default: `max_per_stock_pct` (i.e. treat as if gap == max_per_stock so the
  `target_gap` cap does not bind more tightly than `max_per_stock`).
- `current_invested`: requires portfolio holdings summation. Not available on stock-detail
  page. Honest default: `0` (i.e. assume no deployment yet — gives the upper bound).

Net effect: with `target_gap = max_per_stock` and `current_invested = 0`, the binding
constraint will be either `max_per_stock` or `regime_cap`. This is the defensible honest
minimum — both values are real. The component labels these constraints correctly.

The component is honest about what is real: the suggestion label says which constraint
bound the size. When `max_per_stock_pct` binds, the label reads "stock-cap-bound". When
`regime_cap` binds (low deployment multiplier regime), it reads "regime-cap-bound".

## Architecture

### `frontend/src/components/portfolio/ActButton.tsx`
- `'use client'` component (needs `useState`, `fetch`)
- Props: `{ portfolioId: string | undefined, portfolioName: string | undefined,
           instrumentId: string, suggestedPct: string | null,
           bindingConstraint: string | null }`
- When `portfolioId` is absent: shows disabled secondary "Select a portfolio to size
  this position" message. No number shown.
- When active: shows "Add to [name] — suggest X.X% ([constraint]-bound)"
- On click: POSTs to `/api/portfolio/propose`. Shows loading state, then
  confirmation or error message.
- Binding constraint → plain English map: target_gap→"gap-bound",
  max_per_stock→"stock-cap-bound", regime_cap→"regime-cap-bound", none→"manual".

### `frontend/src/app/api/portfolio/propose/route.ts`
- POST handler only
- Direct DB write using `sql` from `@/lib/db` (no FastAPI proxy needed — this is a
  simple parameterized INSERT, no compute)
- Validates: portfolio_id is UUID, instrument_id is UUID, proposed_weight is positive number
- Parameterized INSERT into `atlas.atlas_portfolio_proposed_change`
- Returns `{data: {id, status: 'pending'}}` on success or `{error_code, message}` on bad input
- Matches the Atlas error envelope pattern seen in other routes

### `frontend/src/app/stocks/[symbol]/page.tsx`
- Add `searchParams` to read `?portfolio=` param
- Load `getEffectivePolicy(portfolioId)` and `getCurrentRegime()` when portfolioId present
- Compute `suggestedPct` and `bindingConstraint` using the sizing logic
- Pass to `<ActButton>` at the bottom of the page (after HitRateRow, before close)

## Edge cases
- No portfolio selected → disabled button, honest message, no number
- Policy not configured (null) → disabled button, "policy not configured" message
- proposed_weight = 0 (regime clamps to 0 due to Risk-Off) → show "0.0% (regime-cap-bound)"
  with different styling (amber, can still propose a 0-size "watch" entry — or disable)
  Decision: if suggested_pct = 0 disable the submit (no point proposing zero weight)
- DB INSERT fails → error message shown inline

## API route conventions matched
- `export const dynamic = 'force-dynamic'`
- `import { NextRequest, NextResponse } from 'next/server'`
- Returns `NextResponse.json({...}, { status: N })`
- Uses parameterized `sql` queries (no f-strings)
- UUID validation via regex check before DB call
- Error shape: `{ error_code: string, message: string }` on errors

## Tests
- `src/__tests__/portfolios/ActButton.test.tsx`:
  1. Renders disabled state with no-portfolio message when portfolioId not provided
  2. Shows suggestion text with constraint label when props provided
  3. Disabled/no-submit when suggestedPct is "0.0"
  4. On click, calls fetch POST; shows confirmation on success; shows error on failure
- `src/__tests__/portfolios/propose-route.test.ts`:
  1. Rejects missing portfolio_id
  2. Rejects invalid UUID portfolio_id
  3. Rejects non-positive proposed_weight
  4. Happy path inserts row and returns {id, status}

## Expected runtime
Single row INSERT — sub-millisecond DB write. No compute.
