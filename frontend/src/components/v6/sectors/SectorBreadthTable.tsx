'use client'
// SectorBreadthTable — compact table form of sector EMA participation. Every numeric
// column header sorts (FM 2026-06-26). Default: %>EMA21 desc. Top movers link to the stock.
import { useState } from 'react'
import Link from 'next/link'
import type { SectorBreadthMVRow, SectorBreadthTrendRow } from '@/lib/queries/v6/sectors'

const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`)
const heat = (v: number | null) => {
  if (v == null) return 'text-txt-3'
  const p = v * 100
  return p >= 60 ? 'text-sig-pos' : p >= 40 ? 'text-txt-2' : 'text-sig-neg'
}

type SortKey = 'constituent_count' | 'pct_above_ema21' | 'pct_above_ema50' | 'pct_above_ema200'

// Tiny inline EMA21 trend: now · 1w · 1m, tinted by the now−1m direction.
function Ema21Trend({ t }: { t: SectorBreadthTrendRow | undefined }) {
  if (!t) return <span className="text-txt-3">—</span>
  const delta = t.ema21_now != null && t.ema21_1m != null ? t.ema21_now - t.ema21_1m : null
  const tint = delta == null ? 'text-txt-3' : delta > 0.02 ? 'text-sig-pos' : delta < -0.02 ? 'text-sig-neg' : 'text-txt-2'
  const n = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(0)}`)
  return (
    <span className={`tabular-nums ${tint}`} title="% above EMA21 — now · 1w ago · 1m ago">
      {n(t.ema21_now)}
      <span className="text-txt-3"> · </span>
      <span className="text-txt-3">{n(t.ema21_1w)}</span>
      <span className="text-txt-3"> · </span>
      <span className="text-txt-3">{n(t.ema21_1m)}</span>
    </span>
  )
}

export function SectorBreadthTable({
  rows,
  trend = [],
}: {
  rows: SectorBreadthMVRow[]
  trend?: SectorBreadthTrendRow[]
}) {
  const trendBySector = new Map(trend.map(t => [t.sector_name, t]))
  const [sortKey, setSortKey] = useState<SortKey>('pct_above_ema21')
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')

  if (rows.length === 0) {
    return <div className="py-6 text-center font-sans text-sm text-txt-3">Breadth data unavailable.</div>
  }

  function onSort(k: SortKey) {
    if (k === sortKey) setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    else { setSortKey(k); setSortDir('desc') }
  }
  const sorted = [...rows].sort((a, b) => {
    const va = (a[sortKey] ?? -1) as number
    const vb = (b[sortKey] ?? -1) as number
    return sortDir === 'desc' ? vb - va : va - vb
  })

  function SortTh({ label, k }: { label: string; k: SortKey }) {
    const active = sortKey === k
    return (
      <th
        onClick={() => onSort(k)}
        className={`py-1.5 font-semibold cursor-pointer select-none hover:text-txt-1 ${active ? 'text-txt-1' : ''}`}
        aria-sort={active ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
      >
        {label}{active && <span className="ml-0.5">{sortDir === 'desc' ? '↓' : '↑'}</span>}
      </th>
    )
  }

  return (
    <table className="w-full text-right" data-testid="sector-breadth-table">
      <thead>
        <tr className="font-num text-[10px] text-txt-3 uppercase tracking-wider border-b border-edge-rule">
          <th className="text-left py-1.5 font-semibold">Sector</th>
          <SortTh label="Stocks" k="constituent_count" />
          <SortTh label="&gt; EMA21" k="pct_above_ema21" />
          <SortTh label="&gt; EMA50" k="pct_above_ema50" />
          <SortTh label="&gt; EMA200" k="pct_above_ema200" />
          <th className="py-1.5 font-semibold pl-4" title="% above EMA21 — now · 1w ago · 1m ago">EMA21 trend</th>
          <th className="text-left py-1.5 font-semibold pl-6">Top movers</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map(r => (
          <tr key={r.sector_name} className="border-b border-edge-hair">
            <td className="text-left py-1.5 font-sans text-xs text-txt-1">
              <a href={`/sectors/${encodeURIComponent(r.sector_name)}`} className="text-txt-1 no-underline hover:text-brand hover:underline">
                {r.sector_name}
              </a>
            </td>
            <td className="py-1.5 font-num text-[11px] tabular-nums text-txt-3">{r.constituent_count}</td>
            <td className={`py-1.5 font-num text-xs tabular-nums ${heat(r.pct_above_ema21)}`}>{pct(r.pct_above_ema21)}</td>
            <td className={`py-1.5 font-num text-xs tabular-nums ${heat(r.pct_above_ema50)}`}>{pct(r.pct_above_ema50)}</td>
            <td className={`py-1.5 font-num text-xs tabular-nums ${heat(r.pct_above_ema200)}`}>{pct(r.pct_above_ema200)}</td>
            <td className="py-1.5 pl-4 font-num text-[11px]"><Ema21Trend t={trendBySector.get(r.sector_name)} /></td>
            <td className="text-left py-1.5 pl-6">
              <span className="flex flex-wrap gap-x-2">
                {r.top_movers.slice(0, 3).map(m => (
                  <Link key={m.symbol} href={`/stocks/${encodeURIComponent(m.symbol)}`}
                    className="font-num text-[10px] tabular-nums text-sig-pos no-underline hover:underline">
                    {m.symbol} +{m.ret_pct.toFixed(1)}%
                  </Link>
                ))}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
