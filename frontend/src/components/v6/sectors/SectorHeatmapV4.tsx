'use client'

// SectorHeatmapV4 — multi-window sector return heatmap. Two grouped blocks: absolute RETURN
// and RELATIVE strength (sector minus Nifty 500), both shown as plain %. The heat tint carries
// the signal so a sector's shape reads at a glance; numbers are secondary. Click-sortable.
// Source: foundation_staging.mv_sector_cards via getSectorCards() — stored, not recomputed.

import { useState } from 'react'
import Link from 'next/link'
import type { SectorCardRow } from '@/lib/queries/v6/sectors'

type Col = { key: string; label: string; group: 'ret' | 'rs'; get: (c: SectorCardRow) => number | null; scale: number }

// Heat tint: strong enough that colour, not the number, tells the story. Values are decimal
// fractions (×100 = %); `scale` is the % magnitude that saturates the tint for that block.
function heatStyle(v: number | null, scale: number): React.CSSProperties {
  if (v == null) return { color: 'var(--color-txt-3)' }
  const mag = Math.min(Math.abs(v * 100) / scale, 1)
  const pct = Math.round((0.1 + mag * 0.55) * 100) // 10% floor so tiny moves still register
  const sig = v >= 0 ? 'var(--color-sig-pos)' : 'var(--color-sig-neg)'
  return { background: `color-mix(in srgb, ${sig} ${pct}%, transparent)` }
}

// Everything in plain %: minus sign for negatives, nothing in front of positives.
const fmt = (v: number | null) => {
  if (v == null) return '—'
  const n = v * 100
  return `${n < 0 ? '−' : ''}${Math.abs(n).toFixed(1)}%`
}

export function SectorHeatmapV4({
  cards, idxRet1dBySector,
}: { cards: SectorCardRow[]; idxRet1dBySector?: Record<string, number | null> }) {
  const COLS: Col[] = [
    { key: 'ret_1d', label: '1D', group: 'ret', get: c => idxRet1dBySector?.[c.sector_name] ?? null, scale: 3 },
    { key: 'ret_1w', label: '1W', group: 'ret', get: c => c.ret_1w, scale: 6 },
    { key: 'ret_1m', label: '1M', group: 'ret', get: c => c.ret_1m, scale: 10 },
    { key: 'ret_3m', label: '3M', group: 'ret', get: c => c.ret_3m, scale: 15 },
    { key: 'ret_6m', label: '6M', group: 'ret', get: c => c.ret_6m, scale: 22 },
    { key: 'ret_12m', label: '1Y', group: 'ret', get: c => c.ret_12m, scale: 35 },
    { key: 'rs_1m', label: '1M', group: 'rs', get: c => c.rs_1m, scale: 12 },
    { key: 'rs_3m', label: '3M', group: 'rs', get: c => c.rs_3m, scale: 15 },
    { key: 'rs_6m', label: '6M', group: 'rs', get: c => c.rs_6m, scale: 20 },
  ]
  const firstRs = COLS.findIndex(c => c.group === 'rs')
  const [sortKey, setSortKey] = useState('ret_3m')
  const [dir, setDir] = useState<1 | -1>(-1)
  if (cards.length === 0) return <div className="text-txt-3 text-sm text-center py-8">No heatmap data.</div>

  const col = COLS.find(c => c.key === sortKey)!
  const sorted = [...cards].sort((a, b) => {
    const av = col.get(a), bv = col.get(b)
    if (av == null) return 1
    if (bv == null) return -1
    return (av - bv) * dir
  })
  const onSort = (k: string) => { if (k === sortKey) setDir(d => (d === 1 ? -1 : 1)); else { setSortKey(k); setDir(-1) } }
  const arrow = (k: string) => (k === sortKey ? (dir === -1 ? ' ↓' : ' ↑') : '')

  const th = 'px-1.5 py-1.5 font-num text-[10px] font-semibold uppercase tracking-wider text-txt-3 bg-surface-raised cursor-pointer select-none hover:text-txt-1'
  const div = 'border-l border-edge-rule' // divider between the two groups

  return (
    <div className="overflow-x-auto rounded-tile border border-edge-hair bg-surface-panel">
      <table className="w-full border-collapse text-xs" data-testid="sector-heatmap-v4">
        <thead>
          {/* group header band */}
          <tr className="border-b border-edge-hair">
            <th className="bg-surface-raised" />
            <th colSpan={firstRs} className="px-2 py-1.5 text-left font-num text-[9px] font-semibold uppercase tracking-[0.14em] text-txt-2 bg-surface-raised">
              Return
            </th>
            <th colSpan={COLS.length - firstRs} className={`px-2 py-1.5 text-left font-num text-[9px] font-semibold uppercase tracking-[0.14em] text-txt-2 bg-surface-raised ${div}`}>
              vs Nifty 500
            </th>
          </tr>
          <tr className="border-b border-edge-rule">
            <th className={`text-left pl-3.5 ${th}`} onClick={() => onSort('sector_name')}>Sector</th>
            {COLS.map((c, i) => (
              <th key={c.key} className={`text-center ${th} ${i === firstRs ? div : ''}`} onClick={() => onSort(c.key)}>
                {c.label}{arrow(c.key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map(card => (
            <tr key={card.sector_name} className="border-b border-edge-hair hover:bg-surface-raised/60 transition-colors">
              <td className="text-left py-[7px] px-3.5">
                <div className="flex items-center gap-2">
                  <Link href={`/sectors/${encodeURIComponent(card.sector_name)}`}
                    className="font-medium text-txt-1 text-[12.5px] hover:text-brand transition-colors">
                    {card.sector_name}
                  </Link>
                  <span className="font-num text-[9px] text-txt-3 bg-surface-inset px-[5px] py-px rounded-tile">
                    {card.constituent_count}
                  </span>
                </div>
              </td>
              {COLS.map((c, i) => {
                const v = c.get(card)
                return (
                  <td key={c.key} className={`text-center font-num text-[11.5px] tabular-nums ${i === firstRs ? div : ''}`} style={heatStyle(v, c.scale)}>
                    <div className="px-1.5 py-[7px]">{fmt(v)}</div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
