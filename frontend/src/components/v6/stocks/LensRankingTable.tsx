// Lens ranking table — sortable table of all stocks by any lens or composite.
// Behind NEXT_PUBLIC_LENS_V4 feature flag.

'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import type { LensScoreSummary } from '@/lib/queries/lens-scores'

type SortKey = 'symbol' | 'composite' | 'technical' | 'fundamental' | 'valuation' | 'catalyst' | 'flow' | 'policy'

type Props = {
  scores: LensScoreSummary[]
}

const LENS_COLS: { key: SortKey; label: string; color: string }[] = [
  { key: 'technical', label: 'Tech', color: 'bg-blue-500' },
  { key: 'fundamental', label: 'Fund', color: 'bg-emerald-500' },
  { key: 'valuation', label: 'Val', color: 'bg-amber-500' },
  { key: 'catalyst', label: 'Cat', color: 'bg-violet-500' },
  { key: 'flow', label: 'Flow', color: 'bg-cyan-500' },
  { key: 'policy', label: 'Pol', color: 'bg-rose-500' },
]

function scoreCell(v: number | null) {
  if (v == null) return <span className="text-ink-tertiary">—</span>
  const cls = v >= 70 ? 'text-signal-pos' : v >= 40 ? 'text-ink-secondary' : 'text-signal-neg'
  return <span className={`tabular-nums ${cls}`}>{v.toFixed(0)}</span>
}

function tierBadge(tier: string | null) {
  const map: Record<string, string> = {
    HIGHEST: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
    HIGH: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
    MEDIUM: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
    WATCH: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
    BELOW_THRESHOLD: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  }
  const cls = (tier && map[tier]) || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
  const label = tier === 'BELOW_THRESHOLD' ? 'BELOW' : (tier ?? '—')
  return <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${cls}`}>{label}</span>
}

export function LensRankingTable({ scores }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('composite')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [sectorFilter, setSectorFilter] = useState<string>('all')
  const [tierFilter, setTierFilter] = useState<string>('all')

  const sectors = useMemo(() => {
    const set = new Set<string>()
    scores.forEach(s => { if (s.sector) set.add(s.sector) })
    return ['all', ...Array.from(set).sort()]
  }, [scores])

  const tiers = useMemo(() => {
    const set = new Set<string>()
    scores.forEach(s => { if (s.conviction_tier) set.add(s.conviction_tier) })
    return ['all', ...Array.from(set).sort()]
  }, [scores])

  const sorted = useMemo(() => {
    let rows = scores.slice()
    if (sectorFilter !== 'all') rows = rows.filter(s => s.sector === sectorFilter)
    if (tierFilter !== 'all') rows = rows.filter(s => s.conviction_tier === tierFilter)

    rows.sort((a, b) => {
      if (sortKey === 'symbol') {
        return sortDir === 'asc' ? a.symbol.localeCompare(b.symbol) : b.symbol.localeCompare(a.symbol)
      }
      const av = a[sortKey] as number | null
      const bv = b[sortKey] as number | null
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      return sortDir === 'asc' ? av - bv : bv - av
    })
    return rows
  }, [scores, sortKey, sortDir, sectorFilter, tierFilter])

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const chevron = (key: SortKey) => sortKey === key ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={sectorFilter}
          onChange={e => setSectorFilter(e.target.value)}
          className="text-xs border border-paper-rule rounded px-2 py-1 bg-paper text-ink-secondary"
        >
          {sectors.map(s => (
            <option key={s} value={s}>{s === 'all' ? 'All Sectors' : s}</option>
          ))}
        </select>
        <select
          value={tierFilter}
          onChange={e => setTierFilter(e.target.value)}
          className="text-xs border border-paper-rule rounded px-2 py-1 bg-paper text-ink-secondary"
        >
          {tiers.map(t => (
            <option key={t} value={t}>{t === 'all' ? 'All Tiers' : t}</option>
          ))}
        </select>
        <span className="text-xs text-ink-tertiary self-center">{sorted.length} stocks</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="tbl-centered w-full text-xs font-sans">
          <thead>
            <tr className="border-b border-paper-rule text-ink-tertiary">
              <th className="text-left px-2 py-2 font-medium cursor-pointer select-none" onClick={() => toggleSort('symbol')}>
                Symbol{chevron('symbol')}
              </th>
              <th className="text-left px-2 py-2 font-medium">Sector</th>
              <th className="text-right px-2 py-2 font-medium cursor-pointer select-none" onClick={() => toggleSort('composite')}>
                Composite{chevron('composite')}
              </th>
              {LENS_COLS.map(col => (
                <th key={col.key} className="text-right px-2 py-2 font-medium cursor-pointer select-none" onClick={() => toggleSort(col.key)}>
                  {col.label}{chevron(col.key)}
                </th>
              ))}
              <th className="text-center px-2 py-2 font-medium">Tier</th>
              <th className="text-center px-2 py-2 font-medium">Flags</th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 200).map(row => (
              <tr key={row.instrument_id} className="border-b border-paper-rule/50 hover:bg-paper-soft/50 transition-colors">
                <td className="px-2 py-1.5">
                  <Link href={`/stocks/${row.symbol}`} className="text-accent hover:underline font-medium">
                    {row.symbol}
                  </Link>
                  <div className="text-[10px] text-ink-tertiary truncate max-w-[140px]">{row.name}</div>
                </td>
                <td className="px-2 py-1.5 text-ink-tertiary truncate max-w-[100px]">{row.sector ?? '—'}</td>
                <td className="px-2 py-1.5 text-right font-semibold">{scoreCell(row.composite)}</td>
                {LENS_COLS.map(col => (
                  <td key={col.key} className="px-2 py-1.5 text-right">{scoreCell(row[col.key as keyof LensScoreSummary] as number | null)}</td>
                ))}
                <td className="px-2 py-1.5 text-center">{tierBadge(row.conviction_tier)}</td>
                <td className="px-2 py-1.5 text-center">
                  {row.risk_flags?.length ? (
                    <span className="text-signal-neg text-[10px]" title={row.risk_flags.join(', ')}>
                      {row.risk_flags.length}
                    </span>
                  ) : (
                    <span className="text-ink-tertiary">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sorted.length > 200 && (
        <p className="text-xs text-ink-tertiary mt-2">Showing top 200 of {sorted.length} stocks</p>
      )}
    </div>
  )
}
