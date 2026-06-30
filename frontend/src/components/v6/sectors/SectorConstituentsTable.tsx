'use client'
// SectorConstituentsTable — every constituent of the sector in one dense, sortable table: the five
// lens deciles (cut within cap cohort), strength, leadership, returns (1M/3M), relative strength
// (vs Nifty 500 over 1M/3M/6M and vs the sector index, 3M), and liquidity. Every column sorts; each
// name links to its instrument page. All from getSectorStocks (real foundation_staging). RULE #0.
import { useState } from 'react'
import Link from 'next/link'
import type { SectorStock } from '@/lib/queries/v6/sector_lens'
import { decileColor } from '@/components/v4/ui/decile'
import { TermInfo } from '@/components/v6/shared/TermInfo'

type Kind = 'sym' | 'text' | 'decile' | 'pct' | 'num' | 'lead' | 'liq' | 'ffwt'
type Col = { key: keyof SectorStock; label: string; kind: Kind; term?: string }
const COLS: Col[] = [
  { key: 'symbol', label: 'Stock', kind: 'sym' },
  { key: 'cap', label: 'Cap', kind: 'text', term: 'cap_tier' },
  { key: 'ff_weight', label: 'FF wt', kind: 'ffwt', term: 'ff_weight' },
  { key: 'd_tech', label: 'Tch', kind: 'decile', term: 'decile' },
  { key: 'd_fund', label: 'Fnd', kind: 'decile', term: 'decile' },
  { key: 'd_cat', label: 'Cat', kind: 'decile', term: 'decile' },
  { key: 'd_flow', label: 'Flw', kind: 'decile', term: 'decile' },
  { key: 'd_val', label: 'Val', kind: 'decile', term: 'decile' },
  { key: 'strength', label: 'Str', kind: 'num', term: 'strength' },
  { key: 'lead', label: 'Lead', kind: 'lead', term: 'lead' },
  { key: 'ret_1m', label: '1M', kind: 'pct', term: 'ret_window' },
  { key: 'ret_3m', label: '3M', kind: 'pct', term: 'ret_window' },
  { key: 'rs_1m', label: 'RS 1M', kind: 'pct', term: 'rs' },
  { key: 'rs_3m', label: 'RS 3M', kind: 'pct', term: 'rs' },
  { key: 'rs_6m', label: 'RS 6M', kind: 'pct', term: 'rs' },
  { key: 'rs_sector_3m', label: 'RS Sec 3M', kind: 'pct', term: 'rs_sector' },
  { key: 'liq_cr', label: 'Liq ₹Cr', kind: 'liq' },
]

const fmtPct = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)}%`)
const pctTone = (v: number | null) => (v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg')
const fmtLiq = (v: number | null) => (v == null ? '—' : v < 10 ? v.toFixed(1) : v.toFixed(0))

function DChip({ d }: { d: number | null }) {
  if (d == null) return <span className="text-txt-3">—</span>
  // tinted text only — no pale chip fill (FM: calmer, less "Excel highlight")
  return <span className="font-num text-[10.5px] font-semibold tabular-nums" style={{ color: decileColor(d) }}>{d}</span>
}

export function SectorConstituentsTable({ stocks }: { stocks: SectorStock[] }) {
  const [sortKey, setSortKey] = useState<keyof SectorStock>('strength')
  const [dir, setDir] = useState<'asc' | 'desc'>('desc')
  if (stocks.length === 0) return <div className="py-6 text-center font-sans text-sm text-txt-3">No constituent data.</div>

  const num = (s: SectorStock, k: keyof SectorStock): number => {
    const v = s[k]
    return typeof v === 'number' ? v : -Infinity
  }
  const sorted = [...stocks].sort((a, b) => {
    if (sortKey === 'symbol' || sortKey === 'cap') {
      const av = String(a[sortKey] ?? ''), bv = String(b[sortKey] ?? '')
      return dir === 'desc' ? bv.localeCompare(av) : av.localeCompare(bv)
    }
    const d = num(a, sortKey) - num(b, sortKey)
    return dir === 'desc' ? -d : d
  })
  const onSort = (k: keyof SectorStock) => { if (k === sortKey) setDir((d) => (d === 'desc' ? 'asc' : 'desc')); else { setSortKey(k); setDir('desc') } }

  const th = 'px-2 py-1.5 font-num text-[9.5px] font-semibold uppercase tracking-wider text-txt-3 cursor-pointer select-none hover:text-txt-1 whitespace-nowrap'
  const ffCovered = stocks.filter((s) => s.ff_weight != null).length

  return (
   <div>
    <div className="overflow-x-auto rounded-tile border border-edge-hair bg-surface-panel" data-testid="sector-constituents-table">
      <table className="tbl-centered w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-edge-rule">
            {COLS.map((c) => {
              const active = sortKey === c.key
              return (
                <th key={c.key} onClick={() => onSort(c.key)}
                  className={`${th} ${c.kind === 'sym' || c.kind === 'text' ? 'text-left' : 'text-right'} ${active ? 'text-txt-1' : ''}`}>
                  {c.label}{c.term && <TermInfo term={c.term} />}{active && <span className="ml-0.5">{dir === 'desc' ? '↓' : '↑'}</span>}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <tr key={s.symbol} className="border-b border-edge-hair/60 hover:bg-surface-raised">
              {COLS.map((c) => {
                const v = s[c.key]
                if (c.kind === 'sym') return (
                  <td key={c.key} className="px-2 py-1.5 text-left">
                    <Link href={`/stocks/${s.symbol}`} className="font-num text-[12px] font-semibold text-brand hover:underline">{s.symbol}</Link>
                  </td>
                )
                if (c.kind === 'text') return <td key={c.key} className="px-2 py-1.5 text-left font-sans text-[11px] text-txt-3">{String(v ?? '—')}</td>
                if (c.kind === 'decile') return <td key={c.key} className="px-2 py-1.5 text-right"><DChip d={v as number | null} /></td>
                if (c.kind === 'num') return <td key={c.key} className="px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-1">{v == null ? '—' : (v as number).toFixed(1)}</td>
                if (c.kind === 'lead') return <td key={c.key} className="px-2 py-1.5 text-right font-num text-[11px] tabular-nums text-txt-2">{v as number}<span className="text-txt-3">/2</span></td>
                if (c.kind === 'liq') return <td key={c.key} className="px-2 py-1.5 text-right font-num text-[11px] tabular-nums text-txt-3">{fmtLiq(v as number | null)}</td>
                if (c.kind === 'ffwt') return <td key={c.key} className="px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-1">{v == null ? '—' : `${(v as number).toFixed(1)}%`}</td>
                // pct (returns / RS)
                return <td key={c.key} className={`px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums ${pctTone(v as number | null)}`}>{fmtPct(v as number | null)}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    <p className="mt-2 font-sans text-[11px] leading-[1.5] text-txt-3">
      <strong className="text-txt-2">FF wt</strong> = free-float weight within this sector’s constituents (live, un-capped) — a concentration read, <em>not</em> the NSE index weight.
      {ffCovered < stocks.length && ` Covers ${ffCovered} of ${stocks.length} names; the rest lack a market-cap or shareholding reading.`}
    </p>
   </div>
  )
}
