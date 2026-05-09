'use client'
import { useState, useMemo } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { ETFRow } from '@/lib/queries/etfs'
import {
  pct, pctColor, PosSizeBar, RSPctileBar,
  RSStateChip, MomentumChip, RiskChip,
} from '@/lib/stock-formatters'

const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
const RISK_ORDER = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend']

function stateRank(order: string[], val: string | null): number {
  if (!val) return order.length
  const i = order.indexOf(val)
  return i === -1 ? order.length : i
}

type SortKey =
  | 'ticker' | 'theme' | 'rs_pctile_3m'
  | 'ret_1m' | 'ret_3m' | 'position_size_pct'
  | 'rs_state' | 'momentum_state' | 'risk_state'

type FilterChip = 'all' | 'broad' | 'sectoral' | 'thematic' | 'investable'

const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',        label: 'All' },
  { key: 'broad',      label: 'Broad' },
  { key: 'sectoral',   label: 'Sectoral' },
  { key: 'thematic',   label: 'Thematic' },
  { key: 'investable', label: 'Investable' },
]

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

export function ETFScreener({ etfs }: { etfs: ETFRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('rs_pctile_3m')
  const [asc, setAsc] = useState(false)
  const [chip, setChip] = useState<FilterChip>('all')
  const [search, setSearch] = useState('')

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  const filtered = useMemo(() => {
    let result = etfs

    if (chip === 'broad')      result = result.filter(e => e.theme === 'Broad')
    else if (chip === 'sectoral') result = result.filter(e => e.theme === 'Sectoral')
    else if (chip === 'thematic') result = result.filter(e => e.theme === 'Thematic')
    else if (chip === 'investable') result = result.filter(e => e.is_investable)

    if (search.trim()) {
      const q = search.trim().toLowerCase()
      result = result.filter(
        e => e.ticker.toLowerCase().includes(q) || (e.etf_name ?? '').toLowerCase().includes(q)
      )
    }

    return [...result].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'ticker') cmp = a.ticker.localeCompare(b.ticker)
      else if (sortKey === 'theme') cmp = a.theme.localeCompare(b.theme)
      else if (sortKey === 'rs_state') cmp = stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state)
      else if (sortKey === 'momentum_state') cmp = stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state)
      else if (sortKey === 'risk_state') cmp = stateRank(RISK_ORDER, a.risk_state) - stateRank(RISK_ORDER, b.risk_state)
      else {
        const av = a[sortKey as keyof ETFRow] != null ? parseFloat(a[sortKey as keyof ETFRow] as string) : null
        const bv = b[sortKey as keyof ETFRow] != null ? parseFloat(b[sortKey as keyof ETFRow] as string) : null
        if (av == null && bv == null) cmp = 0
        else if (av == null) cmp = 1
        else if (bv == null) cmp = -1
        else cmp = av - bv
      }
      return asc ? cmp : -cmp
    })
  }, [etfs, chip, search, sortKey, asc])

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc ? <ChevronUp className="w-3 h-3 text-teal" /> : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, k, align = 'left' }: { label: string; k: SortKey; align?: 'left' | 'right' }) {
    const active = sortKey === k
    return (
      <th
        onClick={() => handleSort(k)}
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align} ${active ? 'text-teal' : 'text-ink-tertiary'}`}
      >
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
          {label}
          <SortIcon k={k} />
        </span>
      </th>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="Search ticker or name..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper placeholder:text-ink-tertiary focus:outline-none focus:ring-1 focus:ring-teal/50 w-56"
        />
        <div className="flex flex-wrap gap-1.5">
          {CHIPS.map(c => (
            <button
              key={c.key}
              type="button"
              aria-pressed={chip === c.key}
              onClick={() => setChip(c.key)}
              className={`px-2.5 py-1 rounded-sm font-sans text-xs font-medium transition-colors ${
                chip === c.key
                  ? 'bg-teal text-paper'
                  : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <span className="ml-auto font-sans text-xs text-ink-tertiary whitespace-nowrap">
          Showing {filtered.length} of {etfs.length} ETFs
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <Th label="Ticker" k="ticker" />
              <Th label="Theme" k="theme" />
              <Th label="RS State" k="rs_state" />
              <Th label="Mom" k="momentum_state" />
              <Th label="Risk" k="risk_state" />
              <Th label="1M" k="ret_1m" align="right" />
              <Th label="3M" k="ret_3m" align="right" />
              <Th label="RS Pctile" k="rs_pctile_3m" align="right" />
              <Th label="Deploy %" k="position_size_pct" align="right" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-6 py-10 text-center">
                  <p className="font-sans text-sm text-ink-secondary">No ETFs match the current filter.</p>
                </td>
              </tr>
            ) : (
              filtered.map((row, i) => (
                <tr
                  key={row.ticker}
                  className={`border-b border-paper-rule last:border-0 hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
                >
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <Link href={`/etfs/${encodeURIComponent(row.ticker)}`} className="hover:opacity-80">
                      <div className="font-sans text-xs font-semibold text-ink-primary">{row.ticker}</div>
                      <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[200px]" title={row.etf_name ?? ''}>
                        {row.etf_name ?? '—'}
                      </div>
                    </Link>
                  </td>
                  <td className="px-3 py-2.5">
                    <ThemeBadge theme={row.theme} />
                  </td>
                  <td className="px-3 py-2.5">
                    <RSStateChip value={row.rs_state} />
                  </td>
                  <td className="px-3 py-2.5">
                    <MomentumChip value={row.momentum_state} />
                  </td>
                  <td className="px-3 py-2.5">
                    <RiskChip value={row.risk_state} />
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1m)}`}>
                    {pct(row.ret_1m)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_3m)}`}>
                    {pct(row.ret_3m)}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <RSPctileBar value={row.rs_pctile_3m} />
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="flex justify-end">
                      <PosSizeBar value={row.position_size_pct} />
                    </div>
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
