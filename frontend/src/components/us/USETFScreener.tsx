'use client'
import { useState, useMemo } from 'react'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { USETFRow } from '@/lib/queries/us-etfs'

const RS_STYLE: Record<string, string> = {
  Leader:        'bg-signal-pos/20 text-signal-pos',
  Strong:        'bg-signal-pos/10 text-signal-pos',
  Consolidating: 'bg-teal/15 text-teal',
  Emerging:      'bg-amber-100 text-amber-700',
  Average:       'bg-ink-tertiary/10 text-ink-secondary',
  Weak:          'bg-orange-100 text-orange-700',
  Laggard:       'bg-signal-neg/20 text-signal-neg',
}

const MOM_STYLE: Record<string, string> = {
  Accelerating:  'bg-signal-pos/20 text-signal-pos',
  Improving:     'bg-signal-pos/10 text-signal-pos',
  Flat:          'bg-ink-tertiary/10 text-ink-secondary',
  Deteriorating: 'bg-signal-neg/10 text-signal-neg',
  Collapsing:    'bg-signal-neg/20 text-signal-neg',
}

const MOM_ABBREV: Record<string, string> = {
  Accelerating:  'Accel',
  Improving:     'Imprvg',
  Flat:          'Flat',
  Deteriorating: 'Detrt',
  Collapsing:    'Collps',
}

type CategoryTab = 'All' | 'Sector' | 'Broad Market' | 'Factor' | 'Thematic'

const TABS: CategoryTab[] = ['All', 'Sector', 'Broad Market', 'Factor', 'Thematic']

type SortCol =
  | 'ticker' | 'etf_category' | 'linked_sector' | 'rs_state'
  | 'rs_pctile_3m_vt' | 'rs_3m_vt' | 'ret_1m' | 'ret_3m' | 'ret_12m'
  | 'realized_vol_63' | 'momentum_state'

function categoryTab(etf: USETFRow): CategoryTab {
  const cat = etf.etf_category?.toLowerCase() ?? ''
  if (cat.includes('sector')) return 'Sector'
  if (cat.includes('broad') || etf.is_benchmark) return 'Broad Market'
  if (cat.includes('factor')) return 'Factor'
  return 'Thematic'
}

function fmtRet(v: string | null): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return (n >= 0 ? '+' : '') + n.toFixed(1) + '%'
}

function retColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  return parseFloat(v) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

function fmtVol(v: string | null): string {
  if (v == null) return '—'
  return (parseFloat(v) * 100).toFixed(1) + '%'
}

function numVal(v: string | null): number | null {
  if (v == null) return null
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : null
}

const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']

function stateRank(order: string[], val: string | null): number {
  if (!val) return order.length
  const i = order.indexOf(val)
  return i === -1 ? order.length : i
}

function RSPctileBar({ value }: { value: string | null }) {
  const pct = value != null ? parseFloat(value) : null
  const display = pct != null ? Math.round(pct * 100) + '%' : '—'
  const width = pct != null ? Math.round(pct * 100) : 0
  const barColor = pct == null ? 'bg-ink-tertiary/20'
    : pct >= 0.7 ? 'bg-signal-pos'
    : pct >= 0.4 ? 'bg-teal'
    : 'bg-signal-neg/60'

  return (
    <div className="flex items-center gap-1.5 justify-end">
      <span className="font-mono text-xs tabular-nums text-ink-secondary w-8 text-right">{display}</span>
      <div className="w-12 h-1.5 bg-ink-tertiary/15 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

export function USETFScreener({ etfs }: { etfs: USETFRow[] }) {
  const [activeTab, setActiveTab] = useState<CategoryTab>('All')
  const [sortCol, setSortCol] = useState<SortCol>('rs_pctile_3m_vt')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  function handleSort(col: SortCol) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('desc') }
  }

  const filtered = useMemo(() => {
    const rows = activeTab === 'All'
      ? etfs
      : etfs.filter(e => categoryTab(e) === activeTab)

    return [...rows].sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1

      if (sortCol === 'ticker') return dir * a.ticker.localeCompare(b.ticker)
      if (sortCol === 'etf_category') {
        return dir * (a.etf_category ?? '').localeCompare(b.etf_category ?? '')
      }
      if (sortCol === 'linked_sector') {
        return dir * (a.linked_sector ?? '').localeCompare(b.linked_sector ?? '')
      }
      if (sortCol === 'rs_state') {
        return dir * (stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state))
      }
      if (sortCol === 'momentum_state') {
        return dir * (stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state))
      }

      const numCols: Record<string, (r: USETFRow) => string | null> = {
        rs_pctile_3m_vt: r => r.rs_pctile_3m_vt,
        rs_3m_vt:        r => r.rs_3m_vt,
        ret_1m:          r => r.ret_1m,
        ret_3m:          r => r.ret_3m,
        ret_12m:         r => r.ret_12m,
        realized_vol_63: r => r.realized_vol_63,
      }
      const getter = numCols[sortCol]
      if (getter) {
        const av = numVal(getter(a))
        const bv = numVal(getter(b))
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        return dir * (av - bv)
      }
      return 0
    })
  }, [etfs, activeTab, sortCol, sortDir])

  function SortIcon({ col }: { col: SortCol }) {
    if (sortCol !== col) return <ChevronUp className="w-3 h-3 opacity-20" />
    return sortDir === 'asc'
      ? <ChevronUp className="w-3 h-3 text-teal" />
      : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, col, align = 'left' }: { label: string; col: SortCol; align?: 'left' | 'right' }) {
    const active = sortCol === col
    return (
      <th
        onClick={() => handleSort(col)}
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align} ${active ? 'text-teal' : 'text-ink-tertiary'}`}
      >
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
          {label}
          <SortIcon col={col} />
        </span>
      </th>
    )
  }

  const tabCounts = useMemo(() => {
    const counts: Partial<Record<CategoryTab, number>> = {}
    for (const e of etfs) {
      const tab = categoryTab(e)
      counts[tab] = (counts[tab] ?? 0) + 1
    }
    counts['All'] = etfs.length
    return counts
  }, [etfs])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-0 border-b border-paper-rule">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-2 font-sans text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === tab
                ? 'border-b-2 border-teal text-ink-primary -mb-px'
                : 'text-ink-tertiary hover:text-ink-secondary'
            }`}
          >
            {tab}
            <span className="ml-1 font-mono text-[10px] opacity-60">
              {tabCounts[tab] ?? 0}
            </span>
          </button>
        ))}
      </div>

      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule sticky top-0 bg-paper z-10">
              <Th label="Ticker" col="ticker" />
              <Th label="Category" col="etf_category" />
              <Th label="Sector/Linked" col="linked_sector" />
              <Th label="RS State" col="rs_state" />
              <Th label="VT 3M%" col="rs_pctile_3m_vt" align="right" />
              <Th label="vs VT 3M" col="rs_3m_vt" align="right" />
              <Th label="1M" col="ret_1m" align="right" />
              <Th label="3M" col="ret_3m" align="right" />
              <Th label="12M" col="ret_12m" align="right" />
              <Th label="Vol" col="realized_vol_63" align="right" />
              <Th label="Momentum" col="momentum_state" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={11} className="px-6 py-10 text-center font-sans text-sm text-ink-secondary">
                  No ETFs match the current filters.
                </td>
              </tr>
            ) : (
              filtered.map((row, i) => (
                <tr
                  key={row.ticker}
                  className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors ${i % 2 !== 0 ? 'bg-paper-bg/50' : ''}`}
                >
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <div className="flex items-center gap-1">
                      <span className="font-mono text-sm font-semibold text-ink-primary">{row.ticker}</span>
                      {row.is_benchmark && (
                        <span className="font-sans text-[9px] text-ink-tertiary bg-ink-tertiary/10 px-1 rounded">BM</span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 max-w-[140px] truncate">
                    <span className="font-sans text-xs text-ink-secondary" title={row.etf_category ?? ''}>
                      {row.etf_category ?? '—'}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="font-sans text-xs text-ink-tertiary">
                      {row.linked_sector ?? '—'}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    {row.rs_state ? (
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${RS_STYLE[row.rs_state] ?? 'bg-ink-tertiary/10 text-ink-secondary'}`}>
                        {row.rs_state}
                      </span>
                    ) : <span className="text-ink-tertiary text-xs">—</span>}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <RSPctileBar value={row.rs_pctile_3m_vt} />
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${retColor(row.rs_3m_vt)}`}>
                    {fmtRet(row.rs_3m_vt)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${retColor(row.ret_1m)}`}>
                    {fmtRet(row.ret_1m)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${retColor(row.ret_3m)}`}>
                    {fmtRet(row.ret_3m)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${retColor(row.ret_12m)}`}>
                    {fmtRet(row.ret_12m)}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                    {fmtVol(row.realized_vol_63)}
                  </td>
                  <td className="px-3 py-2.5">
                    {row.momentum_state ? (
                      <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${MOM_STYLE[row.momentum_state] ?? 'bg-ink-tertiary/10 text-ink-secondary'}`}>
                        {MOM_ABBREV[row.momentum_state] ?? row.momentum_state}
                      </span>
                    ) : <span className="text-ink-tertiary text-xs">—</span>}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
