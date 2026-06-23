// SectorFundamentalsTable — aggregate sector fundamentals (margins, leverage) vs the
// all-stock universe. Native foundation_staging.financials_quarterly. Server component.
import type { SectorFundamentals } from '@/lib/queries/v6/sector_lens'

const pct = (v: number | null) => (v == null ? '—' : `${v.toFixed(1)}%`)
const num = (v: number | null) => (v == null ? '—' : v.toFixed(2))
// margins: higher better; leverage: lower better
const cmp = (s: number | null, u: number | null, lowerBetter = false) => {
  if (s == null || u == null) return 'text-ink-secondary'
  const better = lowerBetter ? s < u : s > u
  return better ? 'text-signal-pos' : 'text-signal-neg'
}

export function SectorFundamentalsTable({ data }: { data: SectorFundamentals }) {
  const rows = [
    { label: 'EBITDA margin', s: data.ebitda_margin, u: data.u_ebitda_margin, fmt: pct, low: false },
    { label: 'Net margin', s: data.net_margin, u: data.u_net_margin, fmt: pct, low: false },
    { label: 'Debt / equity', s: data.debt_equity, u: data.u_debt_equity, fmt: num, low: true },
  ]
  return (
    <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector fundamentals">
      <div className="mb-5">
        <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Sector fundamentals</h2>
        <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
          Constituent-average profitability and leverage (latest filed quarter) vs the all-stock universe.
          {' '}{data.n} of the sector's stocks have financials.
        </p>
      </div>
      <table className="w-full text-right max-w-[640px]">
        <thead>
          <tr className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider border-b border-paper-rule">
            <th className="text-left py-1.5 font-medium">Metric</th>
            <th className="py-1.5 font-medium">Sector</th>
            <th className="py-1.5 font-medium">Universe</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.label} className="border-b border-paper-rule/40">
              <td className="text-left py-1.5 font-sans text-xs text-ink-secondary">{r.label}</td>
              <td className={`py-1.5 font-mono text-xs tabular-nums ${cmp(r.s, r.u, r.low)}`}>{r.fmt(r.s)}</td>
              <td className="py-1.5 font-mono text-xs tabular-nums text-ink-tertiary">{r.fmt(r.u)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
