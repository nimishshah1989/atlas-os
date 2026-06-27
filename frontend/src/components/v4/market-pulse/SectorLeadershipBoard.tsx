'use client'
// Sector leadership — concise Leading/Lagging summary where every sector EXPANDS into the
// breakdown behind its score: a table of the sector's stocks scored across all five lenses.
// This is the core "see why, then drill in" interaction — summary up top, full evidence on click.
import { useState } from 'react'
import Link from 'next/link'
import { DecileMeter } from '../ui/DecileMeter'
import { decileColor } from '../ui/decile'
import { TermInfo } from '@/components/v6/shared/TermInfo'

export type SectorRollup = {
  name: string; avg: number; n: number; techLeaders: number; fundLeaders: number
  rs_1w: number | null; rs_1m: number | null; rs_3m: number | null   // sector index vs Nifty 50 (fractions)
  ema21: number | null; ema50: number | null; emaTotal: number | null // # constituents above EMA21/EMA50, of emaTotal
}
export type StockLensRow = {
  symbol: string
  name: string | null
  d_tech: number | null
  d_fund: number | null
  d_cat: number | null
  d_flow: number | null
  d_val: number | null
  lead: number
  strength: number | null
}

const LENSES: Array<[keyof StockLensRow, string]> = [
  ['d_tech', 'Technical'],
  ['d_fund', 'Fundamental'],
  ['d_cat', 'Catalyst'],
  ['d_flow', 'Flow'],
  ['d_val', 'Value'],
]

function DChip({ d }: { d: number | null }) {
  if (d == null) return <span className="font-num text-[11px] text-txt-3">—</span>
  return (
    <span
      className="inline-block rounded px-1.5 py-0.5 font-num text-[11px] font-medium tabular-nums"
      style={{ background: `color-mix(in srgb, ${decileColor(d)} 22%, transparent)`, color: decileColor(d) }}
    >
      D{d}
    </span>
  )
}

function SectorBreakdown({ name, stocks }: { name: string; stocks: StockLensRow[] }) {
  const sorted = [...stocks].sort((a, b) => (b.strength ?? 0) - (a.strength ?? 0))
  return (
    <div className="mt-2 mb-3 overflow-x-auto rounded-tile border border-edge-rule bg-surface-base/60">
      <div className="flex items-center justify-between px-3 pt-2.5">
        <span className="font-sans text-[12px] text-txt-2">
          <span className="font-medium text-txt-1">{name}</span> — every stock’s decile (1–10) per lens. Higher = stronger; click a name to open it.
        </span>
        <Link href={`/sectors/${encodeURIComponent(name)}`} className="shrink-0 font-num text-[11px] text-brand hover:underline">Open sector →</Link>
      </div>
      <table className="mt-1.5 w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-hair">
            <th className="px-3 py-1.5 text-left font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3">Stock</th>
            {LENSES.map(([, label]) => (
              <th key={label} className="px-2 py-1.5 text-right font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3">{label}<TermInfo term="decile" /></th>
            ))}
            <th className="px-3 py-1.5 text-right font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3">Leads<TermInfo term="lead" /></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <tr key={s.symbol} className="border-b border-edge-hair/50 last:border-0 hover:bg-surface-raised">
              <td className="px-3 py-1.5">
                <Link href={`/stocks/${s.symbol}`} className="font-num text-[12px] font-medium text-txt-1 hover:text-brand">{s.symbol}</Link>
                {s.name && <span className="ml-1.5 hidden truncate font-sans text-[11px] text-txt-3 sm:inline">{s.name}</span>}
              </td>
              {LENSES.map(([k]) => (
                <td key={k} className="px-2 py-1.5 text-right"><DChip d={s[k] as number | null} /></td>
              ))}
              <td className="px-3 py-1.5 text-right font-num text-[11px] tabular-nums text-txt-2">{s.lead}<span className="text-txt-3">/4</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// RS (sector index vs Nifty 50) and EMA-participation formatting.
const fmtRS = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)}`)
const rsTone = (v: number | null) => (v == null ? 'text-txt-3' : v > 0.0005 ? 'text-sig-pos' : v < -0.0005 ? 'text-sig-neg' : 'text-txt-2')
const fmtEma = (c: number | null, tot: number | null) => (c == null ? '—' : tot != null ? `${c}/${tot}` : `${c}`)

const NUM_TH = 'px-2 py-1 text-right font-num text-[9px] font-medium uppercase tracking-[0.1em] text-txt-3'

function SectorRow({ s, open, onToggle }: { s: SectorRollup; open: boolean; onToggle: () => void }) {
  const tone = s.avg >= 6 ? 'var(--color-sig-pos)' : s.avg < 4 ? 'var(--color-sig-neg)' : 'var(--color-txt-1)'
  return (
    <tr onClick={onToggle} aria-expanded={open}
      className={`cursor-pointer border-b border-edge-hair/60 transition-colors hover:bg-surface-raised ${open ? 'bg-surface-raised' : ''}`}>
      <td className="px-2 py-1.5">
        <span className="flex items-center gap-1.5 truncate font-sans text-[12.5px] font-medium text-txt-1">
          <span className="font-num text-[10px] text-txt-3">{open ? '▾' : '▸'}</span>{s.name}
        </span>
      </td>
      <td className="px-2 py-1.5">
        <span className="flex items-center justify-end gap-1.5">
          <DecileMeter decile={Math.round(s.avg)} size="sm" />
          <span className="w-[34px] shrink-0 text-right font-num text-[12px] tabular-nums" style={{ color: tone }}>{s.avg.toFixed(1)}</span>
        </span>
      </td>
      <td className={`px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums ${rsTone(s.rs_1w)}`}>{fmtRS(s.rs_1w)}</td>
      <td className={`px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums ${rsTone(s.rs_1m)}`}>{fmtRS(s.rs_1m)}</td>
      <td className={`px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums ${rsTone(s.rs_3m)}`}>{fmtRS(s.rs_3m)}</td>
      <td className="px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-2">{fmtEma(s.ema21, s.emaTotal)}</td>
      <td className="px-2 py-1.5 text-right font-num text-[11.5px] tabular-nums text-txt-2">{fmtEma(s.ema50, s.emaTotal)}</td>
    </tr>
  )
}

function SectorTable({ rows, open, toggle }: { rows: SectorRollup[]; open: string | null; toggle: (n: string) => void }) {
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-edge-rule">
          <th className="px-2 py-1 text-left font-num text-[9px] font-medium uppercase tracking-[0.1em] text-txt-3">Sector</th>
          <th className={NUM_TH}>Conviction<TermInfo term="strength" /></th>
          <th className={NUM_TH} title="Sector index vs Nifty 50, 1 week">RS 1W<TermInfo term="rs" /></th>
          <th className={NUM_TH} title="Sector index vs Nifty 50, 1 month">RS 1M<TermInfo term="rs" /></th>
          <th className={NUM_TH} title="Sector index vs Nifty 50, 3 months">RS 3M<TermInfo term="rs" /></th>
          <th className={NUM_TH} title="Constituents above their 21-EMA">&gt;EMA21<TermInfo term="above_ema_count" /></th>
          <th className={NUM_TH} title="Constituents above their 50-EMA">&gt;EMA50<TermInfo term="above_ema_count" /></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => <SectorRow key={s.name} s={s} open={open === s.name} onToggle={() => toggle(s.name)} />)}
      </tbody>
    </table>
  )
}

export function SectorLeadershipBoard({
  top,
  weak,
  stocksBySector,
}: {
  top: SectorRollup[]
  weak: SectorRollup[]
  stocksBySector: Record<string, StockLensRow[]>
}) {
  const [open, setOpen] = useState<string | null>(null)
  const toggle = (n: string) => setOpen((cur) => (cur === n ? null : n))
  return (
    <div className="space-y-4">
      <div>
        <p className="mb-1 font-num text-[9px] uppercase tracking-[0.14em] text-sig-pos">Leading · strongest conviction</p>
        <SectorTable rows={top} open={open} toggle={toggle} />
      </div>
      <div>
        <p className="mb-1 font-num text-[9px] uppercase tracking-[0.14em] text-sig-neg">Lagging · weakest conviction</p>
        <SectorTable rows={weak} open={open} toggle={toggle} />
      </div>
      <p className="font-num text-[9.5px] text-txt-3">
        Conviction = avg constituent decile (1–10). RS = sector index minus Nifty 50 over each window (% pts).
        &gt;EMA21 / &gt;EMA50 = constituents above that EMA, of the sector’s tracked count. Click a row for the per-stock decile breakdown.
      </p>
      {open && <SectorBreakdown name={open} stocks={stocksBySector[open] ?? []} />}
    </div>
  )
}
