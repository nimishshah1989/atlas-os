'use client'

// SectorHeatmapV4 — multi-window sector return heatmap. Two grouped blocks: absolute RETURN
// and RELATIVE strength (sector minus a selectable base index). Both shown as plain %. The heat
// tint carries the signal so a sector's shape reads at a glance; numbers are secondary. The base
// (Nifty 50 / Nifty 500) toggles client-side — RS recomputes with no refetch. Click-sortable.
//
// Source: sector-INDEX returns from atlas_index_metrics_daily (native, calendar-anchored) via
// getSectorIndexRs — NOT mv_sector_cards, whose bottom-up return columns were corrupt/inflated.

import { useState } from 'react'
import Link from 'next/link'
import type { SectorConstituentMatrixRow } from '@/lib/queries/v6/sectors'
import { TermInfo } from '@/components/v6/shared/TermInfo'

// The return windows every matrix row carries — a sector index OR one of its constituents — so
// the column getters work for both and a constituent renders in the SAME columns as its sector.
type RetRow = {
  ret_1d: number | null; ret_1w: number | null; ret_1m: number | null
  ret_3m: number | null; ret_6m: number | null; ret_12m: number | null
}

// Returns are decimal fractions (×100 = %). RS is computed here = sector return − base return.
export type SectorHeatRow = RetRow & {
  sector_name: string
  constituent_count: number
}

export type BaseRet = { ret_1m: number | null; ret_3m: number | null; ret_6m: number | null }
export type BaseKey = 'NIFTY 50' | 'NIFTY 500'
const BASE_LABEL: Record<BaseKey, string> = { 'NIFTY 50': 'Nifty 50', 'NIFTY 500': 'Nifty 500' }

type Col = { key: string; label: string; group: 'ret' | 'rs'; get: (c: RetRow) => number | null; scale: number; term?: string }

// Heat tint: strong enough that colour, not the number, tells the story. `scale` is the %
// magnitude that saturates the tint for that block.
function heatStyle(v: number | null, scale: number): React.CSSProperties {
  if (v == null) return { color: 'var(--color-txt-3)' }
  const mag = Math.min(Math.abs(v * 100) / scale, 1)
  const pct = Math.round((0.1 + mag * 0.55) * 100) // 10% floor so tiny moves still register
  const sig = v >= 0 ? 'var(--color-sig-pos)' : 'var(--color-sig-neg)'
  return { background: `color-mix(in srgb, ${sig} ${pct}%, transparent)` }
}

// Plain %: minus sign for negatives, nothing in front of positives.
const fmt = (v: number | null) => {
  if (v == null) return '—'
  const n = v * 100
  return `${n < 0 ? '−' : ''}${Math.abs(n).toFixed(1)}%`
}

const rel = (a: number | null, b: number | null) => (a != null && b != null ? a - b : null)

export function SectorHeatmapV4({ rows, bases, constituents }: {
  rows: SectorHeatRow[]
  bases: Record<BaseKey, BaseRet>
  constituents?: Record<string, SectorConstituentMatrixRow[]>
}) {
  const [base, setBase] = useState<BaseKey>('NIFTY 500')
  const [sortKey, setSortKey] = useState('ret_3m')
  const [dir, setDir] = useState<1 | -1>(-1)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const toggle = (name: string) => setOpen((s) => { const n = new Set(s); n.has(name) ? n.delete(name) : n.add(name); return n })

  const b = bases[base]
  const COLS: Col[] = [
    { key: 'ret_1d', label: '1D', group: 'ret', get: c => c.ret_1d, scale: 3, term: 'ret_window' },
    { key: 'ret_1w', label: '1W', group: 'ret', get: c => c.ret_1w, scale: 6, term: 'ret_window' },
    { key: 'ret_1m', label: '1M', group: 'ret', get: c => c.ret_1m, scale: 10, term: 'ret_window' },
    { key: 'ret_3m', label: '3M', group: 'ret', get: c => c.ret_3m, scale: 15, term: 'ret_window' },
    { key: 'ret_6m', label: '6M', group: 'ret', get: c => c.ret_6m, scale: 22, term: 'ret_window' },
    { key: 'ret_12m', label: '1Y', group: 'ret', get: c => c.ret_12m, scale: 35, term: 'ret_window' },
    { key: 'rs_1m', label: '1M', group: 'rs', get: c => rel(c.ret_1m, b.ret_1m), scale: 12, term: 'rs' },
    { key: 'rs_3m', label: '3M', group: 'rs', get: c => rel(c.ret_3m, b.ret_3m), scale: 15, term: 'rs' },
    { key: 'rs_6m', label: '6M', group: 'rs', get: c => rel(c.ret_6m, b.ret_6m), scale: 20, term: 'rs' },
  ]
  const firstRs = COLS.findIndex(c => c.group === 'rs')
  if (rows.length === 0) return <div className="text-txt-3 text-sm text-center py-8">No heatmap data.</div>

  const col = COLS.find(c => c.key === sortKey)!
  const cmp = (a: RetRow, b2: RetRow) => {
    const av = col.get(a), bv = col.get(b2)
    if (av == null) return 1
    if (bv == null) return -1
    return (av - bv) * dir
  }
  const sorted = [...rows].sort(cmp)
  const onSort = (k: string) => { if (k === sortKey) setDir(d => (d === 1 ? -1 : 1)); else { setSortKey(k); setDir(-1) } }
  const arrow = (k: string) => (k === sortKey ? (dir === -1 ? ' ↓' : ' ↑') : '')

  const th = 'px-1.5 py-1.5 font-num text-[10px] font-semibold uppercase tracking-wider text-txt-3 bg-surface-raised cursor-pointer select-none hover:text-txt-1'
  const divCls = 'border-l border-edge-rule' // divider between the two groups

  return (
    <div>
      {/* base toggle — drives the "vs base" RS block */}
      <div className="mb-2 flex items-center gap-2 px-1.5">
        <span className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Relative to</span>
        <div className="inline-flex rounded-tile border border-edge-rule bg-surface-inset p-0.5">
          {(Object.keys(BASE_LABEL) as BaseKey[]).map((k) => (
            <button key={k} type="button" onClick={() => setBase(k)}
              className={`font-num text-[10px] px-2 py-0.5 rounded-tile transition-colors ${base === k ? 'bg-surface-raised text-txt-1 font-semibold' : 'text-txt-3 hover:text-txt-1'}`}>
              {BASE_LABEL[k]}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-tile border border-edge-hair bg-surface-panel">
        <table className="w-full border-collapse text-xs" data-testid="sector-heatmap-v4">
          <thead>
            {/* group header band */}
            <tr className="border-b border-edge-hair">
              <th className="bg-surface-raised" />
              <th colSpan={firstRs} className="px-2 py-1.5 text-left font-num text-[9px] font-semibold uppercase tracking-[0.14em] text-txt-2 bg-surface-raised">
                Return
              </th>
              <th colSpan={COLS.length - firstRs} className={`px-2 py-1.5 text-left font-num text-[9px] font-semibold uppercase tracking-[0.14em] text-txt-2 bg-surface-raised ${divCls}`}>
                vs {BASE_LABEL[base]}
              </th>
            </tr>
            <tr className="border-b border-edge-rule">
              <th className={`text-left pl-3.5 ${th}`} onClick={() => onSort('sector_name')}>Sector</th>
              {COLS.map((c, i) => (
                <th key={c.key} className={`text-center ${th} ${i === firstRs ? divCls : ''}`} onClick={() => onSort(c.key)}>
                  {c.label}{c.term && <TermInfo term={c.term} />}{arrow(c.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map(card => {
              const kids = constituents?.[card.sector_name]
              const canExpand = !!kids?.length
              const isOpen = open.has(card.sector_name)
              return (
                <tr key={card.sector_name} className="border-b border-edge-hair hover:bg-surface-raised/60 transition-colors">
                  <td className="text-left py-[7px] px-3.5">
                    <div className="flex items-center gap-1.5">
                      {canExpand ? (
                        <button type="button" onClick={() => toggle(card.sector_name)} aria-expanded={isOpen}
                          aria-label={isOpen ? `Collapse ${card.sector_name}` : `Expand ${card.sector_name} constituents`}
                          className="w-[14px] shrink-0 font-num text-[10px] text-txt-3 hover:text-txt-1 transition-colors">
                          {isOpen ? '▾' : '▸'}
                        </button>
                      ) : <span className="w-[14px] shrink-0" />}
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
                      <td key={c.key} className={`text-center font-num text-[11.5px] tabular-nums ${i === firstRs ? divCls : ''}`} style={heatStyle(v, c.scale)}>
                        <div className="px-1.5 py-[7px]">{fmt(v)}</div>
                      </td>
                    )
                  })}
                </tr>
              )
            }).flatMap((row, idx) => {
              // splice each sector's constituent sub-rows (when open) directly under it, in the SAME columns.
              const card = sorted[idx]
              const kids = constituents?.[card.sector_name]
              if (!open.has(card.sector_name) || !kids?.length) return [row]
              const subRows = [...kids].sort(cmp).map((s) => (
                <tr key={`${card.sector_name}::${s.symbol}`} className="border-b border-edge-hair/60 bg-surface-inset/40">
                  <td className="text-left py-[5px] pl-[34px] pr-3.5">
                    <Link href={`/stocks/${s.symbol}`} className="font-num text-[11.5px] text-txt-2 hover:text-brand transition-colors">
                      {s.symbol}
                    </Link>
                  </td>
                  {COLS.map((c, i) => {
                    const v = c.get(s)
                    return (
                      <td key={c.key} className={`text-center font-num text-[11px] tabular-nums ${i === firstRs ? divCls : ''}`} style={heatStyle(v, c.scale)}>
                        <div className="px-1.5 py-[5px]">{fmt(v)}</div>
                      </td>
                    )
                  })}
                </tr>
              ))
              return [row, ...subRows]
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
