// MacroContextTable — macro context for Markets Today (USD/INR, yields, Brent, DXY, FII/DII).
// Native data from foundation_staging.atlas_macro_daily via getMacroContext(). Server component.
import type { MacroRow } from '@/lib/queries/v6/market_pulse'

function fmtVal(r: MacroRow): string {
  if (r.value == null) return '—'
  if (r.unit === '%') return `${r.value.toFixed(2)}%`
  if (r.unit === '₹') return `₹${r.value.toFixed(0)}`
  if (r.unit === '₹cr') return `${r.value >= 0 ? '+' : ''}${Math.round(r.value).toLocaleString('en-IN')}`
  return r.value.toFixed(2)
}
const dcol = (v: number | null) =>
  v == null ? 'text-ink-tertiary' : v > 0 ? 'text-signal-pos' : v < 0 ? 'text-signal-neg' : 'text-ink-secondary'
const fmtD = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2)}`)

export function MacroContextTable({ rows, as_of }: { rows: MacroRow[]; as_of: string | null }) {
  if (rows.length === 0) return null
  return (
    <section className="px-6 py-5 border-b border-paper-rule">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">Macro context</h2>
        {as_of && <span className="font-sans text-[10px] text-ink-tertiary">as of {as_of}</span>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
        {[rows.slice(0, 4), rows.slice(4)].map((half, hi) => (
          <table key={hi} className="w-full text-right">
            <thead>
              <tr className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider border-b border-paper-rule">
                <th className="text-left py-1.5 font-medium">Indicator</th>
                <th className="py-1.5 font-medium">Value</th>
                <th className="py-1.5 font-medium">Δ 1d</th>
                <th className="py-1.5 font-medium">Δ 1m</th>
              </tr>
            </thead>
            <tbody>
              {half.map(r => (
                <tr key={r.id} className="border-b border-paper-rule/40">
                  <td className="text-left py-1.5 font-sans text-xs text-ink-secondary">{r.label}</td>
                  <td className="py-1.5 font-mono text-xs tabular-nums text-ink-primary">{fmtVal(r)}</td>
                  <td className={`py-1.5 font-mono text-[11px] tabular-nums ${dcol(r.d1)}`}>{fmtD(r.d1)}</td>
                  <td className={`py-1.5 font-mono text-[11px] tabular-nums ${dcol(r.d1m)}`}>{fmtD(r.d1m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      </div>
    </section>
  )
}
