# Stocks Page Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the Stock Universe page — wire up the bubble chart, add multi-MA breadth bands with clickable filters, full-width table with pagination and Gate legend, remove Deploy %, fix sort nulls, restructure layout to eliminate the squishing side panel, and flatten the deep dive page into a single scrolling view.

**Architecture:** State for the MA breadth filter is lifted into a new `StocksClientShell` client component wrapping the interactive sections; the server `page.tsx` passes pre-fetched data down. The bubble chart, breadth panel, intelligence panel, and screener all become children of that shell. Deep dive page drops `StockTabs` entirely and renders all content in one scroll.

**Tech Stack:** Next.js 15 App Router, React 19, Recharts, Tailwind CSS, Postgres via `postgres` tagged-template driver

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `frontend/src/lib/queries/stocks.ts` | Add `avg_volume_20`, `ret_12m`, `realized_vol_63`, `above_50d_ma`, `above_200d_ma` to query + types |
| Create | `frontend/src/components/stocks/StocksClientShell.tsx` | Client wrapper; holds `maFilter` + `page` state; renders breadth → bubble → intelligence → screener |
| Modify | `frontend/src/app/stocks/page.tsx` | Slim server shell; delegates layout to `StocksClientShell` |
| Modify | `frontend/src/components/stocks/StockBreadthPanel.tsx` | Multi-MA band + full index composition band; emits `onMaFilter` |
| Modify | `frontend/src/components/stocks/StockScreener.tsx` | Remove Deploy %, fix sort nulls, Gate legend, more optional cols, pagination, accept `maFilter` prop |
| Modify | `frontend/src/components/stocks/StockIntelligencePanel.tsx` | Convert from vertical sidebar to horizontal 3-column row |
| Modify | `frontend/src/app/stocks/[symbol]/page.tsx` | Remove `StockTabs`; render flat scrolling page directly |
| Delete | `frontend/src/components/stocks/StockTabs.tsx` | No longer needed |
| Modify | `frontend/src/components/stocks/StockOverviewTab.tsx` | Rename content kept for re-use; turns into inline section |

---

## Task 1: Extend `getAllStocks()` query — add bubble chart + MA fields

**Files:**
- Modify: `frontend/src/lib/queries/stocks.ts`

### What to add to the query

The bubble chart (`StockBubbleChart`) needs `avg_volume_20`, `ret_12m`, and `realized_vol_63`. These columns all exist in `atlas_stock_metrics_daily`. Additionally we derive:
- `above_200d_ma` = `extension_pct > 0` (extension_pct = (close − ema_200) / ema_200, so positive means close > ema_200)
- `above_50d_ma` = `ema_200_stock * (1 + extension_pct) > ema_50_stock`

- [ ] **Step 1: Update `StockRowWithSector` type and `getAllStocks()` SQL**

Replace `frontend/src/lib/queries/stocks.ts` lines 5–93:

```typescript
export type StockRowWithSector = StockRow & {
  sector: string
  above_30w_ma: boolean | null
  above_50d_ma: boolean | null
  above_200d_ma: boolean | null
  ret_1w: string | null
  ret_12m: string | null
  extension_pct: string | null
  vol_63: string | null
  realized_vol_63: string | null   // same value as vol_63; needed by StockBubbleChart
  avg_volume_20: string | null
  drawdown: string | null
  days_in_state: number | null
  history_gate_pass: boolean | null
  liquidity_gate_pass: boolean | null
  stage1_base_qualifies: boolean | null
  strength_gate: boolean | null
  direction_gate: boolean | null
}

// FullStockRow is now the same as StockRowWithSector (all fields included)
export type FullStockRow = StockRowWithSector
```

Update the SELECT inside `getAllStocks()` to include the new fields (add after the existing `m.realized_vol_63::text AS vol_63` line):

```sql
      m.realized_vol_63::text              AS vol_63,
      m.realized_vol_63::text              AS realized_vol_63,
      m.avg_volume_20::text                AS avg_volume_20,
      m.ret_12m::text                      AS ret_12m,
      (m.extension_pct > 0)                AS above_200d_ma,
      (
        m.ema_200_stock IS NOT NULL
        AND m.extension_pct IS NOT NULL
        AND m.ema_50_stock IS NOT NULL
        AND m.ema_200_stock * (1 + m.extension_pct) > m.ema_50_stock
      )                                    AS above_50d_ma,
```

Also add `m.ema_50_stock` to the SELECT (not exposed in type, just used for the derived column — Postgres handles this inline).

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -40
```

Expected: zero errors referencing `stocks.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/queries/stocks.ts
git commit -m "feat(stocks): add avg_volume_20, ret_12m, above_50d_ma, above_200d_ma to query"
```

---

## Task 2: Fix sort null bug + add market cap rank sort key

**Files:**
- Modify: `frontend/src/components/stocks/StockScreener.tsx:174–191`

The current sort pushes null values to the *top* when sorting descending (the `asc ? cmp : -cmp` flip inverts null's +1 into -1, bringing it first). Fix: handle nulls outside the asc/desc flip.

- [ ] **Step 1: Replace sort comparator**

Find this block in `StockScreener.tsx` (approx line 174):

```typescript
    return [...result].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'symbol') cmp = a.symbol.localeCompare(b.symbol)
      else if (sortKey === 'sector') cmp = a.sector.localeCompare(b.sector)
      else if (sortKey === 'rs_state') cmp = stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state)
      else if (sortKey === 'momentum_state') cmp = stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state)
      else if (sortKey === 'risk_state') cmp = stateRank(RISK_ORDER, a.risk_state) - stateRank(RISK_ORDER, b.risk_state)
      else if (sortKey === 'volume_state') cmp = stateRank(VOL_ORDER, a.volume_state) - stateRank(VOL_ORDER, b.volume_state)
      else {
        const av = a[sortKey as keyof typeof a] != null ? parseFloat(a[sortKey as keyof typeof a] as string) : null
        const bv = b[sortKey as keyof typeof b] != null ? parseFloat(b[sortKey as keyof typeof b] as string) : null
        if (av == null && bv == null) cmp = 0
        else if (av == null) cmp = 1
        else if (bv == null) cmp = -1
        else cmp = av - bv
      }
      return asc ? cmp : -cmp
    })
```

Replace with:

```typescript
    return [...result].sort((a, b) => {
      // Nulls always last regardless of sort direction.
      function numVal(row: StockRowWithSector, key: string): number | null {
        const v = (row as unknown as Record<string, unknown>)[key]
        if (v == null) return null
        const n = parseFloat(v as string)
        return Number.isFinite(n) ? n : null
      }

      if (sortKey === 'symbol') {
        const cmp = a.symbol.localeCompare(b.symbol)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'sector') {
        const cmp = a.sector.localeCompare(b.sector)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'rs_state') {
        const cmp = stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'momentum_state') {
        const cmp = stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'risk_state') {
        const cmp = stateRank(RISK_ORDER, a.risk_state) - stateRank(RISK_ORDER, b.risk_state)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'volume_state') {
        const cmp = stateRank(VOL_ORDER, a.volume_state) - stateRank(VOL_ORDER, b.volume_state)
        return asc ? cmp : -cmp
      }
      // Numeric sort — nulls always last
      const av = numVal(a, sortKey)
      const bv = numVal(b, sortKey)
      if (av == null && bv == null) return 0
      if (av == null) return 1   // null a → always after non-null b
      if (bv == null) return -1  // null b → always after non-null a
      const cmp = av - bv
      return asc ? cmp : -cmp
    })
```

- [ ] **Step 2: Add `cap_rank` sort key + default sort**

Add `'cap_rank'` to the `SortKey` union type:

```typescript
type SortKey =
  | 'symbol' | 'sector' | 'rs_pctile_3m'
  | 'ret_1m' | 'ret_3m' | 'ret_6m'
  | 'rs_state' | 'momentum_state' | 'risk_state' | 'volume_state'
  | 'cap_rank'
```

Add a helper before the sort block:

```typescript
function capRank(s: StockRowWithSector): number {
  if (s.in_nifty_50) return 1
  if (s.in_nifty_100) return 2
  if (s.in_nifty_500) return 3
  return 4
}
```

Add the `cap_rank` case to the sort comparator (before the numeric fallthrough):

```typescript
      if (sortKey === 'cap_rank') {
        const cmp = capRank(a) - capRank(b)
        return asc ? cmp : -cmp
      }
```

Change the default `useState` for `sortKey` and `asc`:

```typescript
  const [sortKey, setSortKey] = useState<SortKey>('cap_rank')
  const [asc, setAsc] = useState(true)
```

Add a `Th` for Cap Rank in the table header (next to Symbol):

```tsx
<Th label="Cap" k="cap_rank" />
```

- [ ] **Step 3: Verify no TS errors**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "StockScreener\|sort\|SortKey" | head -20
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/stocks/StockScreener.tsx
git commit -m "fix(stocks): nulls-last sort, default cap rank order"
```

---

## Task 3: Table improvements — remove Deploy %, fix Gate legend, add optional columns

**Files:**
- Modify: `frontend/src/components/stocks/StockScreener.tsx`

- [ ] **Step 1: Remove Deploy % column**

In `StockScreener.tsx`:

1. Remove the `Th label="Deploy %" k="position_size_pct"` header cell.
2. Remove the corresponding `<td>` with `<PosSizeBar value={row.position_size_pct} />`.
3. Update `ALWAYS_VISIBLE_COL_COUNT` from `11` to `10`.
4. Remove `'position_size_pct'` from the `SortKey` union type.
5. Remove `PosSizeBar` from the import of `stock-formatters`.

- [ ] **Step 2: Make 1W visible by default**

In `OPTIONAL_COLS`, change `ret_1w` to `defaultVisible: true`:

```typescript
const OPTIONAL_COLS: ColumnDef[] = [
  { key: 'ret_1w',        label: '1W',       defaultVisible: true },
  { key: 'ret_6m',        label: '6M',        defaultVisible: true },
  { key: 'extension_pct', label: 'Ext %',     defaultVisible: false },
  { key: 'vol_63',        label: 'Vol (63D)', defaultVisible: false },
  { key: 'drawdown',      label: 'Drawdown',  defaultVisible: false },
  { key: 'days_in_state', label: 'Days',      defaultVisible: false },
]
```

- [ ] **Step 3: Replace GateDots with a version that has a legend popover**

Replace the `GateDot` + `GateDots` functions and the Gates `<th>` header with:

```typescript
const GATE_LEGEND = [
  { key: 'H', label: 'History', desc: 'Stock has ≥6M of price history in our universe' },
  { key: 'L', label: 'Liquidity', desc: 'Avg daily value traded meets minimum threshold' },
  { key: 'W', label: 'Weinstein', desc: 'Price is in Weinstein Stage 2 (above rising 30W MA)' },
  { key: 'S', label: 'Strength', desc: 'RS State is Leader or Strong' },
  { key: 'D', label: 'Direction', desc: 'Momentum is Accelerating or Improving' },
]

function GateDot({ value }: { value: boolean | null }) {
  const color = value === true
    ? 'bg-teal'
    : value === false ? 'bg-signal-neg' : 'bg-paper-rule'
  return <span className={`w-1.5 h-1.5 rounded-full ${color} shrink-0`} />
}

function GateDots({ row }: { row: StockRowWithSector }) {
  const vals = [
    optBool(row, 'history_gate_pass'),
    optBool(row, 'liquidity_gate_pass'),
    optBool(row, 'weinstein_gate_pass'),
    optBool(row, 'strength_gate'),
    optBool(row, 'direction_gate'),
  ]
  const passCount = vals.filter(v => v === true).length
  return (
    <span
      className="inline-flex items-center gap-0.5"
      title={vals.map((v, i) => `${GATE_LEGEND[i].key}: ${v === true ? '✓' : v === false ? '✗' : '?'} ${GATE_LEGEND[i].desc}`).join('\n')}
    >
      {vals.map((v, i) => <GateDot key={i} value={v} />)}
      <span className="ml-1 font-mono text-[10px] text-ink-tertiary tabular-nums">{passCount}/5</span>
    </span>
  )
}
```

For the `PlainTh` Gates column header, add an info tooltip with the legend:

```tsx
<th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap text-ink-tertiary">
  <span className="inline-flex items-center gap-1">
    Gates
    <span
      className="cursor-help text-ink-tertiary/60 hover:text-ink-secondary"
      title={GATE_LEGEND.map(g => `${g.key} = ${g.label}: ${g.desc}`).join('\n')}
    >
      ⓘ
    </span>
  </span>
</th>
```

- [ ] **Step 4: Verify TS + spot-check render**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "screener\|GateDot" | head -20
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/stocks/StockScreener.tsx
git commit -m "feat(stocks): remove Deploy col, Gates legend, 1W+6M default on"
```

---

## Task 4: Add pagination (50 per page)

**Files:**
- Modify: `frontend/src/components/stocks/StockScreener.tsx`

The `StockScreener` gets a `maFilter` prop from the parent shell (Task 6), but pagination is internal state.

- [ ] **Step 1: Add page state and accept `maFilter` prop**

At the top of `StockScreener`, add the prop to the component signature and add page state:

```typescript
export function StockScreener({
  stocks,
  maFilter,
}: {
  stocks: StockRowWithSector[]
  maFilter?: 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null
}) {
  // ... existing state ...
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 50
```

- [ ] **Step 2: Apply `maFilter` to the `filtered` memo + reset page on filter change**

At the start of the `filtered = useMemo(...)` block, add the maFilter clause:

```typescript
  const filtered = useMemo(() => {
    // reset to page 1 whenever any filter changes (page is excluded from deps)
    let result = stocks

    // MA filter from breadth panel
    if (maFilter === 'above_30w_ma') result = result.filter(s => s.above_30w_ma === true)
    else if (maFilter === 'above_50d_ma') result = result.filter(s => optBool(s, 'above_50d_ma') === true)
    else if (maFilter === 'above_200d_ma') result = result.filter(s => optBool(s, 'above_200d_ma') === true)

    // ... rest of existing filter logic (chip, sectorFilter, search, sort) ...
```

Add `maFilter` to the `useMemo` dependency array.

Also reset page when filters change — add a `useEffect`:

```typescript
  useEffect(() => {
    setPage(1)
  }, [chip, sectorFilter, search, sortKey, asc, maFilter])
```

- [ ] **Step 3: Slice filtered for display**

After the `filtered` memo, add:

```typescript
  const pagedRows = useMemo(() => filtered.slice(0, page * PAGE_SIZE), [filtered, page])
  const hasMore = pagedRows.length < filtered.length
```

Replace `filtered.map(...)` in the table body with `pagedRows.map(...)`.

- [ ] **Step 4: Add "Load 50 more" row at bottom of table**

After `</tbody>`, inside the scrollable wrapper, add:

```tsx
      {hasMore && (
        <div className="px-4 py-3 border-t border-paper-rule text-center">
          <button
            type="button"
            onClick={() => setPage(p => p + 1)}
            className="font-sans text-xs text-teal hover:underline"
          >
            Load {Math.min(PAGE_SIZE, filtered.length - pagedRows.length)} more
            <span className="text-ink-tertiary ml-1">
              ({pagedRows.length} of {filtered.length})
            </span>
          </button>
        </div>
      )}
```

Also update the count badge in controls:

```tsx
<span className="font-sans text-xs text-ink-tertiary whitespace-nowrap">
  {pagedRows.length} of {filtered.length} shown ({stocks.length} total)
</span>
```

- [ ] **Step 5: Verify TS**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "screener\|page\|maFilter" | head -20
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/stocks/StockScreener.tsx
git commit -m "feat(stocks): 50-per-page pagination + maFilter prop"
```

---

## Task 5: Overhaul `StockBreadthPanel` — multi-MA + full composition

**Files:**
- Modify: `frontend/src/components/stocks/StockBreadthPanel.tsx`

The panel becomes two visual bands:
1. **MA Band** — 30W, 50D, 200D MA counts with clickable filter
2. **Composition Band** — N50 / N100 / N500 / All with 100% stacked bar across all RS states

The component now accepts `onMaFilter` callback and `activeMaFilter`.

- [ ] **Step 1: Rewrite `StockBreadthPanel.tsx` in full**

```typescript
import type { StockRowWithSector } from '@/lib/queries/stocks'

type MaFilter = 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null

const RS_STATES = ['Leader', 'Strong', 'Emerging', 'Consolidating', 'Average', 'Weak', 'Laggard'] as const
const RS_COLORS: Record<string, string> = {
  Leader:        '#2F6B43',
  Strong:        '#4CAF78',
  Emerging:      '#d97706',
  Consolidating: '#1D9E75',
  Average:       '#94a3b8',
  Weak:          '#ef6644',
  Laggard:       '#B0492C',
}

const MOM_STATES = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing'] as const
const MOM_COLORS: Record<string, string> = {
  Accelerating:  '#2F6B43',
  Improving:     '#4CAF78',
  Flat:          '#94a3b8',
  Deteriorating: '#ef6644',
  Collapsing:    '#B0492C',
}

function barColor(pct: number) {
  return pct >= 0.6 ? '#2F6B43' : pct >= 0.4 ? '#f59e0b' : '#ef4444'
}

type OptBool = (s: StockRowWithSector, key: string) => boolean
function getBool(s: StockRowWithSector, key: string): boolean {
  return (s as unknown as Record<string, unknown>)[key] === true
}

function MaTile({
  label,
  count,
  total,
  filterKey,
  active,
  onClick,
}: {
  label: string
  count: number
  total: number
  filterKey: MaFilter
  active: boolean
  onClick: (k: MaFilter) => void
}) {
  const pct = total > 0 ? count / total : 0
  const color = barColor(pct)
  return (
    <button
      type="button"
      onClick={() => onClick(active ? null : filterKey)}
      className={`flex flex-col gap-1.5 px-4 py-2.5 border rounded-sm min-w-[160px] text-left transition-colors ${
        active
          ? 'border-teal bg-teal/5'
          : 'border-paper-rule bg-paper hover:bg-paper-rule/20'
      }`}
    >
      <div className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
        {label}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-lg font-semibold text-ink-primary tabular-nums">{count}</span>
        <span className="font-sans text-xs text-ink-tertiary">of {total}</span>
      </div>
      <div className="w-full h-1 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.round(pct * 100)}%`, background: color }} />
      </div>
      <div className="font-mono text-[10px] tabular-nums" style={{ color }}>
        {Math.round(pct * 100)}%{active && ' · active filter'}
      </div>
    </button>
  )
}

function CompositionBar({
  label,
  arr,
}: {
  label: string
  arr: StockRowWithSector[]
}) {
  const n = arr.length
  if (n === 0) return null
  const rsCounts = RS_STATES.map(s => ({ state: s, count: arr.filter(r => r.rs_state === s).length }))

  return (
    <div className="flex flex-col gap-1.5 min-w-[120px]">
      <div className="font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
        {label}
        <span className="font-normal normal-case tracking-normal ml-1 text-ink-tertiary/60">({n})</span>
      </div>
      {/* Stacked 100% bar */}
      <div className="flex h-3 rounded-sm overflow-hidden w-full" title={rsCounts.map(r => `${r.state}: ${r.count}`).join(' · ')}>
        {rsCounts.filter(r => r.count > 0).map(r => (
          <div
            key={r.state}
            className="h-full"
            style={{ width: `${(r.count / n) * 100}%`, background: RS_COLORS[r.state] }}
            title={`${r.state}: ${r.count} (${Math.round((r.count / n) * 100)}%)`}
          />
        ))}
      </div>
      {/* Top 2 RS states labels */}
      <div className="space-y-0.5">
        {rsCounts
          .filter(r => r.count > 0)
          .slice(0, 3)
          .map(r => (
            <div key={r.state} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary">
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: RS_COLORS[r.state] }} />
                {r.state}
              </span>
              <span className="font-mono text-[10px] tabular-nums text-ink-secondary">
                {Math.round((r.count / n) * 100)}%
              </span>
            </div>
          ))}
      </div>
    </div>
  )
}

export function StockBreadthPanel({
  stocks,
  activeMaFilter,
  onMaFilter,
}: {
  stocks: StockRowWithSector[]
  activeMaFilter: MaFilter
  onMaFilter: (f: MaFilter) => void
}) {
  const total = stocks.length
  const above30w = stocks.filter(s => s.above_30w_ma === true).length
  const above50d  = stocks.filter(s => getBool(s, 'above_50d_ma')).length
  const above200d = stocks.filter(s => getBool(s, 'above_200d_ma')).length

  const n50  = stocks.filter(s => s.in_nifty_50)
  const n100 = stocks.filter(s => s.in_nifty_100)
  const n500 = stocks.filter(s => s.in_nifty_500)

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      {/* Band 1: MA metrics */}
      <div className="px-4 py-3 border-b border-paper-rule">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
          Market Breadth — Moving Average Participation
          {activeMaFilter && (
            <button
              type="button"
              onClick={() => onMaFilter(null)}
              className="ml-3 text-teal normal-case tracking-normal hover:underline"
            >
              Clear filter
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          <MaTile
            label="Above 30-Week MA"
            count={above30w}
            total={total}
            filterKey="above_30w_ma"
            active={activeMaFilter === 'above_30w_ma'}
            onClick={onMaFilter}
          />
          <MaTile
            label="Above 50-Day EMA"
            count={above50d}
            total={total}
            filterKey="above_50d_ma"
            active={activeMaFilter === 'above_50d_ma'}
            onClick={onMaFilter}
          />
          <MaTile
            label="Above 200-Day EMA"
            count={above200d}
            total={total}
            filterKey="above_200d_ma"
            active={activeMaFilter === 'above_200d_ma'}
            onClick={onMaFilter}
          />
        </div>
      </div>

      {/* Band 2: Index composition */}
      <div className="px-4 py-3">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
          RS State Composition by Index
        </div>
        <div className="flex flex-wrap gap-6">
          <CompositionBar label="Nifty 50"  arr={n50} />
          <CompositionBar label="Nifty 100" arr={n100} />
          <CompositionBar label="Nifty 500" arr={n500} />
          <CompositionBar label="All"       arr={stocks} />
        </div>
        {/* Legend */}
        <div className="flex flex-wrap gap-3 mt-3 pt-2 border-t border-paper-rule/40">
          {RS_STATES.map(s => (
            <span key={s} className="flex items-center gap-1 font-sans text-[10px] text-ink-tertiary">
              <span className="w-2 h-2 rounded-full" style={{ background: RS_COLORS[s] }} />
              {s}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TS**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "BreadthPanel\|MaFilter\|MaTile" | head -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/stocks/StockBreadthPanel.tsx
git commit -m "feat(stocks): multi-MA breadth tiles + full RS composition band"
```

---

## Task 6: Convert `StockIntelligencePanel` to horizontal layout

**Files:**
- Modify: `frontend/src/components/stocks/StockIntelligencePanel.tsx`

Currently renders as a vertical sidebar (360px). Now renders as a full-width horizontal 3-column row: RS Distribution | Momentum | Commentary.

- [ ] **Step 1: Rewrite the return JSX**

Replace the `return (...)` block (lines 68–92) with:

```tsx
  return (
    <div className="border border-paper-rule rounded-sm bg-paper px-5 py-4">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
        Stock Intelligence
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* RS Distribution */}
        <div className="space-y-1.5">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
            RS Distribution
          </div>
          {RS_STATES.map(s => (
            <DistBar key={s} label={s} count={rsCounts[s] ?? 0} total={n} color={rsStateColor(s)} />
          ))}
        </div>

        {/* Momentum Distribution */}
        <div className="space-y-1.5">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
            Momentum
          </div>
          {MOM_STATES.map(s => (
            <DistBar key={s} label={s} count={momCounts[s] ?? 0} total={n} color={MOM_COLORS[s] ?? CHART_COLORS.inkTertiary} />
          ))}
        </div>

        {/* Commentary */}
        <div className="border-t md:border-t-0 md:border-l border-paper-rule pt-3 md:pt-0 md:pl-6">
          <CommentaryBlock
            narrative={commentary.narrative}
            contextCards={commentary.contextCards}
          />
        </div>
      </div>
    </div>
  )
```

- [ ] **Step 2: Verify TS**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "IntelligencePanel" | head -10
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/stocks/StockIntelligencePanel.tsx
git commit -m "feat(stocks): intelligence panel → horizontal 3-col layout"
```

---

## Task 7: Create `StocksClientShell` + restructure `page.tsx`

**Files:**
- Create: `frontend/src/components/stocks/StocksClientShell.tsx`
- Modify: `frontend/src/app/stocks/page.tsx`

The shell holds `maFilter` state and renders: breadth → bubble → intelligence → screener (all full width).

- [ ] **Step 1: Create `StocksClientShell.tsx`**

```typescript
// allow-large: main stocks page client shell — holds maFilter state, renders all interactive sections
'use client'
import { useState } from 'react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import { StockBreadthPanel } from './StockBreadthPanel'
import { StockBubbleChart } from './StockBubbleChart'
import { StockIntelligencePanel } from './StockIntelligencePanel'
import { StockScreener } from './StockScreener'

type MaFilter = 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null

export function StocksClientShell({
  stocks,
  regimeState,
  deploymentMultiplier,
}: {
  stocks: StockRowWithSector[]
  regimeState: string
  deploymentMultiplier: number
}) {
  const [maFilter, setMaFilter] = useState<MaFilter>(null)

  return (
    <div className="flex flex-col gap-6">
      <StockBreadthPanel
        stocks={stocks}
        activeMaFilter={maFilter}
        onMaFilter={setMaFilter}
      />

      <StockBubbleChart stocks={stocks} />

      <StockIntelligencePanel
        stocks={stocks}
        regimeState={regimeState}
        deploymentMultiplier={deploymentMultiplier}
      />

      <StockScreener
        stocks={stocks}
        maFilter={maFilter}
      />
    </div>
  )
}
```

- [ ] **Step 2: Update `page.tsx`**

Replace the entire file content with:

```typescript
export const dynamic = 'force-dynamic'

import { getAllStocks } from '@/lib/queries/stocks'
import { getCurrentRegime } from '@/lib/queries/regime'
import { StocksClientShell } from '@/components/stocks/StocksClientShell'

export default async function StocksPage() {
  const [stocks, regime] = await Promise.all([
    getAllStocks(),
    getCurrentRegime(),
  ])

  if (stocks.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No stock data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const investableCount  = stocks.filter(s => s.is_investable).length
  const leaderCount      = stocks.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length
  const improvingCount   = stocks.filter(s => s.momentum_state === 'Improving' || s.momentum_state === 'Accelerating').length

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            Stock Universe
          </h1>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-teal" />
              {investableCount} Investable
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {leaderCount} Leader/Strong
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {improvingCount} Accel/Improving
            </span>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="px-6 py-6">
        <StocksClientShell
          stocks={stocks}
          regimeState={regime?.regime_state ?? 'Unknown'}
          deploymentMultiplier={parseFloat(regime?.deployment_multiplier ?? '0')}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Fix `StockBubbleChart` to accept `StockRowWithSector`**

`StockBubbleChart` currently types its prop as `FullStockRow[]`. Since `FullStockRow = StockRowWithSector` after Task 1, update the prop type:

In `frontend/src/components/stocks/StockBubbleChart.tsx` line 113, change:

```typescript
export function StockBubbleChart({ stocks }: { stocks: FullStockRow[] }) {
```
to:
```typescript
export function StockBubbleChart({ stocks }: { stocks: StockRowWithSector[] }) {
```

And update the import to use `StockRowWithSector` instead of `FullStockRow`.

- [ ] **Step 4: Verify TS compiles clean**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -40
```

Expected: zero errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/stocks/StocksClientShell.tsx \
        frontend/src/app/stocks/page.tsx \
        frontend/src/components/stocks/StockBubbleChart.tsx
git commit -m "feat(stocks): client shell wires bubble chart + full-width layout"
```

---

## Task 8: Deep dive page — flatten tabs into scrolling page

**Files:**
- Modify: `frontend/src/app/stocks/[symbol]/page.tsx`
- Modify: `frontend/src/components/stocks/StockOverviewTab.tsx`
- Modify: `frontend/src/components/stocks/StockHistoryTab.tsx`
- Delete: `frontend/src/components/stocks/StockTabs.tsx`

The deep dive page drops the Overview / History tab split. Everything renders in one continuous scroll: header → snapshot tiles → state heatmap → metric charts → returns.

- [ ] **Step 1: Update `[symbol]/page.tsx` to not use `StockTabs`**

Replace the entire file with:

```typescript
export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import { getStockBySymbol, getStockMetricHistory, getStockStateHistory } from '@/lib/queries/stocks'
import { StockDeepDiveHeader } from '@/components/stocks/StockDeepDiveHeader'
import { StockSnapshotTiles } from '@/components/stocks/StockSnapshotTiles'
import { StockDeepDiveBody } from '@/components/stocks/StockDeepDiveBody'

export default async function StockPage({
  params,
}: {
  params: Promise<{ symbol: string }>
}) {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase()
  const stock = await getStockBySymbol(symbol)
  if (!stock) notFound()

  const [metricHistory, stateHistory] = await Promise.all([
    getStockMetricHistory(stock.instrument_id, 180),
    getStockStateHistory(stock.instrument_id, 180),
  ])

  return (
    <div className="max-w-[1200px] mx-auto">
      <StockDeepDiveHeader stock={stock} />
      <StockSnapshotTiles stock={stock} />
      <StockDeepDiveBody
        stock={stock}
        metricHistory={metricHistory}
        stateHistory={stateHistory}
      />
    </div>
  )
}
```

- [ ] **Step 2: Create `StockDeepDiveBody.tsx`**

This merges the content of `StockOverviewTab` and `StockHistoryTab` into one scrolling component. The "History" tab content (state heatmap) appears immediately after the commentary cards. The "Overview" charts follow.

Create `frontend/src/components/stocks/StockDeepDiveBody.tsx`:

```typescript
import type { ReactNode } from 'react'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { MetricHistoryRow, StateHistoryRow, StockRowWithSector } from '@/lib/queries/stocks'
import {
  interpretRSPctile,
  interpretMomentumState,
  interpretWeinsteinGate,
  interpretEMARatio,
  interpret3MReturn,
} from '@/lib/stock-formatters'
import { StateHeatmap } from './StateHeatmap'
import { pct, pctColor } from '@/lib/stock-formatters'

function Commentary({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col justify-center h-full px-5 py-4 bg-paper-rule/5 border border-paper-rule/40 rounded-sm">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
        {title}
      </div>
      <div className="font-sans text-xs text-ink-secondary leading-relaxed space-y-2">
        {children}
      </div>
    </div>
  )
}

function dateStr(d: Date | string): string {
  return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10)
}

function pctStr(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function rawPct(v: string | null, digits = 0): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(digits)}`
}

function ReturnRow({ label, value }: { label: string; value: string | null }) {
  return (
    <tr className="border-b border-paper-rule last:border-0">
      <td className="py-2 pr-8 font-sans text-xs text-ink-secondary">{label}</td>
      <td className={`py-2 text-right font-mono text-xs tabular-nums font-semibold ${pctColor(value)}`}>
        {pct(value)}
      </td>
    </tr>
  )
}

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
      {children}
    </div>
  )
}

export function StockDeepDiveBody({
  stock,
  metricHistory,
  stateHistory,
}: {
  stock: StockRowWithSector
  metricHistory: MetricHistoryRow[]
  stateHistory: StateHistoryRow[]
}) {
  const rsPctileData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.rs_pctile_3m != null ? parseFloat(r.rs_pctile_3m) : null,
  }))
  const ret3mData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ret_3m != null ? parseFloat(r.ret_3m) : null,
  }))
  const emaData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ema_10_ratio != null ? parseFloat(r.ema_10_ratio) : null,
  }))
  const latest = metricHistory[metricHistory.length - 1]

  return (
    <div className="px-6 py-6 space-y-8">
      {/* Stage + Momentum summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Commentary title="Weinstein Stage">
          {interpretWeinsteinGate(stock.weinstein_gate_pass, stock.ema_10_at_20d_high)}
        </Commentary>
        <Commentary title="Momentum">
          {interpretMomentumState(stock.momentum_state)}
        </Commentary>
      </div>

      {/* State History heatmap (was behind "History" tab) */}
      <div>
        <SectionHeading>State History — 6M</SectionHeading>
        <div className="mt-3">
          <StateHeatmap history={stateHistory} />
        </div>
      </div>

      {/* Returns summary */}
      <div>
        <SectionHeading>Returns</SectionHeading>
        <table className="border-collapse mt-3">
          <tbody>
            <ReturnRow label="1 Week"   value={stock.ret_1w} />
            <ReturnRow label="1 Month"  value={stock.ret_1m} />
            <ReturnRow label="3 Months" value={stock.ret_3m} />
            <ReturnRow label="6 Months" value={stock.ret_6m} />
            <ReturnRow label="12 Months" value={stock.ret_12m} />
          </tbody>
        </table>
      </div>

      {/* Metric charts */}
      {metricHistory.length === 0 ? (
        <p className="font-sans text-xs text-ink-tertiary">No metric history available.</p>
      ) : (
        <div className="space-y-5">
          <SectionHeading>Metric History — 6M</SectionHeading>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="RS Percentile (3M)"
              description="Rank within sector peers on 3M RS. 100th = beats all peers. Below 50th = underperforms most."
              currentValue={rawPct(latest?.rs_pctile_3m)}
              isBullish={latest?.rs_pctile_3m != null ? parseFloat(latest.rs_pctile_3m) >= 0.5 : null}
              data={rsPctileData}
              refLine={0.5}
              refLabel="50%"
              variant="area"
              yFormat="pct"
            />
            <Commentary title={`RS Pctile · ${rawPct(latest?.rs_pctile_3m)}`}>
              {interpretRSPctile(latest?.rs_pctile_3m ?? null)}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="3-Month Return"
              description="Rolling 3M price return. Absolute — use RS to judge relative to market."
              currentValue={pctStr(latest?.ret_3m)}
              isBullish={latest?.ret_3m != null ? parseFloat(latest.ret_3m) >= 0 : null}
              data={ret3mData}
              refLine={0}
              refLabel="0"
              variant="area"
              yFormat="pct"
            />
            <Commentary title={`3M Return · ${pctStr(latest?.ret_3m)}`}>
              {interpret3MReturn(latest?.ret_3m ?? null)}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="Short-term Momentum (EMA10/EMA20)"
              description="Ratio of 10-day EMA to 20-day EMA. Above 1.0 = rising short-term trend."
              currentValue={latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio).toFixed(3) : '—'}
              isBullish={latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio) >= 1.0 : null}
              data={emaData}
              refLine={1.0}
              refLabel="1.0 = parity"
              variant="area"
              yFormat="ratio"
            />
            <Commentary title={`EMA Ratio · ${latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio).toFixed(3) : '—'}`}>
              {interpretEMARatio(latest?.ema_10_ratio ?? null)}
            </Commentary>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Extract `StateHeatmap` out of `StockHistoryTab` into its own file**

The `StateHeatmap` function is currently inside `StockHistoryTab.tsx`. Create `frontend/src/components/stocks/StateHeatmap.tsx` with the `StateHeatmap` function extracted from lines 52–157 of `StockHistoryTab.tsx`. Export it. Update `StockHistoryTab.tsx` to import it (or just leave `StockHistoryTab.tsx` in place as it is still valid if ever needed — just add the export).

Specifically, add to `StockHistoryTab.tsx`:

```typescript
export { StateHeatmap }
```

And in `StockDeepDiveBody.tsx` import from there:

```typescript
import { StateHeatmap } from './StockHistoryTab'
```

(No need to create a separate file — just re-export from `StockHistoryTab`.)

- [ ] **Step 4: Delete `StockTabs.tsx`**

```bash
rm frontend/src/components/stocks/StockTabs.tsx
```

- [ ] **Step 5: Verify TS**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -40
```

Expected: zero errors. Fix any import errors that arise.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/stocks/[symbol]/page.tsx \
        frontend/src/components/stocks/StockDeepDiveBody.tsx \
        frontend/src/components/stocks/StockHistoryTab.tsx
git rm frontend/src/components/stocks/StockTabs.tsx
git commit -m "feat(stocks/deep-dive): flatten tabs into single scrolling page"
```

---

## Task 9: Investigate state history empty in row-expand

**Files:**
- Modify: `frontend/src/components/stocks/StockScreener.tsx` (fallback display only if needed)
- Read-only: `frontend/src/app/api/states-compact/route.ts` (already checked — logic is fine)

The API route at `/api/states-compact?symbol=X&days=90` looks correct. Empty results are most likely a data gap: `atlas_stock_states_daily` may not have 90 days of data for all stocks (only stocks that ran through the full pipeline). The `StateJourneyCompact` already handles this gracefully with `<p>No state history</p>`.

- [ ] **Step 1: Check data availability on EC2**

SSH to EC2 and run:

```sql
SELECT COUNT(DISTINCT instrument_id), MIN(date), MAX(date)
FROM atlas.atlas_stock_states_daily;

SELECT COUNT(*)
FROM atlas.atlas_stock_states_daily
WHERE date >= CURRENT_DATE - 90
GROUP BY instrument_id
ORDER BY 1 ASC
LIMIT 10;
```

Expected: if counts are small or min date is recent, the EC2 backfill is needed.

- [ ] **Step 2: If data is present, test the API endpoint directly**

On the app server, call:

```bash
curl "http://localhost:3000/api/states-compact?symbol=HFCL&days=90"
```

If it returns `{"rows":[]}`, data gap confirmed. If it returns 500, investigate query.

- [ ] **Step 3: Improve empty state message in `StateJourneyCompact`**

In `frontend/src/components/ui/StateJourneyCompact.tsx`, replace line 96:

```typescript
  if (rows.length === 0) return <p className="text-xs text-ink-tertiary">No state history</p>
```

with:

```typescript
  if (rows.length === 0) return (
    <p className="text-xs text-ink-tertiary">
      No state history in the last {days} days — run the backfill pipeline or click to open the deep-dive.
    </p>
  )
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/StateJourneyCompact.tsx
git commit -m "fix(stocks): improve empty state message for state history"
```

---

## Self-Review Against Spec

### Spec coverage check

| Requirement | Covered by |
|---|---|
| Bubble chart missing | Task 7 — wires `StockBubbleChart` into shell |
| Multiple MA breadth metrics (30W, 50D, 200D) | Task 5 — MA tiles |
| Click MA tile to filter table | Task 5 + Task 4 — `onMaFilter` → `maFilter` prop |
| Index composition full bars (not just OW RS + Improving) | Task 5 — `CompositionBar` with all RS states |
| Layout: table full width, Intelligence moved below | Task 7 — `StocksClientShell` eliminates grid split |
| Sort blanks at top | Task 2 — nulls-last fix |
| Sort by cap rank | Task 2 — cap_rank sort key |
| Gate legend/tooltip | Task 3 — GATE_LEGEND + title attribute |
| More return columns (1W, 6M default on) | Task 3 — optional cols defaults |
| Remove Deploy % column | Task 3 |
| Pagination 50 per page | Task 4 |
| State history row expand investigation | Task 9 |
| Deep dive — no tabs, rolling page | Task 8 |
| Returns on deep dive (1W, 1M, 3M, 6M, 12M) | Task 8 — ReturnRow table includes ret_12m |
| State heatmap inline (not behind tab) | Task 8 — inline in `StockDeepDiveBody` |

### Items NOT covered (out of scope or need design review first)

- **Deploy 0% data bug on HFCL** — the `position_size_pct` column logic is in `atlas_stock_decisions_daily`; since we're removing the Deploy column entirely, this is moot.
- **More charts on deep dive** — currently 3 charts (RS Pctile, 3M Return, EMA Ratio); adding more charts (e.g. volume state history chart, risk state chart) is deferred to a future `/design-review` pass since it needs new indicator interpretations.
- **Relative returns column** — `rs_3m_nifty500` is already in the query as `rs_3m_nifty500` on `StockRow`; adding it as an optional column is a small addition to Task 3 optional cols: `{ key: 'rs_3m_nifty500', label: 'RS vs N500', defaultVisible: false }`.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-10-stocks-page-overhaul.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — Fresh subagent per task, two-stage review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`

Which approach?
