// BreadthDetailTable — the detailed 9-row breadth table for Markets Today (Nifty 500).
// Native data from foundation_staging.atlas_market_regime_daily via getBreadthTable(). Server component.
import type { BreadthTableRow } from '@/lib/queries/v6/market_pulse'

function fmtVal(r: BreadthTableRow): string {
  if (r.today == null) return '—'
  switch (r.kind) {
    case 'pct': return `${(r.today * 100).toFixed(0)}%`
    case 'count': return `${Math.round(r.today)}`
    case 'ratio': return r.today.toFixed(2)
    case 'signed': return `${r.today >= 0 ? '+' : ''}${Math.round(r.today)}`
  }
}
function fmtDelta(v: number | null, kind: BreadthTableRow['kind']): string {
  if (v == null) return '—'
  if (kind === 'pct') return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}pp`
  if (kind === 'ratio') return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
  return `${v >= 0 ? '+' : ''}${Math.round(v)}`
}
const dcol = (v: number | null) =>
  v == null ? 'text-ink-tertiary' : v > 0 ? 'text-signal-pos' : v < 0 ? 'text-signal-neg' : 'text-ink-secondary'

export function BreadthDetailTable({ rows, as_of }: { rows: BreadthTableRow[]; as_of: string | null }) {
  if (rows.length === 0) return null
  return (
    <section className="px-6 py-5 border-b border-paper-rule">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          Market breadth · Nifty 500 (detail)
        </h2>
        {as_of && <span className="font-sans text-[10px] text-ink-tertiary">as of {as_of}</span>}
      </div>
      <table className="w-full text-right">
        <thead>
          <tr className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider border-b border-paper-rule">
            <th className="text-left py-1.5 font-medium">Metric</th>
            <th className="py-1.5 font-medium">Today</th>
            <th className="py-1.5 font-medium">Δ 1w</th>
            <th className="py-1.5 font-medium">Δ 1m</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.metric} className="border-b border-paper-rule/40">
              <td className="text-left py-1.5 font-sans text-xs text-ink-secondary">{r.label}</td>
              <td className="py-1.5 font-mono text-xs tabular-nums text-ink-primary">{fmtVal(r)}</td>
              <td className={`py-1.5 font-mono text-[11px] tabular-nums ${dcol(r.d1w)}`}>{fmtDelta(r.d1w, r.kind)}</td>
              <td className={`py-1.5 font-mono text-[11px] tabular-nums ${dcol(r.d1m)}`}>{fmtDelta(r.d1m, r.kind)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
