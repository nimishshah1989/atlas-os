'use client'
import { useState, useMemo } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import { pct, pctColor, PosSizeBar, StateChip, RSPctileBar } from '@/lib/stock-formatters'
import { SectorBadge } from './SectorBadge'

type SortKey =
  | 'symbol' | 'sector' | 'rs_pctile_3m' | 'rs_3m_nifty500'
  | 'ret_1m' | 'ret_3m' | 'ret_6m' | 'position_size_pct'

type FilterChip = 'all' | 'n50' | 'n100' | 'n500' | 'investable' | 'strong'

const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',        label: 'All' },
  { key: 'n50',        label: 'Nifty 50' },
  { key: 'n100',       label: 'Nifty 100' },
  { key: 'n500',       label: 'Nifty 500' },
  { key: 'investable', label: 'Investable' },
  { key: 'strong',     label: 'Strong' },
]

export function StockScreener({ stocks }: { stocks: StockRowWithSector[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('rs_pctile_3m')
  const [asc, setAsc] = useState(false)
  const [chip, setChip] = useState<FilterChip>('all')
  const [search, setSearch] = useState('')

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  function clearFilters() {
    setChip('all')
    setSearch('')
  }

  const filtered = useMemo(() => {
    let result = stocks

    if (chip === 'n50') result = result.filter(s => s.in_nifty_50)
    else if (chip === 'n100') result = result.filter(s => s.in_nifty_100)
    else if (chip === 'n500') result = result.filter(s => s.in_nifty_500)
    else if (chip === 'investable') result = result.filter(s => s.is_investable)
    else if (chip === 'strong') result = result.filter(
      s => s.rs_state === 'Overweight_RS' && s.momentum_state === 'Improving'
    )

    if (search.trim()) {
      const q = search.trim().toLowerCase()
      result = result.filter(
        s => s.symbol.toLowerCase().includes(q) || s.company_name.toLowerCase().includes(q)
      )
    }

    return [...result].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'symbol') cmp = a.symbol.localeCompare(b.symbol)
      else if (sortKey === 'sector') cmp = a.sector.localeCompare(b.sector)
      else {
        const av = a[sortKey] != null ? parseFloat(a[sortKey] as string) : null
        const bv = b[sortKey] != null ? parseFloat(b[sortKey] as string) : null
        if (av == null && bv == null) cmp = 0
        else if (av == null) cmp = 1
        else if (bv == null) cmp = -1
        else cmp = av - bv
      }
      return asc ? cmp : -cmp
    })
  }, [stocks, chip, search, sortKey, asc])

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
          placeholder="Search symbol or company..."
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
          Showing {filtered.length} of {stocks.length} stocks
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <Th label="Symbol" k="symbol" />
              <Th label="Sector" k="sector" />
              <th className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">
                State
              </th>
              <Th label="1M" k="ret_1m" align="right" />
              <Th label="3M" k="ret_3m" align="right" />
              <Th label="6M" k="ret_6m" align="right" />
              <Th label="RS Pctile" k="rs_pctile_3m" align="right" />
              <Th label="Deploy %" k="position_size_pct" align="right" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-10 text-center">
                  <p className="font-sans text-sm text-ink-secondary mb-2">
                    No stocks match the current filter.
                  </p>
                  <button onClick={clearFilters} className="font-sans text-xs text-teal hover:underline">
                    Clear filters
                  </button>
                </td>
              </tr>
            ) : (
              filtered.map((row, i) => (
                <tr
                  key={row.instrument_id}
                  className={`border-b border-paper-rule last:border-0 hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
                >
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <Link href={`/stocks/${encodeURIComponent(row.symbol)}`} className="hover:opacity-80">
                      <div className="font-sans text-xs font-semibold text-ink-primary">{row.symbol}</div>
                      <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[180px]" title={row.company_name}>
                        {row.company_name}
                      </div>
                    </Link>
                  </td>
                  <td className="px-3 py-2.5">
                    <SectorBadge sector={row.sector} />
                  </td>
                  <td className="px-3 py-2.5">
                    <StateChip rs={row.rs_state} mom={row.momentum_state} />
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1m)}`}>
                    {pct(row.ret_1m)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_3m)}`}>
                    {pct(row.ret_3m)}
                  </td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_6m)}`}>
                    {pct(row.ret_6m)}
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
