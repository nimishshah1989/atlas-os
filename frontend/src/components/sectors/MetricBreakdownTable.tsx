'use client'
// A sector-metric table where every metric row is CLICKABLE to drill into the
// "within the sector" view — each constituent's own value for that metric, sorted, with a
// proportional bar and a link to the stock. Generic so both Sector fundamentals and Sector
// fund-flow reuse it. All values are real, passed down from the server query.
import { Fragment, useState } from 'react'
import Link from 'next/link'
import { TermInfo } from '@/components/shared/TermInfo'

export type BreakdownItem = { symbol: string; value: number | null; note?: string }
// Formatters live HERE (the client side), keyed by a string — server components can't
// pass functions across the RSC boundary, so they pass a `format` discriminator instead.
export type MetricFormat = 'pct' | 'signed' | 'num0'
const FMT: Record<MetricFormat, (v: number | null) => string> = {
  pct: (v) => (v == null ? '—' : `${v.toFixed(1)}%`),
  signed: (v) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`),
  num0: (v) => (v == null ? '—' : v.toFixed(0)),
}
export type MetricRow = {
  key: string
  label: string
  term?: string
  sector: number | null
  universe: number | null
  format: MetricFormat
  lowerBetter?: boolean
  kind?: 'bar' | 'flag' // 'flag' = a binary good/bad chip (e.g. profitable / loss)
  breakdown: BreakdownItem[]
}

const cmpClass = (s: number | null, u: number | null, lower = false) => {
  if (s == null || u == null) return 'text-txt-2'
  return (lower ? s < u : s > u) ? 'text-sig-pos' : 'text-sig-neg'
}

function Breakdown({ row }: { row: MetricRow }) {
  const fmt = FMT[row.format]
  const items = row.breakdown
  if (items.length === 0) return <p className="font-sans text-[11px] text-txt-3">No constituent data.</p>
  const present = items.filter((i) => i.value != null) as { symbol: string; value: number; note?: string }[]
  const maxAbs = Math.max(1, ...present.map((i) => Math.abs(i.value)))
  return (
    <div>
      <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3 mb-2">
        Within the sector · {present.length} constituent{present.length === 1 ? '' : 's'} · highest first
      </p>
      <div className="max-h-[280px] overflow-y-auto pr-1 space-y-[3px]">
        {items.map((i) => {
          const v = i.value
          const pos = v == null ? false : v >= 0
          return (
            <div key={i.symbol} className="flex items-center gap-2 font-num text-[11px] tabular-nums">
              <Link
                href={`/stocks/${i.symbol}`}
                className="w-[92px] shrink-0 truncate text-left font-sans text-txt-2 hover:text-brand no-underline"
                title={i.symbol}
              >
                {i.symbol}
              </Link>
              {row.kind === 'flag' ? (
                <span className={`flex-1 text-left ${pos ? 'text-sig-pos' : 'text-sig-neg'}`}>
                  <span className="inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle" style={{ background: 'currentColor' }} />
                  {i.note ?? (pos ? 'Yes' : 'No')}
                </span>
              ) : (
                <>
                  <span className="flex-1 h-[10px] bg-surface-raised rounded-sm overflow-hidden flex">
                    {v != null && (
                      <span
                        className={`h-full rounded-sm ${pos ? 'bg-sig-pos/55' : 'bg-sig-neg/55'}`}
                        style={{ width: `${(Math.abs(v) / maxAbs) * 100}%` }}
                      />
                    )}
                  </span>
                  <span className={`w-[60px] shrink-0 text-right ${v == null ? 'text-txt-3' : pos ? 'text-txt-1' : 'text-sig-neg'}`}>
                    {fmt(v)}
                  </span>
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function MetricBreakdownTable({ title, subtitle, footnote, rows }: { title: string; subtitle: string; footnote?: string; rows: MetricRow[] }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <div>
      <div className="mb-4">
        <h2 className="font-display text-[24px] font-normal tracking-tight text-txt-1">{title}</h2>
        <p className="font-sans text-[12.5px] text-txt-3 max-w-[540px] leading-[1.45] mt-1">{subtitle}</p>
      </div>
      <table className="tbl-centered w-full text-right">
        <thead>
          <tr className="font-num text-[10px] text-txt-3 uppercase tracking-wider border-b border-edge-hair">
            <th className="text-left py-1.5 font-medium">Metric</th>
            <th className="py-1.5 font-medium">Sector</th>
            <th className="py-1.5 font-medium">Universe</th>
            <th className="py-1.5 font-medium w-5" aria-label="expand" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const isOpen = open === r.key
            const fmt = FMT[r.format]
            return (
              <Fragment key={r.key}>
                <tr
                  className="border-b border-edge-hair cursor-pointer hover:bg-surface-inset/50"
                  onClick={() => setOpen(isOpen ? null : r.key)}
                  aria-expanded={isOpen}
                >
                  <td className="text-left py-1.5 font-sans text-xs text-txt-2">
                    {r.label}
                    {r.term && <TermInfo term={r.term} />}
                  </td>
                  <td className={`py-1.5 font-num text-xs tabular-nums ${cmpClass(r.sector, r.universe, r.lowerBetter)}`}>{fmt(r.sector)}</td>
                  <td className="py-1.5 font-num text-xs tabular-nums text-txt-3">{r.universe == null ? '—' : fmt(r.universe)}</td>
                  <td className="py-1.5 text-txt-3 text-[9px] text-center select-none">{isOpen ? '▾' : '▸'}</td>
                </tr>
                {isOpen && (
                  <tr className="border-b border-edge-hair bg-surface-inset/30">
                    <td colSpan={4} className="py-3 px-2">
                      <Breakdown row={r} />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
      {footnote && <p className="font-sans text-[11px] text-txt-3 mt-3 max-w-[540px] leading-[1.5]">{footnote}</p>}
    </div>
  )
}
