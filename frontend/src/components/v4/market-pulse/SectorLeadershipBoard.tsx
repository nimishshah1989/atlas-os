'use client'
// Sector leadership — concise Leading/Lagging summary where every sector EXPANDS into the
// breakdown behind its score: a table of the sector's stocks scored across all five lenses.
// This is the core "see why, then drill in" interaction — summary up top, full evidence on click.
import { useState } from 'react'
import Link from 'next/link'
import { DecileMeter } from '../ui/DecileMeter'
import { decileColor } from '../ui/decile'

export type SectorRollup = { name: string; avg: number; n: number; techLeaders: number; fundLeaders: number }
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
              <th key={label} className="px-2 py-1.5 text-right font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3">{label}</th>
            ))}
            <th className="px-3 py-1.5 text-right font-num text-[9px] font-medium uppercase tracking-[0.12em] text-txt-3">Leads</th>
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

function SectorRow({ s, open, onToggle }: { s: SectorRollup; open: boolean; onToggle: () => void }) {
  const tone = s.avg >= 6 ? 'var(--color-sig-pos)' : s.avg < 4 ? 'var(--color-sig-neg)' : 'var(--color-txt-1)'
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={`-mx-2 block w-full rounded-tile px-2 py-1.5 text-left transition-colors hover:bg-surface-raised ${open ? 'bg-surface-raised' : ''}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5 truncate font-sans text-[12.5px] font-medium text-txt-1">
          <span className="font-num text-[10px] text-txt-3">{open ? '▾' : '▸'}</span>{s.name}
        </span>
        <span className="shrink-0 font-num text-[12px] tabular-nums" style={{ color: tone }}>{s.avg.toFixed(1)}<span className="text-[10px] text-txt-3">/10</span></span>
      </div>
      <div className="mt-1 flex items-center gap-2 pl-3.5">
        <DecileMeter decile={Math.round(s.avg)} size="sm" />
        <span className="shrink-0 font-num text-[10px] tabular-nums text-txt-3">{s.techLeaders} tech · {s.fundLeaders} fund · of {s.n}</span>
      </div>
    </button>
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
    <div>
      <div className="grid grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-2">
        <div>
          <p className="mb-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-sig-pos">Leading</p>
          {top.map((s) => <SectorRow key={s.name} s={s} open={open === s.name} onToggle={() => toggle(s.name)} />)}
        </div>
        <div>
          <p className="mb-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-sig-neg">Lagging</p>
          {weak.map((s) => <SectorRow key={s.name} s={s} open={open === s.name} onToggle={() => toggle(s.name)} />)}
        </div>
      </div>
      {open && <SectorBreakdown name={open} stocks={stocksBySector[open] ?? []} />}
    </div>
  )
}
