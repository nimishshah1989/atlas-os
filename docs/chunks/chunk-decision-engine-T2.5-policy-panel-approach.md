# chunk-decision-engine-T2.5 — Policy Panel UI

## Task
Surface the effective policy for a portfolio on the portfolio detail page.

## Files in scope
- `frontend/src/lib/queries/policy.ts` (new — note: `policies.ts` already exists for decision policy, so new file is `policy.ts`)
- `frontend/src/components/portfolio/PolicyPanel.tsx` (new component)
- `frontend/src/app/portfolios/[id]/page.tsx` (modify — add panel, keep ≤250 LOC)
- `frontend/src/__tests__/portfolios/PolicyPanel.test.tsx` (new test)

## Data scale
- `atlas_portfolio_policy`: single-digit rows (1 house default + N portfolio overrides). No pagination needed.
- Query strategy: 2 SELECTs (house + portfolio row) — both tiny, trivial latency.

## Approach

### query (`policy.ts`)
- Uses `sql` tagged-template helper (same as `portfolios.ts`, `policies.ts`).
- Two queries: `SELECT ... FROM atlas.atlas_portfolio_policy WHERE is_house_default = TRUE LIMIT 1` and `SELECT ... WHERE portfolio_id = $id LIMIT 1`.
- Returns `EffectivePolicyRow`: per field `{ value: string | string[] | boolean | null, source: 'inherited' | 'overridden' }`.
- Merge semantics: for each field, if the portfolio row exists and field is non-null, source = 'overridden'; else source = 'inherited', value from house default.
- If house row doesn't exist: return null (caller renders empty state).
- Numeric columns from Postgres arrive as strings via `postgres` driver; keep as strings for display.
- Array column `buy_states` comes back as a JS array.

### component (`PolicyPanel.tsx`)
- Pure presentational 'use client' component (takes `EffectivePolicyRow[]` as prop, no DB calls).
- Actually takes `policy: EffectivePolicy | null` where `EffectivePolicy` is the typed structure.
- Renders 7 groups: Deployment / Concentration / Entry / Exit / Instrument / Benchmark / Cadence.
- Per field: label + value + InfoTooltip (inline string, not MetricTooltip — avoids extending the metric registry with non-metric concepts). Every field gets a real definition string.
- Source marker: 'inherited' (grey badge) vs 'overridden' (teal badge).
- pct fields format: `${value}%`; rank fields: as-is (already `0.60` etc); booleans: 'Yes'/'No'; buy_states: one badge per state; text fields: display as-is; null trailing_stop_pct: 'Off'.
- Empty state (null policy): explicit "Policy not configured" card — no crash, no fake values.
- Budget: ≤350 LOC.

### page modification
- Current `page.tsx` is 165 LOC — adding the panel section + import stays well under 250.
- Import `PolicyPanel` and `getEffectivePolicy`.
- Fetch policy in the `Promise.all` with the existing fetches (or a parallel `await`).
- Add a `#policy` anchor and section below the composition section.
- Nav bar gets a 'policy' link added.

### Tooltip system
- Using `InfoTooltip` directly (inline string prop) — NOT MetricTooltip/metric-registry.
- Rationale: policy fields are config parameters, not financial metrics. Extending the metric-registry with policy fields would muddy its purpose.
- Every field gets its own definition string inlined in the PolicyPanel component.

## Edge cases
- No house-default row: `getEffectivePolicy` returns `null`. PolicyPanel shows "Policy not configured".
- Portfolio has no override row: all fields show house default, all source = 'inherited'.
- `trailing_stop_pct` is null in house default (by design): value displays as 'Off', source = 'inherited'.
- `buy_states` empty array: render empty badges section.

## LOC budget check
- `policy.ts`: ~80 LOC
- `PolicyPanel.tsx`: ~280-320 LOC (within 350 budget for a component, 600 limit applies)
- `page.tsx` after changes: ~190 LOC (under 250)
- `PolicyPanel.test.tsx`: ~150-180 LOC (under 800)

## Wiki patterns checked
- Tooltip pattern: `InfoTooltip` with Radix UI — used by `MetricTooltip.tsx`.
- Query pattern: `sql` tagged-template, server-only, return typed array.
- Component pattern: 'use client', props-driven, no DB calls.
- Empty state pattern: `<p className="font-sans text-sm text-ink-tertiary">...</p>`.
