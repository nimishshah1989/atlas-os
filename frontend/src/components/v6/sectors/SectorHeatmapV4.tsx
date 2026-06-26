'use client'

// SectorHeatmapV4 — multi-window sector return/RS heatmap, click-sortable on every column,
// verdict + signal-confidence columns dropped (v4 strips the conviction cruft). Numbers shown
// with a continuous RAG heat tint. Source: foundation_staging.mv_sector_cards via getSectorCards().

import { useState } from 'react'
import Link from 'next/link'
import type { SectorCardRow } from '@/lib/queries/v6/sectors'

type Col = { key: string; label: string; sub: string; get: (c: SectorCardRow) => number | null; unit: '%' | 'pp' }

// RAG heat tint. BOTH units are stored as decimal FRACTIONS (×100 → display):
//   '%'  absolute return, normalised over ±10%.
//   'pp' relative strength = sector return − Nifty 500 return, normalised over ±15pp.
function heatStyle(v: number | null, unit: '%' | 'pp'): React.CSSProperties {
  if (v == null) return { color: 'var(--color-txt-3)' }
  const mag = unit === '%' ? Math.abs(v * 100) / 10 : Math.abs(v * 100) / 15
  const a = (Math.min(mag, 1) * 0.36).toFixed(2)
  const sig = v >= 0 ? 'var(--color-sig-pos)' : 'var(--color-sig-neg)'
  return { background: `color-mix(in srgb, ${sig} ${Math.round(parseFloat(a) * 100)}%, transparent)` }
}

// Both RETURN and RS columns are decimal fractions in the MV → ×100 for display.
// '%' = absolute return; 'pp' = relative strength (sector minus Nifty 500), in points.
const fmt = (v: number | null, unit: '%' | 'pp') => {
  if (v == null) return '—'
  const n = v * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}${unit}`
}

export function SectorHeatmapV4({
  cards, idxRet1dBySector,
}: { cards: SectorCardRow[]; idxRet1dBySector?: Record<string, number | null> }) {
  const COLS: Col[] = [
    { key: 'ret_1d', label: '1D', sub: 'idx', get: c => idxRet1dBySector?.[c.sector_name] ?? null, unit: '%' },
    { key: 'ret_1w', label: '1W', sub: 'abs', get: c => c.ret_1w, unit: '%' },
    { key: 'ret_1m', label: '1M', sub: 'abs', get: c => c.ret_1m, unit: '%' },
    { key: 'ret_3m', label: '3M', sub: 'abs', get: c => c.ret_3m, unit: '%' },
    { key: 'ret_6m', label: '6M', sub: 'abs', get: c => c.ret_6m, unit: '%' },
    { key: 'ret_12m', label: '12M', sub: 'abs', get: c => c.ret_12m, unit: '%' },
    { key: 'rs_1m', label: 'RS 1M', sub: 'pp', get: c => c.rs_1m, unit: 'pp' },
    { key: 'rs_3m', label: 'RS 3M', sub: 'pp', get: c => c.rs_3m, unit: 'pp' },
    { key: 'rs_6m', label: 'RS 6M', sub: 'pp', get: c => c.rs_6m, unit: 'pp' },
  ]
  const [sortKey, setSortKey] = useState('rs_3m')
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

  const th = "px-1.5 py-2 font-num text-[9px] font-semibold uppercase tracking-wider text-txt-3 bg-surface-raised border-b border-edge-rule cursor-pointer select-none hover:text-txt-1"

  return (
    <div className="overflow-x-auto rounded-tile border border-edge-hair bg-surface-panel">
      <table className="w-full border-collapse text-xs" data-testid="sector-heatmap-v4">
        <thead>
          <tr>
            <th className={`text-left pl-3.5 ${th}`} onClick={() => onSort('sector_name')}>Sector</th>
            {COLS.map(c => (
              <th key={c.key} className={`text-center ${th}`} onClick={() => onSort(c.key)}>
                {c.label}{arrow(c.key)}
                <span className="block font-num text-[8px] text-txt-3 tracking-normal normal-case mt-0.5">{c.sub}</span>
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
              {COLS.map(c => {
                const v = c.get(card)
                return (
                  <td key={c.key} className="text-center font-num text-[11.5px] tabular-nums border-b border-edge-hair" style={heatStyle(v, c.unit)}>
                    <div className="px-1 py-[7px]">{fmt(v, c.unit)}</div>
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
