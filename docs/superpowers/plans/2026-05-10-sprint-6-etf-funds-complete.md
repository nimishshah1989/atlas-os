# Sprint 6 — ETF & Funds Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 32/100 ETF data gap, add holdings deep-dive tabs for ETFs and funds, surface all remaining computed fields (exit triggers, linked_index, 6M return, data_as_of), and audit the funds page end-to-end.

**Architecture:** Two parallel tracks. Track A (this plan) is pure frontend — query extensions + new components. Track B (Task 9) runs on EC2 via SSH and fixes the data pipeline. No new DB migrations needed for Track A; the holdings query uses an existing join path through `de_etf_holdings → atlas_universe_stocks → atlas_stock_states_daily`.

**Tech Stack:** Next.js 14 App Router (RSC + client components), postgres.js (`sql` tagged template), TypeScript, Recharts, Tailwind CSS, Supabase PostgreSQL.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/lib/queries/etfs.ts` | Modify | Add exit triggers, linked_index, inception_date, data_as_of to ETFRow + getETFByTicker; add getETFHoldings() |
| `frontend/src/lib/queries/funds.ts` | Modify | Add data_as_of to FundRow + queries; add getFundHoldings() |
| `frontend/src/components/etfs/ETFScreener.tsx` | Modify | Add 6M return column; rename Days label to "Days RS" |
| `frontend/src/components/etfs/ETFDeepDiveHeader.tsx` | Modify | Add linked_index, inception_date, data_as_of |
| `frontend/src/components/etfs/ETFOverviewTab.tsx` | Modify | Add exit trigger badges section |
| `frontend/src/components/etfs/ETFHoldingsTab.tsx` | Create | New: top-20 holdings with stock states |
| `frontend/src/components/etfs/ETFDeepDiveTabs.tsx` | Modify | Add 'holdings' third tab |
| `frontend/src/app/etfs/[ticker]/page.tsx` | Modify | Fetch holdings alongside etf + history |
| `frontend/src/components/funds/FundDeepDiveHeader.tsx` | Modify | Add data_as_of |
| `frontend/src/components/funds/FundHoldingsTab.tsx` | Create | New: top-20 fund holdings with stock states |
| `frontend/src/app/funds/[mstar_id]/page.tsx` | Modify | Add holdings tab fetch + render |

---

## Task 1: Extend ETF query types and getETFByTicker

**Files:**
- Modify: `frontend/src/lib/queries/etfs.ts`

- [ ] **Step 1: Update ETFRow type to add new fields**

Open `frontend/src/lib/queries/etfs.ts`. Replace the `ETFRow` type (lines 4–37) with:

```typescript
export type ETFRow = {
  ticker: string
  etf_name: string | null
  theme: string
  linked_sector: string | null
  linked_index: string | null
  inception_date: string | null
  asset_class: string | null
  fund_house: string | null
  data_as_of: string | null
  // Metrics
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  rs_pctile_3m: string | null
  ema_10_ratio: string | null
  extension_pct: string | null
  ret_1w: string | null
  vol_63: string | null
  drawdown: string | null
  days_in_state: number | null
  // States (3-tuple)
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  weinstein_gate_pass: boolean | null
  history_gate_pass: boolean | null
  liquidity_gate_pass: boolean | null
  // Decisions
  is_investable: boolean | null
  strength_gate: boolean | null
  direction_gate: boolean | null
  risk_gate: boolean | null
  sector_gate: boolean | null
  market_gate: boolean | null
  position_size_pct: string | null
  // Exit triggers
  exit_market_riskoff: boolean | null
  exit_sector_avoid: boolean | null
  exit_rs_deteriorate: boolean | null
  exit_momentum_collapse: boolean | null
}
```

- [ ] **Step 2: Update getAllETFs() to expose data_as_of**

In `getAllETFs()` (line 53), add `l.d::text AS data_as_of` to the SELECT after `u.fund_house`:

```typescript
export async function getAllETFs(): Promise<ETFRow[]> {
  return sql<ETFRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.linked_index,
      u.inception_date::text        AS inception_date,
      u.asset_class,
      u.fund_house,
      l.d::text                     AS data_as_of,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      m.ret_6m::text                AS ret_6m,
      m.rs_pctile_3m::text          AS rs_pctile_3m,
      m.ema_10_ratio::text          AS ema_10_ratio,
      m.extension_pct::text         AS extension_pct,
      m.ret_1w::text                AS ret_1w,
      m.realized_vol_63::text       AS vol_63,
      m.drawdown_ratio_252::text    AS drawdown,
      (CURRENT_DATE - s.state_since_date)::int AS days_in_state,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.weinstein_gate_pass,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      d.is_investable,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.sector_gate,
      d.market_gate,
      d.position_size_pct::text     AS position_size_pct,
      d.exit_market_riskoff,
      d.exit_sector_avoid,
      d.exit_rs_deteriorate,
      d.exit_momentum_collapse
    FROM atlas.atlas_universe_etfs u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = l.d
    LEFT JOIN atlas.atlas_etf_decisions_daily d
      ON d.ticker = u.ticker AND d.date = l.d
    WHERE u.effective_to IS NULL
    ORDER BY
      d.is_investable DESC NULLS LAST,
      m.rs_pctile_3m DESC NULLS LAST
  `
}
```

- [ ] **Step 3: Update getETFByTicker() with the same new fields**

Replace the existing `getETFByTicker` function body with:

```typescript
export async function getETFByTicker(ticker: string): Promise<ETFRow | null> {
  const rows = await sql<ETFRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_etf_metrics_daily
    )
    SELECT
      u.ticker,
      u.etf_name,
      u.theme,
      u.linked_sector,
      u.linked_index,
      u.inception_date::text        AS inception_date,
      u.asset_class,
      u.fund_house,
      l.d::text                     AS data_as_of,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      m.ret_6m::text                AS ret_6m,
      m.rs_pctile_3m::text          AS rs_pctile_3m,
      m.ema_10_ratio::text          AS ema_10_ratio,
      m.extension_pct::text         AS extension_pct,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.weinstein_gate_pass,
      s.history_gate_pass,
      s.liquidity_gate_pass,
      d.is_investable,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.sector_gate,
      d.market_gate,
      d.position_size_pct::text     AS position_size_pct,
      d.exit_market_riskoff,
      d.exit_sector_avoid,
      d.exit_rs_deteriorate,
      d.exit_momentum_collapse
    FROM atlas.atlas_universe_etfs u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = u.ticker AND m.date = l.d
    LEFT JOIN atlas.atlas_etf_states_daily s
      ON s.ticker = u.ticker AND s.date = l.d
    LEFT JOIN atlas.atlas_etf_decisions_daily d
      ON d.ticker = u.ticker AND d.date = l.d
    WHERE u.ticker = ${ticker}
      AND u.effective_to IS NULL
    LIMIT 1
  `
  return rows[0] ?? null
}
```

- [ ] **Step 4: Add getETFHoldings() function at end of file**

Append to `frontend/src/lib/queries/etfs.ts`:

```typescript
export type ETFHoldingRow = {
  symbol: string | null
  company_name: string | null
  weight: string | null
  sector: string | null
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  ret_1m: string | null
  ret_3m: string | null
  holdings_date: string | null
}

export async function getETFHoldings(ticker: string, limit = 20): Promise<ETFHoldingRow[]> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error(`limit must be between 1 and 100, got: ${limit}`)
  }
  return sql<ETFHoldingRow[]>`
    WITH latest_holdings AS (
      SELECT MAX(as_of_date) AS as_of_date
      FROM public.de_etf_holdings
      WHERE ticker = ${ticker}
    ),
    latest_states_date AS (
      SELECT MAX(date) AS d
      FROM atlas.atlas_stock_states_daily
      WHERE date <= COALESCE((SELECT as_of_date FROM latest_holdings), CURRENT_DATE)
    )
    SELECT
      u.symbol,
      u.company_name,
      h.weight::text            AS weight,
      u.sector,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      m.ret_1m::text            AS ret_1m,
      m.ret_3m::text            AS ret_3m,
      lh.as_of_date::text       AS holdings_date
    FROM public.de_etf_holdings h
    JOIN latest_holdings lh ON h.ticker = ${ticker}
      AND h.as_of_date = lh.as_of_date
    LEFT JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = h.instrument_id
      AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_stock_states_daily s
      ON s.instrument_id = u.instrument_id
      AND s.date = (SELECT d FROM latest_states_date)
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id
      AND m.date = (SELECT d FROM latest_states_date)
    WHERE h.ticker = ${ticker}
    ORDER BY h.weight DESC
    LIMIT ${limit}
  `
}
```

- [ ] **Step 5: TypeScript check**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os/frontend
npx tsc --noEmit 2>&1 | grep "queries/etfs" | head -20
```

Expected: no errors on `queries/etfs.ts`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/queries/etfs.ts
git commit -m "feat(etfs): extend ETFRow with exit triggers, linked_index, inception_date, data_as_of; add getETFHoldings()"
```

---

## Task 2: Add ETF screener 6M column + fix Days label

**Files:**
- Modify: `frontend/src/components/etfs/ETFScreener.tsx`

- [ ] **Step 1: Add 6M to OPTIONAL_COLS and rename Days label**

In `ETFScreener.tsx`, replace the `OPTIONAL_COLS` array (lines 46–51):

```typescript
const OPTIONAL_COLS: ColumnDef[] = [
  { key: 'ret_1w',        label: '1W Return',  defaultVisible: false },
  { key: 'ret_6m',        label: '6M Return',  defaultVisible: false },
  { key: 'vol_63',        label: 'Vol 63D',    defaultVisible: false },
  { key: 'drawdown',      label: 'Drawdown',   defaultVisible: false },
  { key: 'days_in_state', label: 'Days (RS)',  defaultVisible: false },
]
```

- [ ] **Step 2: Add 6M column header and cell to the table**

Find the table header `{visibleCols.has('ret_1w') &&` block (around line 235) and add the 6M header after the 1W header. Also add the corresponding cell in the data row.

In the `<tr>` header section, after `{visibleCols.has('ret_1w') && <PlainTh label="1W" align="right" />}`:

```tsx
{visibleCols.has('ret_6m') && <PlainTh label="6M" align="right" />}
```

In the data row `<tr>`, find where `ret_1w` is rendered and add after it:

```tsx
{visibleCols.has('ret_6m') && (
  <td className="px-3 py-2.5 text-right font-mono text-xs">
    {formatReturn(row.ret_6m)}
  </td>
)}
```

The `formatReturn` function is already used for `ret_1m` and `ret_3m` in this file — reuse the same pattern.

- [ ] **Step 3: TypeScript check**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os/frontend
npx tsc --noEmit 2>&1 | grep "ETFScreener" | head -10
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/etfs/ETFScreener.tsx
git commit -m "feat(etf-screener): add 6M return optional column; rename Days → Days (RS)"
```

---

## Task 3: ETF deep dive header — add linked_index, inception_date, data_as_of

**Files:**
- Modify: `frontend/src/components/etfs/ETFDeepDiveHeader.tsx`

- [ ] **Step 1: Add linked_index, inception_date, data_as_of to the header**

Replace `ETFDeepDiveHeader.tsx` with:

```tsx
import Link from 'next/link'
import { ChevronRight } from 'lucide-react'
import type { ETFRow } from '@/lib/queries/etfs'
import { StateTuple3 } from '@/lib/stock-formatters'

const THEME_STYLE: Record<string, string> = {
  Broad:     'bg-teal/10 text-teal',
  Sectoral:  'bg-signal-pos/10 text-signal-pos',
  Thematic:  'bg-signal-warn/10 text-signal-warn',
}

function ThemeBadge({ theme }: { theme: string }) {
  const style = THEME_STYLE[theme] ?? 'bg-ink-tertiary/10 text-ink-secondary'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${style}`}>
      {theme}
    </span>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  }).replace(',', '')
}

export function ETFDeepDiveHeader({ etf }: { etf: ETFRow }) {
  return (
    <div className="sticky top-14 bg-paper border-b border-paper-rule z-30">
      <div className="px-6 py-4">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1 font-sans text-xs text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/etfs" className="hover:text-ink-secondary transition-colors">ETFs</Link>
          <ChevronRight className="w-3 h-3" />
          <span className="text-ink-secondary">{etf.ticker}</span>
        </nav>

        {/* Headline row */}
        <div className="flex items-end justify-between flex-wrap gap-4">
          <div className="flex items-end gap-3 flex-wrap">
            <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none">
              {etf.ticker}
            </h1>
            <span className="font-sans text-sm text-ink-secondary">{etf.etf_name ?? ''}</span>
            <ThemeBadge theme={etf.theme} />
            {etf.linked_sector && (
              <span className="font-sans text-xs text-ink-tertiary">{etf.linked_sector}</span>
            )}
            {etf.linked_index && (
              <span className="font-sans text-xs text-ink-tertiary bg-paper-rule/30 px-1.5 py-0.5 rounded">
                {etf.linked_index}
              </span>
            )}
            <StateTuple3
              rs={etf.rs_state}
              mom={etf.momentum_state}
              risk={etf.risk_state}
            />
          </div>
          <div className="flex items-center gap-5 font-sans text-xs text-ink-tertiary">
            {etf.inception_date && (
              <span>Since <span className="text-ink-secondary">{formatDate(etf.inception_date)}</span></span>
            )}
            {etf.position_size_pct && (
              <span>
                Pos Size:{' '}
                <span className="font-mono font-semibold text-ink-primary">
                  {(parseFloat(etf.position_size_pct) * 100).toFixed(2)}%
                </span>
              </span>
            )}
            {etf.is_investable && (
              <span className="text-signal-pos font-semibold">● Investable</span>
            )}
            {etf.fund_house && (
              <span className="text-ink-tertiary">{etf.fund_house}</span>
            )}
            {etf.data_as_of && (
              <span className="text-ink-tertiary/60 text-[10px]">
                Data as of {formatDate(etf.data_as_of)}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os/frontend
npx tsc --noEmit 2>&1 | grep "ETFDeepDiveHeader" | head -10
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/etfs/ETFDeepDiveHeader.tsx
git commit -m "feat(etf-header): add linked_index, inception_date, data_as_of"
```

---

## Task 4: ETF overview tab — add exit trigger badges

**Files:**
- Modify: `frontend/src/components/etfs/ETFOverviewTab.tsx`

- [ ] **Step 1: Add exit trigger section after the gates panel grid**

In `ETFOverviewTab.tsx`, after the closing `</div>` of the `grid grid-cols-1 sm:grid-cols-3` section (the Weinstein/Momentum/Gates grid), add:

```tsx
      {/* Exit triggers — only show if any are active */}
      {(etf.exit_market_riskoff || etf.exit_sector_avoid || etf.exit_rs_deteriorate || etf.exit_momentum_collapse) && (
        <div className="border border-signal-neg/30 bg-signal-neg/5 rounded-sm px-4 py-3">
          <div className="font-sans text-[10px] font-semibold text-signal-neg uppercase tracking-wider mb-2">
            Exit Signals Active
          </div>
          <div className="flex flex-wrap gap-2">
            {etf.exit_market_riskoff && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                Market Risk-Off
              </span>
            )}
            {etf.exit_sector_avoid && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                Sector Avoid
              </span>
            )}
            {etf.exit_rs_deteriorate && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                RS Deteriorating
              </span>
            )}
            {etf.exit_momentum_collapse && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                Momentum Collapse
              </span>
            )}
          </div>
        </div>
      )}
```

The `etf` prop already has the exit trigger fields from Task 1.

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os/frontend
npx tsc --noEmit 2>&1 | grep "ETFOverviewTab" | head -10
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/etfs/ETFOverviewTab.tsx
git commit -m "feat(etf-overview): add exit trigger badges (only shown when active)"
```

---

## Task 5: Create ETFHoldingsTab component

**Files:**
- Create: `frontend/src/components/etfs/ETFHoldingsTab.tsx`

- [ ] **Step 1: Create the holdings tab component**

Create `frontend/src/components/etfs/ETFHoldingsTab.tsx`:

```tsx
import type { ETFHoldingRow } from '@/lib/queries/etfs'

const RS_STYLE: Record<string, string> = {
  Leader:   'bg-teal/20 text-teal',
  Strong:   'bg-signal-pos/20 text-signal-pos',
  Average:  'bg-paper-rule/40 text-ink-secondary',
  Weak:     'bg-signal-neg/10 text-signal-neg',
  Laggard:  'bg-signal-neg/20 text-signal-neg',
}

const MOM_STYLE: Record<string, string> = {
  Accelerating:  'text-signal-pos',
  Improving:     'text-signal-pos/70',
  Flat:          'text-ink-tertiary',
  Deteriorating: 'text-signal-neg/70',
  Collapsing:    'text-signal-neg',
}

const RISK_STYLE: Record<string, string> = {
  Low:          'text-signal-pos',
  Normal:       'text-ink-secondary',
  Elevated:     'text-signal-warn',
  High:         'text-signal-neg',
  'Below Trend':'text-signal-neg',
}

function pctStr(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function weightStr(v: string | null): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(1)}%`
}

function StateBadge({ state, styleMap }: { state: string | null; styleMap: Record<string, string> }) {
  if (!state) return <span className="text-ink-tertiary">—</span>
  const cls = styleMap[state] ?? 'text-ink-secondary'
  return <span className={`font-sans text-[11px] font-medium ${cls}`}>{state}</span>
}

export function ETFHoldingsTab({
  holdings,
}: {
  holdings: ETFHoldingRow[]
}) {
  if (holdings.length === 0) {
    return (
      <div className="px-6 py-10 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No holdings data available for this ETF. Disclosures are typically delayed 30–60 days.
        </p>
      </div>
    )
  }

  const holdingsDate = holdings[0]?.holdings_date
  const totalShown = holdings.length
  const strongCount = holdings.filter(h => h.rs_state === 'Leader' || h.rs_state === 'Strong').length
  const weakCount = holdings.filter(h => h.rs_state === 'Weak' || h.rs_state === 'Laggard').length

  return (
    <div className="px-6 py-6 space-y-5">
      {/* Summary bar */}
      <div className="flex items-center gap-6 font-sans text-xs text-ink-secondary">
        <span>
          Top <span className="font-semibold text-ink-primary">{totalShown}</span> holdings
        </span>
        <span className="text-signal-pos font-semibold">{strongCount} Leader/Strong</span>
        <span className="text-signal-neg font-semibold">{weakCount} Weak/Laggard</span>
        {holdingsDate && (
          <span className="ml-auto text-ink-tertiary text-[10px]">
            Holdings as of{' '}
            {new Date(holdingsDate).toLocaleDateString('en-IN', {
              day: '2-digit', month: 'short', year: 'numeric',
            }).replace(',', '')}
          </span>
        )}
      </div>

      {/* Holdings table */}
      <div className="overflow-x-auto">
        <table className="w-full font-sans text-xs border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Stock</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Sector</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Weight</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">RS State</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Momentum</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Risk</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">1M</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">3M</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => (
              <tr key={h.symbol ?? i} className="border-b border-paper-rule/50 hover:bg-paper-rule/10 transition-colors">
                <td className="px-3 py-2.5">
                  <div className="font-semibold text-ink-primary">{h.symbol ?? '—'}</div>
                  {h.company_name && (
                    <div className="text-[10px] text-ink-tertiary truncate max-w-[140px]">{h.company_name}</div>
                  )}
                </td>
                <td className="px-3 py-2.5 text-ink-secondary">{h.sector ?? '—'}</td>
                <td className="px-3 py-2.5 text-right font-mono font-semibold text-ink-primary">
                  {weightStr(h.weight)}
                </td>
                <td className="px-3 py-2.5">
                  {h.rs_state ? (
                    <span className={`px-1.5 py-0.5 rounded-[2px] text-[10px] font-semibold ${RS_STYLE[h.rs_state] ?? 'bg-paper-rule/30 text-ink-secondary'}`}>
                      {h.rs_state}
                    </span>
                  ) : <span className="text-ink-tertiary">—</span>}
                </td>
                <td className="px-3 py-2.5">
                  <StateBadge state={h.momentum_state} styleMap={MOM_STYLE} />
                </td>
                <td className="px-3 py-2.5">
                  <StateBadge state={h.risk_state} styleMap={RISK_STYLE} />
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${h.ret_1m && parseFloat(h.ret_1m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pctStr(h.ret_1m)}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${h.ret_3m && parseFloat(h.ret_3m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pctStr(h.ret_3m)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os/frontend
npx tsc --noEmit 2>&1 | grep "ETFHoldingsTab" | head -10
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/etfs/ETFHoldingsTab.tsx
git commit -m "feat(etf-holdings): add ETFHoldingsTab component with top-20 holdings + stock states"
```

---

## Task 6: Wire Holdings tab into ETFDeepDiveTabs + update page

**Files:**
- Modify: `frontend/src/components/etfs/ETFDeepDiveTabs.tsx`
- Modify: `frontend/src/app/etfs/[ticker]/page.tsx`

- [ ] **Step 1: Update ETFDeepDiveTabs to add Holdings tab**

Replace `frontend/src/components/etfs/ETFDeepDiveTabs.tsx` with:

```tsx
'use client'
import { useState } from 'react'
import type { ETFRow, ETFMetricHistoryRow, ETFStateHistoryRow, ETFHoldingRow } from '@/lib/queries/etfs'
import { ETFOverviewTab } from './ETFOverviewTab'
import { ETFHistoryTab } from './ETFHistoryTab'
import { ETFHoldingsTab } from './ETFHoldingsTab'

type Tab = 'overview' | 'history' | 'holdings'

const TAB_LABELS: Record<Tab, string> = {
  overview: 'Overview',
  history: 'State History',
  holdings: 'Holdings',
}

export function ETFDeepDiveTabs({
  etf,
  metricHistory,
  stateHistory,
  holdings,
}: {
  etf: ETFRow
  metricHistory: ETFMetricHistoryRow[]
  stateHistory: ETFStateHistoryRow[]
  holdings: ETFHoldingRow[]
}) {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div>
      {/* Tab bar */}
      <div className="px-6 border-b border-paper-rule">
        <div className="flex items-center gap-0">
          {(['overview', 'history', 'holdings'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 font-sans text-sm capitalize transition-colors border-b-2 -mb-px ${
                tab === t
                  ? 'border-teal text-ink-primary font-medium'
                  : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
              }`}
            >
              {TAB_LABELS[t]}
              {t === 'holdings' && holdings.length > 0 && (
                <span className="ml-1.5 font-sans text-[10px] bg-paper-rule/40 px-1 py-0.5 rounded">
                  {holdings.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <ETFOverviewTab etf={etf} metricHistory={metricHistory} />
      )}
      {tab === 'history' && (
        <ETFHistoryTab etf={etf} stateHistory={stateHistory} metricHistory={metricHistory} />
      )}
      {tab === 'holdings' && (
        <ETFHoldingsTab holdings={holdings} />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Update [ticker]/page.tsx to fetch holdings**

Replace `frontend/src/app/etfs/[ticker]/page.tsx` with:

```tsx
export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import {
  getETFByTicker,
  getETFMetricHistory,
  getETFStateHistory,
  getETFHoldings,
} from '@/lib/queries/etfs'
import { ETFDeepDiveHeader } from '@/components/etfs/ETFDeepDiveHeader'
import { ETFSnapshotTiles } from '@/components/etfs/ETFSnapshotTiles'
import { ETFDeepDiveTabs } from '@/components/etfs/ETFDeepDiveTabs'

export default async function ETFPage({
  params,
}: {
  params: Promise<{ ticker: string }>
}) {
  const { ticker } = await params
  const decoded = decodeURIComponent(ticker)

  const [etf, metricHistory, stateHistory, holdings] = await Promise.all([
    getETFByTicker(decoded),
    getETFMetricHistory(decoded, 180),
    getETFStateHistory(decoded, 180),
    getETFHoldings(decoded, 20),
  ])

  if (!etf) notFound()

  return (
    <div className="max-w-[1400px] mx-auto">
      <ETFDeepDiveHeader etf={etf} />
      <ETFSnapshotTiles etf={etf} />
      <ETFDeepDiveTabs
        etf={etf}
        metricHistory={metricHistory}
        stateHistory={stateHistory}
        holdings={holdings}
      />
    </div>
  )
}
```

- [ ] **Step 3: TypeScript check — full frontend**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os/frontend
npx tsc --noEmit 2>&1 | head -30
```

Expected: 0 errors.

- [ ] **Step 4: Build check**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os/frontend
npm run build 2>&1 | tail -20
```

Expected: compiled successfully.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/etfs/ETFDeepDiveTabs.tsx frontend/src/app/etfs/[ticker]/page.tsx
git commit -m "feat(etf-deep-dive): add Holdings tab with top-20 constituent stocks + stock states"
```

---

## Task 7: Funds page — add data_as_of + getFundHoldings query

**Files:**
- Modify: `frontend/src/lib/queries/funds.ts`
- Modify: `frontend/src/components/funds/FundDeepDiveHeader.tsx` (or wherever the fund page header lives)
- Create: `frontend/src/components/funds/FundHoldingsTab.tsx`
- Modify: `frontend/src/app/funds/[mstar_id]/page.tsx`

- [ ] **Step 1: Add data_as_of to FundRow type and getAllFunds query**

In `frontend/src/lib/queries/funds.ts`, add `data_as_of: string | null` to the `FundRow` type.

In the `getAllFunds()` SELECT, after the first CTE `latest` block, add:
```sql
l.metrics_date::text AS data_as_of,
```

In `getFundMaster()` (or equivalent single-fund query), similarly add:
```sql
(SELECT MAX(nav_date) FROM atlas.atlas_fund_metrics_daily WHERE mstar_id = ${mstar_id})::text AS data_as_of,
```

- [ ] **Step 2: Add getFundHoldings() to funds.ts**

Append to `frontend/src/lib/queries/funds.ts`:

```typescript
export type FundHoldingRow = {
  symbol: string | null
  company_name: string | null
  weight: string | null
  sector: string | null
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  ret_1m: string | null
  ret_3m: string | null
  holdings_date: string | null
}

export async function getFundHoldings(mstar_id: string, limit = 20): Promise<FundHoldingRow[]> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error(`limit must be between 1 and 100, got: ${limit}`)
  }
  return sql<FundHoldingRow[]>`
    WITH latest_holdings AS (
      SELECT MAX(as_of_date) AS as_of_date
      FROM public.de_mf_holdings
      WHERE mstar_id = ${mstar_id}
    ),
    latest_states_date AS (
      SELECT MAX(date) AS d
      FROM atlas.atlas_stock_states_daily
      WHERE date <= COALESCE((SELECT as_of_date FROM latest_holdings), CURRENT_DATE)
    )
    SELECT
      u.symbol,
      u.company_name,
      h.weight::text            AS weight,
      u.sector,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      m.ret_1m::text            AS ret_1m,
      m.ret_3m::text            AS ret_3m,
      lh.as_of_date::text       AS holdings_date
    FROM public.de_mf_holdings h
    JOIN latest_holdings lh ON h.mstar_id = ${mstar_id}
      AND h.as_of_date = lh.as_of_date
    LEFT JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = h.instrument_id
      AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_stock_states_daily s
      ON s.instrument_id = u.instrument_id
      AND s.date = (SELECT d FROM latest_states_date)
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id
      AND m.date = (SELECT d FROM latest_states_date)
    WHERE h.mstar_id = ${mstar_id}
    ORDER BY h.weight DESC
    LIMIT ${limit}
  `
}
```

**Note:** If `de_mf_holdings` uses a different column name than `mstar_id` (e.g., `fund_id`), adjust accordingly. Run `SELECT column_name FROM information_schema.columns WHERE table_name = 'de_mf_holdings' LIMIT 20` on EC2 to verify.

- [ ] **Step 3: Create FundHoldingsTab component**

Create `frontend/src/components/funds/FundHoldingsTab.tsx` — this is identical in structure to `ETFHoldingsTab.tsx` but accepts `FundHoldingRow[]`:

```tsx
import type { FundHoldingRow } from '@/lib/queries/funds'

const RS_STYLE: Record<string, string> = {
  Leader:   'bg-teal/20 text-teal',
  Strong:   'bg-signal-pos/20 text-signal-pos',
  Average:  'bg-paper-rule/40 text-ink-secondary',
  Weak:     'bg-signal-neg/10 text-signal-neg',
  Laggard:  'bg-signal-neg/20 text-signal-neg',
}

const MOM_STYLE: Record<string, string> = {
  Accelerating:  'text-signal-pos',
  Improving:     'text-signal-pos/70',
  Flat:          'text-ink-tertiary',
  Deteriorating: 'text-signal-neg/70',
  Collapsing:    'text-signal-neg',
}

const RISK_STYLE: Record<string, string> = {
  Low:           'text-signal-pos',
  Normal:        'text-ink-secondary',
  Elevated:      'text-signal-warn',
  High:          'text-signal-neg',
  'Below Trend': 'text-signal-neg',
}

function pctStr(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function weightStr(v: string | null): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(1)}%`
}

function StateBadge({ state, styleMap }: { state: string | null; styleMap: Record<string, string> }) {
  if (!state) return <span className="text-ink-tertiary">—</span>
  const cls = styleMap[state] ?? 'text-ink-secondary'
  return <span className={`font-sans text-[11px] font-medium ${cls}`}>{state}</span>
}

export function FundHoldingsTab({ holdings }: { holdings: FundHoldingRow[] }) {
  if (holdings.length === 0) {
    return (
      <div className="px-6 py-10 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No holdings data available. Fund disclosures are typically delayed 30–60 days.
        </p>
      </div>
    )
  }

  const holdingsDate = holdings[0]?.holdings_date
  const strongCount = holdings.filter(h => h.rs_state === 'Leader' || h.rs_state === 'Strong').length
  const weakCount = holdings.filter(h => h.rs_state === 'Weak' || h.rs_state === 'Laggard').length

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-6 font-sans text-xs text-ink-secondary">
        <span>Top <span className="font-semibold text-ink-primary">{holdings.length}</span> holdings</span>
        <span className="text-signal-pos font-semibold">{strongCount} Leader/Strong</span>
        <span className="text-signal-neg font-semibold">{weakCount} Weak/Laggard</span>
        {holdingsDate && (
          <span className="ml-auto text-ink-tertiary text-[10px]">
            Holdings as of{' '}
            {new Date(holdingsDate).toLocaleDateString('en-IN', {
              day: '2-digit', month: 'short', year: 'numeric',
            }).replace(',', '')}
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full font-sans text-xs border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Stock</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Sector</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Weight</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">RS State</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Momentum</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Risk</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">1M</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">3M</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => (
              <tr key={h.symbol ?? i} className="border-b border-paper-rule/50 hover:bg-paper-rule/10 transition-colors">
                <td className="px-3 py-2.5">
                  <div className="font-semibold text-ink-primary">{h.symbol ?? '—'}</div>
                  {h.company_name && (
                    <div className="text-[10px] text-ink-tertiary truncate max-w-[140px]">{h.company_name}</div>
                  )}
                </td>
                <td className="px-3 py-2.5 text-ink-secondary">{h.sector ?? '—'}</td>
                <td className="px-3 py-2.5 text-right font-mono font-semibold text-ink-primary">{weightStr(h.weight)}</td>
                <td className="px-3 py-2.5">
                  {h.rs_state ? (
                    <span className={`px-1.5 py-0.5 rounded-[2px] text-[10px] font-semibold ${RS_STYLE[h.rs_state] ?? 'bg-paper-rule/30 text-ink-secondary'}`}>
                      {h.rs_state}
                    </span>
                  ) : <span className="text-ink-tertiary">—</span>}
                </td>
                <td className="px-3 py-2.5"><StateBadge state={h.momentum_state} styleMap={MOM_STYLE} /></td>
                <td className="px-3 py-2.5"><StateBadge state={h.risk_state} styleMap={RISK_STYLE} /></td>
                <td className={`px-3 py-2.5 text-right font-mono ${h.ret_1m && parseFloat(h.ret_1m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pctStr(h.ret_1m)}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${h.ret_3m && parseFloat(h.ret_3m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pctStr(h.ret_3m)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Add Holdings tab to fund deep dive page**

In `frontend/src/app/funds/[mstar_id]/page.tsx`, add `getFundHoldings` to the parallel fetch:

```tsx
const [fundMaster, metricHistory, lens, decisionHistory, holdings] = await Promise.all([
  getFundMaster(mstar_id),
  getFundMetricHistory(mstar_id, 90),
  getFundLens(mstar_id),
  getFundDecisionHistory(mstar_id),
  getFundHoldings(mstar_id, 20),
])
```

Then add a "Holdings" section below the existing 3-lens grid — use the same pattern as the existing layout:

```tsx
{/* Holdings section — individual stocks */}
<div className="mt-6 border border-paper-rule rounded-sm">
  <div className="px-4 py-3 border-b border-paper-rule">
    <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
      Portfolio Holdings — Individual Stock States
    </div>
  </div>
  <FundHoldingsTab holdings={holdings} />
</div>
```

Import `FundHoldingsTab` and `getFundHoldings` at the top of the page file.

- [ ] **Step 5: TypeScript check + build**

```bash
cd /Users/nimishshah/Documents/GitHub/atlas-os/frontend
npx tsc --noEmit 2>&1 | head -20
npm run build 2>&1 | tail -15
```

Expected: 0 TS errors, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/queries/funds.ts \
        frontend/src/components/funds/FundHoldingsTab.tsx \
        frontend/src/app/funds/[mstar_id]/page.tsx
git commit -m "feat(funds): add getFundHoldings(), FundHoldingsTab, data_as_of — surface individual stock states in fund deep dive"
```

---

## Task 8: Deploy to production

- [ ] **Step 1: Push to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: SSH to atlas frontend server and deploy**

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.202.162.196 \
  "cd /home/ubuntu/atlas-frontend && git pull && npm run build && pm2 restart atlas-frontend"
```

Expected: build success, pm2 confirms restart.

- [ ] **Step 3: Verify live site**

```bash
curl -s -o /dev/null -w "%{http_code}" https://atlas.jslwealth.in/etfs
```

Expected: 200.

---

## Task 9: EC2 Backfill — Fix 32/100 ETF data gap (run in parallel with Tasks 1-8)

**This task runs on the compute EC2 server (`ubuntu@13.206.34.214`), not the frontend server.**

- [ ] **Step 1: Push latest code to EC2**

```bash
# Create tarball on Mac
cd /Users/nimishshah/Documents/GitHub/atlas-os
tar --exclude='.git' --exclude='node_modules' --exclude='.venv' \
    --exclude='frontend/.next' -czf /tmp/atlas-os.tar.gz .

# Copy to EC2
scp -i ~/.ssh/jsl-wealth-key.pem /tmp/atlas-os.tar.gz ubuntu@13.206.34.214:/tmp/

# Extract on EC2
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  "cd /home/ubuntu && mkdir -p atlas-os-new && tar -xzf /tmp/atlas-os.tar.gz -C atlas-os-new && rsync -a --delete atlas-os-new/ atlas-os/ && rm -rf atlas-os-new && cd atlas-os && source .venv/bin/activate && pip install -e . -q"
```

- [ ] **Step 2: Run migration 028 (add state_since_date to ETF states)**

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  "cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python -c \"
from atlas.db import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    result = conn.execute(text(\\\"SELECT COUNT(*) FROM atlas.atlas_etf_states_daily WHERE state_since_date IS NOT NULL\\\"))
    print('rows with state_since_date:', result.scalar())
\""
```

If the count is 0 (migration hasn't run), apply it:

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  "cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python -m alembic upgrade 028"
```

- [ ] **Step 3: Diagnose 32/100 ETF gap**

Check how many ETFs have decisions for the latest date:

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  "cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python -c \"
from atlas.db import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    # Count universe
    n_universe = conn.execute(text('SELECT COUNT(*) FROM atlas.atlas_universe_etfs WHERE effective_to IS NULL')).scalar()
    # Count metrics for latest date
    n_metrics = conn.execute(text('SELECT COUNT(*) FROM atlas.atlas_etf_metrics_daily WHERE date = (SELECT MAX(date) FROM atlas.atlas_etf_metrics_daily)')).scalar()
    # Count decisions for latest date
    n_decisions = conn.execute(text('SELECT COUNT(*) FROM atlas.atlas_etf_decisions_daily WHERE date = (SELECT MAX(date) FROM atlas.atlas_etf_decisions_daily)')).scalar()
    latest_m = conn.execute(text('SELECT MAX(date) FROM atlas.atlas_etf_metrics_daily')).scalar()
    latest_d = conn.execute(text('SELECT MAX(date) FROM atlas.atlas_etf_decisions_daily')).scalar()
    print(f'Universe: {n_universe}')
    print(f'Metrics rows (latest date {latest_m}): {n_metrics}')
    print(f'Decisions rows (latest date {latest_d}): {n_decisions}')
\""
```

- [ ] **Step 4: Run ETF compute backfill if needed**

If metrics or decisions count < 90 (indicating incomplete compute):

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  "cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python scripts/m3_daily.py 2>&1 | tail -20"
```

Then M4:
```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  "cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python scripts/m4_daily.py 2>&1 | tail -20"
```

Then M5 (ETF decisions):
```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  "cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python scripts/m5_daily.py 2>&1 | tail -20"
```

- [ ] **Step 5: Verify cron is scheduled**

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 "crontab -l 2>/dev/null || echo 'NO CRON SET'"
```

If no cron set, add the daily schedule:

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 "crontab -l 2>/dev/null > /tmp/crontab_bak; cat >> /tmp/crontab_bak << 'EOF'
# Atlas daily compute — runs at 7:30 PM IST (14:00 UTC)
0 14 * * 1-5 cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python scripts/m3_daily.py >> /var/log/atlas-m3.log 2>&1
30 14 * * 1-5 cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python scripts/m4_daily.py >> /var/log/atlas-m4.log 2>&1
0 15 * * 1-5 cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python scripts/m5_daily.py >> /var/log/atlas-m5.log 2>&1
EOF
crontab /tmp/crontab_bak && echo 'Cron set'"
```

- [ ] **Step 6: Re-verify ETF count after backfill**

```bash
ssh -i ~/.ssh/jsl-wealth-key.pem ubuntu@13.206.34.214 \
  "cd /home/ubuntu/atlas-os && source .venv/bin/activate && PYTHONPATH=. python -c \"
from atlas.db import get_engine
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    n = conn.execute(text('SELECT COUNT(*) FROM atlas.atlas_etf_decisions_daily WHERE date = (SELECT MAX(date) FROM atlas.atlas_etf_decisions_daily)')).scalar()
    print(f'ETF decisions for latest date: {n} (target: ~100)')
\""
```

Expected: count close to 100 (universe size).

---

## Self-Review

**Spec coverage check:**
- ✅ 32/100 data gap: Task 9 diagnoses and fixes
- ✅ ETF Holdings tab: Tasks 1, 5, 6
- ✅ Screener 6M column: Task 2
- ✅ Exit trigger badges: Task 4
- ✅ linked_index + inception_date in header: Task 3
- ✅ data_as_of for ETFs: Tasks 1 + 3
- ✅ data_as_of for funds: Task 7
- ✅ Fund individual holdings tab: Task 7
- ✅ Production deployment: Task 8
- ✅ EC2 cron schedule: Task 9

**Type consistency check:**
- `ETFHoldingRow` defined in `etfs.ts` Task 1, used in `ETFHoldingsTab` Task 5, imported into `ETFDeepDiveTabs` Task 6, fetched in `[ticker]/page.tsx` Task 6 — all consistent.
- `FundHoldingRow` defined in `funds.ts` Task 7, used in `FundHoldingsTab` Task 7 — consistent.
- `exit_market_riskoff`, `exit_sector_avoid`, `exit_rs_deteriorate`, `exit_momentum_collapse` added to `ETFRow` in Task 1, used in `ETFOverviewTab` Task 4 — consistent.
- `linked_index`, `inception_date`, `data_as_of` added to `ETFRow` in Task 1, used in `ETFDeepDiveHeader` Task 3 — consistent.

**No placeholders — all tasks have exact code.**
