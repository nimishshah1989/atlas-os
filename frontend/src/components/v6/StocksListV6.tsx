// frontend/src/components/v6/StocksListV6.tsx
// C.15 — Stocks list: column chooser + portfolio badge + virtualization.
// Default columns (FM-critic mandate 4): own_badge ticker name sector tier
//   conviction 1d 1w 6m rs_pct ic composite action
// Optional: volatility 1m 3m 12m ema_dist drawdown
// Virtualization: @tanstack/react-virtual at >300 rows.

'use client'

import { useMemo, useState, useRef, useCallback, type CSSProperties } from 'react'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ChevronUp, ChevronDown } from 'lucide-react'

import { ColumnChooser, type ColumnDef } from '@/components/v6/ColumnChooser'
import { PortfolioBadge } from '@/components/v6/PortfolioBadge'
import { ConvictionTape } from '@/components/v6/ConvictionTape'
import { useColumnPreferences } from '@/lib/v6/useColumnPreferences'
import { signedPct } from '@/lib/v6/decimal'
import type { StockV6Row } from '@/lib/queries/v6/stocks'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ── Types ────────────────────────────────────────────────────────────────────

type ActionFilter = 'ALL' | 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'
type TierFilter = 'ALL' | 'Large' | 'Mid' | 'Small'

type SortKey =
  | 'symbol' | 'name' | 'sector' | 'tier'
  | 'ret_1d' | 'ret_1w' | 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_12m'
  | 'rs_pct' | 'ic' | 'composite'

export type StocksListV6Column =
  | 'own_badge' | 'ticker' | 'name' | 'sector' | 'tier' | 'conviction'
  | 'ret_1d' | 'ret_1w' | 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_12m'
  | 'rs_pct' | 'ic' | 'composite' | 'action'
  | 'volatility' | 'ema_dist' | 'drawdown'

// ── Column definitions ────────────────────────────────────────────────────────

const COLUMN_DEFS: ColumnDef<StocksListV6Column>[] = [
  { key: 'own_badge',  label: 'Held',        group: 'atlas' },
  { key: 'ticker',     label: 'Ticker',       group: 'atlas' },
  { key: 'name',       label: 'Name',         group: 'atlas' },
  { key: 'sector',     label: 'Sector',       group: 'atlas' },
  { key: 'tier',       label: 'Tier',         group: 'atlas' },
  { key: 'conviction', label: 'Conviction',   group: 'atlas' },
  { key: 'ret_1d',     label: '1d return',    group: 'returns' },
  { key: 'ret_1w',     label: '1w return',    group: 'returns' },
  { key: 'ret_1m',     label: '1m return',    group: 'returns' },
  { key: 'ret_3m',     label: '3m return',    group: 'returns' },
  { key: 'ret_6m',     label: '6m return',    group: 'returns' },
  { key: 'ret_12m',    label: '12m return',   group: 'returns' },
  { key: 'rs_pct',     label: 'RS %ile',      group: 'atlas' },
  { key: 'ic',         label: 'IC (6m)',       group: 'atlas' },
  { key: 'composite',  label: 'Composite',    group: 'atlas' },
  { key: 'action',     label: 'Action',       group: 'atlas' },
  { key: 'volatility', label: 'Volatility',   group: 'risk' },
  { key: 'ema_dist',   label: 'EMA 200 dist', group: 'technicals' },
  { key: 'drawdown',   label: 'Max drawdown', group: 'risk' },
]

export const DEFAULT_COLUMNS: StocksListV6Column[] = [
  'own_badge', 'ticker', 'name', 'sector', 'tier', 'conviction',
  'ret_1d', 'ret_1w', 'ret_6m', 'rs_pct', 'ic', 'composite', 'action',
]

const ROW_HEIGHT = 40
const VIRTUALISE_THRESHOLD = 300

// Minimal HoldingState for held stocks (weights unknown client-side at v6.0)
const BADGE_STATE: HoldingState = {
  portfolio_count: 1,
  weight_range: ['0.00', '0.00'],
  aggregate_weight: '0.00',
  last_add_date: null,
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function tapeScore(s: StockV6Row): number {
  let pos = 0; let icSum = 0
  for (const t of ['1m', '3m', '6m', '12m'] as const) {
    const v = s.conviction_tape[t]
    if (v.direction === 'POSITIVE') pos += 1
    if (v.direction === 'NEGATIVE') pos -= 1
    if (v.ic != null) icSum += v.ic
  }
  return pos + icSum * 0.5
}

function ic6m(s: StockV6Row): number | null { return s.conviction_tape['6m'].ic }

function dominantAction(s: StockV6Row): 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' {
  let pos = 0; let neg = 0
  for (const t of ['1m', '3m', '6m', '12m'] as const) {
    if (s.conviction_tape[t].direction === 'POSITIVE') pos++
    if (s.conviction_tape[t].direction === 'NEGATIVE') neg++
  }
  if (pos > neg && pos >= 2) return 'POSITIVE'
  if (neg > pos && neg >= 2) return 'NEGATIVE'
  return 'NEUTRAL'
}

const ACTION_LABELS = { POSITIVE: 'BUY', NEUTRAL: 'WATCH', NEGATIVE: 'AVOID' }
const ACTION_COLORS = {
  POSITIVE: 'text-signal-pos',
  NEUTRAL: 'text-signal-warn',
  NEGATIVE: 'text-signal-neg',
}

function retStr(v: number | null): string {
  return signedPct(v != null ? String(v) : null)
}
function retColor(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  return v >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}
function rsDisplay(v: number | null): string {
  return v == null ? '—' : `${Math.round(v * 100)}`
}
function icDisplay(v: number | null): string {
  if (v == null) return '—'
  const s = (v * 100).toFixed(1)
  return v >= 0 ? `+${s}` : s
}

function nullLast(va: number | null, vb: number | null, dir: number): number {
  if (va == null && vb == null) return 0
  if (va == null) return 1
  if (vb == null) return -1
  return (va - vb) * dir
}

// ── Props ────────────────────────────────────────────────────────────────────

export interface StocksListV6Props {
  stocks: StockV6Row[]
  heldIids: string[]
  snapshotDate: string
}

// ── Component ────────────────────────────────────────────────────────────────

export function StocksListV6({ stocks, heldIids }: StocksListV6Props) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const urlTier    = (searchParams.get('filter_tier') ?? 'ALL') as TierFilter
  const urlSector  = searchParams.get('filter_sector') ?? 'ALL'
  const urlAction  = (searchParams.get('filter_action') ?? 'ALL') as ActionFilter
  const urlBook    = searchParams.get('in_my_book') === '1'

  const [tierFilter,   setTierState]   = useState<TierFilter>(urlTier)
  const [sectorFilter, setSectorState] = useState<string>(urlSector)
  const [actionFilter, setActionState] = useState<ActionFilter>(urlAction)
  const [inMyBook,     setBookState]   = useState<boolean>(urlBook)
  const [sortKey,      setSortKey]     = useState<SortKey>('composite')
  const [sortDir,      setSortDir]     = useState<'asc' | 'desc'>('desc')
  const [chooserOpen,  setChooserOpen] = useState(false)

  const { visible, setVisible, reset } = useColumnPreferences<StocksListV6Column>(
    'stocks-v6', DEFAULT_COLUMNS,
  )
  const visSet = useMemo(() => new Set(visible), [visible])
  const heldSet = useMemo(() => new Set(heldIids), [heldIids])

  const sectors = useMemo(() => {
    const s = new Set<string>()
    stocks.forEach(r => { if (r.sector) s.add(r.sector) })
    return Array.from(s).sort()
  }, [stocks])

  const updateParams = useCallback((updates: Record<string, string>) => {
    const p = new URLSearchParams(searchParams.toString())
    for (const [k, v] of Object.entries(updates)) {
      if (v === 'ALL' || v === '0') p.delete(k); else p.set(k, v)
    }
    router.replace(`${pathname}?${p.toString()}`, { scroll: false })
  }, [router, pathname, searchParams])

  const setTierFilter = (v: TierFilter) => { setTierState(v); updateParams({ filter_tier: v }) }
  const setSectorFilter = (v: string)  => { setSectorState(v); updateParams({ filter_sector: v }) }
  const setActionFilter = (v: ActionFilter) => { setActionState(v); updateParams({ filter_action: v }) }
  const setInMyBook = (v: boolean) => { setBookState(v); updateParams({ in_my_book: v ? '1' : '0' }) }

  const rows = useMemo(() => {
    let r = stocks.slice()
    if (tierFilter !== 'ALL') r = r.filter(s => s.tier === tierFilter)
    if (sectorFilter !== 'ALL') r = r.filter(s => s.sector === sectorFilter)
    if (actionFilter !== 'ALL') r = r.filter(s => dominantAction(s) === actionFilter)
    if (inMyBook) r = r.filter(s => heldSet.has(s.iid))
    const dir = sortDir === 'asc' ? 1 : -1
    r.sort((a, b) => {
      switch (sortKey) {
        case 'composite': return nullLast(tapeScore(a), tapeScore(b), dir)
        case 'ic':        return nullLast(ic6m(a), ic6m(b), dir)
        case 'rs_pct':    return nullLast(a.rs_pctile_3m, b.rs_pctile_3m, dir)
        case 'ret_1d':    return nullLast(a.ret_1d, b.ret_1d, dir)
        case 'ret_1w':    return nullLast(a.ret_1w, b.ret_1w, dir)
        case 'ret_1m':    return nullLast(a.ret_1m, b.ret_1m, dir)
        case 'ret_3m':    return nullLast(a.ret_3m, b.ret_3m, dir)
        case 'ret_6m':    return nullLast(a.ret_6m, b.ret_6m, dir)
        case 'ret_12m':   return nullLast(a.ret_12m, b.ret_12m, dir)
        case 'symbol':    return a.symbol.localeCompare(b.symbol) * dir
        case 'name':      return (a.company_name ?? '').localeCompare(b.company_name ?? '') * dir
        case 'sector':    return (a.sector ?? '').localeCompare(b.sector ?? '') * dir
        case 'tier':      return (a.tier ?? '').localeCompare(b.tier ?? '') * dir
        default:          return 0
      }
    })
    return r
  }, [stocks, tierFilter, sectorFilter, actionFilter, inMyBook, heldSet, sortKey, sortDir])

  const toggleSort = (k: SortKey) => {
    if (k === sortKey) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(k); setSortDir('desc') }
  }

  const clearFilters = () => {
    setTierState('ALL'); setSectorState('ALL'); setActionState('ALL'); setBookState(false)
    updateParams({ filter_tier: 'ALL', filter_sector: 'ALL', filter_action: 'ALL', in_my_book: '0' })
  }

  // ── Virtualization ───────────────────────────────────────────────────────

  const parentRef = useRef<HTMLDivElement>(null)
  const shouldVirtualise = rows.length > VIRTUALISE_THRESHOLD
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
    enabled: shouldVirtualise,
  })

  // ── Sub-components ───────────────────────────────────────────────────────

  function SortIcon({ k }: { k: SortKey }) {
    if (k !== sortKey) return null
    return sortDir === 'asc' ? <ChevronUp size={10} className="text-teal" /> : <ChevronDown size={10} className="text-teal" />
  }

  function Th({ label, k, align = 'right' }: { label: string; k: SortKey; align?: 'left' | 'right' }) {
    return (
      <th scope="col" onClick={() => toggleSort(k)}
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align}`}>
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'justify-end' : 'justify-start'}`}>
          {label}<SortIcon k={k} />
        </span>
      </th>
    )
  }

  function ThS({ label, align = 'left' }: { label: string; align?: 'left' | 'right' }) {
    return (
      <th scope="col" className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary select-none whitespace-nowrap text-${align}`}>
        {label}
      </th>
    )
  }

  function renderRow(s: StockV6Row, style?: CSSProperties) {
    const action = dominantAction(s)
    const ic = ic6m(s)
    const comp = tapeScore(s)
    const holdingState = heldSet.has(s.iid) ? BADGE_STATE : null
    return (
      <tr key={s.iid} style={style}
        className="border-b border-paper-rule hover:bg-paper-rule/20 transition-colors"
        data-testid="stocks-row" data-tier={s.tier} data-action={action}
        data-held={heldSet.has(s.iid) ? 'true' : 'false'}
      >
        {visSet.has('own_badge') && (
          <td className="px-3 py-2 whitespace-nowrap" aria-label="Portfolio holding">
            <PortfolioBadge state={holdingState} variant="compact" />
          </td>
        )}
        {visSet.has('ticker') && (
          <td className="px-3 py-2 whitespace-nowrap font-mono text-xs font-semibold text-ink-primary">
            <a href={`/v6/stocks/${encodeURIComponent(s.iid)}`} className="hover:text-teal transition-colors"
              aria-label={`View ${s.symbol} detail`}>{s.symbol}</a>
          </td>
        )}
        {visSet.has('name') && (
          <td className="px-3 py-2 font-sans text-xs text-ink-secondary max-w-[180px] truncate"
            title={s.company_name ?? ''} aria-label={`Company name: ${s.company_name ?? '—'}`}>
            {s.company_name ?? '—'}
          </td>
        )}
        {visSet.has('sector') && (
          <td className="px-3 py-2 font-sans text-[11px] text-ink-secondary whitespace-nowrap"
            aria-label={`Sector: ${s.sector ?? '—'}`}>{s.sector ?? '—'}</td>
        )}
        {visSet.has('tier') && (
          <td className="px-3 py-2 font-sans text-[11px] text-ink-tertiary whitespace-nowrap"
            aria-label={`Tier: ${s.tier}`}>{s.tier}</td>
        )}
        {visSet.has('conviction') && (
          <td className="px-3 py-2 whitespace-nowrap" aria-label="Conviction tape">
            <ConvictionTape tape={s.conviction_tape} compact />
          </td>
        )}
        {visSet.has('ret_1d') && (
          <td className={`px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(s.ret_1d)}`}
            aria-label={`1d return: ${retStr(s.ret_1d)}`}>{retStr(s.ret_1d)}</td>
        )}
        {visSet.has('ret_1w') && (
          <td className={`px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(s.ret_1w)}`}
            aria-label={`1w return: ${retStr(s.ret_1w)}`}>{retStr(s.ret_1w)}</td>
        )}
        {visSet.has('ret_1m') && (
          <td className={`px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(s.ret_1m)}`}
            aria-label={`1m return: ${retStr(s.ret_1m)}`}>{retStr(s.ret_1m)}</td>
        )}
        {visSet.has('ret_3m') && (
          <td className={`px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(s.ret_3m)}`}
            aria-label={`3m return: ${retStr(s.ret_3m)}`}>{retStr(s.ret_3m)}</td>
        )}
        {visSet.has('ret_6m') && (
          <td className={`px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(s.ret_6m)}`}
            aria-label={`6m return: ${retStr(s.ret_6m)}`}>{retStr(s.ret_6m)}</td>
        )}
        {visSet.has('ret_12m') && (
          <td className={`px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap ${retColor(s.ret_12m)}`}
            aria-label={`12m return: ${retStr(s.ret_12m)}`}>{retStr(s.ret_12m)}</td>
        )}
        {visSet.has('rs_pct') && (
          <td className="px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-secondary"
            aria-label={`RS percentile: ${rsDisplay(s.rs_pctile_3m)}`}>{rsDisplay(s.rs_pctile_3m)}</td>
        )}
        {visSet.has('ic') && (
          <td className={`px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap ${ic != null && ic >= 0 ? 'text-signal-pos' : ic != null ? 'text-signal-neg' : 'text-ink-tertiary'}`}
            aria-label={`IC 6m: ${icDisplay(ic)}`}>{icDisplay(ic)}</td>
        )}
        {visSet.has('composite') && (
          <td className="px-3 py-2 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-primary"
            aria-label={`Composite: ${comp.toFixed(2)}`}>{comp.toFixed(2)}</td>
        )}
        {visSet.has('action') && (
          <td className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap ${ACTION_COLORS[action]}`}
            aria-label={`Action: ${ACTION_LABELS[action]}`}>{ACTION_LABELS[action]}</td>
        )}
        {visSet.has('volatility') && (
          <td className="px-3 py-2 font-mono text-xs text-right whitespace-nowrap text-ink-tertiary" aria-label="Volatility: —">—</td>
        )}
        {visSet.has('ema_dist') && (
          <td className="px-3 py-2 font-mono text-xs text-right whitespace-nowrap text-ink-tertiary" aria-label="EMA 200 distance: —">—</td>
        )}
        {visSet.has('drawdown') && (
          <td className="px-3 py-2 font-mono text-xs text-right whitespace-nowrap text-ink-tertiary" aria-label="Max drawdown: —">—</td>
        )}
      </tr>
    )
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Filter row */}
      <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-3 flex-wrap">
        <select value={tierFilter} onChange={e => setTierFilter(e.target.value as TierFilter)}
          aria-label="Filter by tier" data-testid="tier-filter"
          className="font-sans text-xs border border-paper-rule rounded-[2px] bg-paper px-2 py-1">
          <option value="ALL">All tiers</option>
          <option value="Large">Large</option>
          <option value="Mid">Mid</option>
          <option value="Small">Small</option>
        </select>

        <select value={sectorFilter} onChange={e => setSectorFilter(e.target.value)}
          aria-label="Filter by sector" data-testid="sector-filter"
          className="font-sans text-xs border border-paper-rule rounded-[2px] bg-paper px-2 py-1">
          <option value="ALL">All sectors</option>
          {sectors.map(sec => <option key={sec} value={sec}>{sec}</option>)}
        </select>

        <div className="flex items-center gap-1" role="group" aria-label="Filter by action">
          {(['ALL', 'POSITIVE', 'NEUTRAL', 'NEGATIVE'] as ActionFilter[]).map(a => (
            <button key={a} onClick={() => setActionFilter(a)}
              data-testid={`action-filter-${a.toLowerCase()}`}
              className={`px-2.5 py-1 rounded-[2px] font-sans text-[11px] border transition-colors ${actionFilter === a ? 'bg-teal/10 text-teal border-teal/30' : 'bg-paper text-ink-secondary border-paper-rule hover:bg-paper-rule/20'}`}>
              {a === 'ALL' ? 'All' : a === 'POSITIVE' ? 'BUY' : a === 'NEGATIVE' ? 'AVOID' : 'WATCH'}
            </button>
          ))}
        </div>

        <button onClick={() => setInMyBook(!inMyBook)} data-testid="in-my-book-toggle"
          className={`px-2.5 py-1 rounded-[2px] font-sans text-[11px] border transition-colors ${inMyBook ? 'bg-teal/10 text-teal border-teal/30' : 'bg-paper text-ink-secondary border-paper-rule hover:bg-paper-rule/20'}`}>
          In my book
        </button>

        <span className="font-sans text-[11px] text-ink-tertiary ml-auto">
          {rows.length} of {stocks.length}
        </span>
        <ColumnChooser columns={COLUMN_DEFS} visible={visible} onVisibleChange={setVisible}
          onReset={reset} open={chooserOpen} onOpenChange={setChooserOpen} />
      </div>

      {/* Table */}
      <div ref={parentRef} className="overflow-auto border-b border-paper-rule"
        style={{ maxHeight: shouldVirtualise ? '70vh' : undefined }}>
        {rows.length === 0 ? (
          <div className="px-6 py-12 text-center" data-testid="empty-state">
            <p className="font-sans text-sm text-ink-secondary mb-2">
              No stocks match the current filters.
            </p>
            <button onClick={clearFilters} className="font-sans text-xs text-teal hover:underline">
              Clear filters
            </button>
          </div>
        ) : (
          <table role="table" className="w-full border-collapse" aria-label="Stocks universe">
            <thead>
              <tr className="border-b border-paper-rule bg-paper sticky top-0 z-10">
                {visSet.has('own_badge')  && <ThS label="Held" />}
                {visSet.has('ticker')     && <Th  label="Ticker"    k="symbol"    align="left"  />}
                {visSet.has('name')       && <Th  label="Name"      k="name"      align="left"  />}
                {visSet.has('sector')     && <Th  label="Sector"    k="sector"    align="left"  />}
                {visSet.has('tier')       && <Th  label="Tier"      k="tier"      align="left"  />}
                {visSet.has('conviction') && <ThS label="Conviction" />}
                {visSet.has('ret_1d')     && <Th  label="1d"        k="ret_1d"   />}
                {visSet.has('ret_1w')     && <Th  label="1w"        k="ret_1w"   />}
                {visSet.has('ret_1m')     && <Th  label="1m"        k="ret_1m"   />}
                {visSet.has('ret_3m')     && <Th  label="3m"        k="ret_3m"   />}
                {visSet.has('ret_6m')     && <Th  label="6m"        k="ret_6m"   />}
                {visSet.has('ret_12m')    && <Th  label="12m"       k="ret_12m"  />}
                {visSet.has('rs_pct')     && <Th  label="RS%"       k="rs_pct"   />}
                {visSet.has('ic')         && <Th  label="IC"        k="ic"       />}
                {visSet.has('composite')  && <Th  label="Composite" k="composite"/>}
                {visSet.has('action')     && <ThS label="Action" />}
                {visSet.has('volatility') && <ThS label="Vol"  align="right" />}
                {visSet.has('ema_dist')   && <ThS label="EMA200" align="right" />}
                {visSet.has('drawdown')   && <ThS label="DD" align="right" />}
              </tr>
            </thead>
            {shouldVirtualise ? (
              <tbody style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
                {virtualizer.getVirtualItems().map(vItem =>
                  renderRow(rows[vItem.index], {
                    position: 'absolute', top: 0, left: 0, width: '100%',
                    transform: `translateY(${vItem.start}px)`,
                    height: `${ROW_HEIGHT}px`,
                  }),
                )}
              </tbody>
            ) : (
              <tbody>{rows.map(s => renderRow(s))}</tbody>
            )}
          </table>
        )}
      </div>
    </div>
  )
}
