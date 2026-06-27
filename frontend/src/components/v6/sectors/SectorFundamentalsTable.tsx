// SectorFundamentalsTable — aggregate sector fundamentals (margins, leverage) vs the
// all-stock universe. Native foundation_staging.financials_quarterly. Server component.
import type { SectorFundamentals } from '@/lib/queries/v6/sector_lens'
import { TermInfo } from '@/components/v6/shared/TermInfo'

const pct = (v: number | null) => (v == null ? '—' : `${v.toFixed(1)}%`)
const num = (v: number | null) => (v == null ? '—' : v.toFixed(2))
// margins: higher better; leverage: lower better
const cmp = (s: number | null, u: number | null, lowerBetter = false) => {
  if (s == null || u == null) return 'text-txt-2'
  const better = lowerBetter ? s < u : s > u
  return better ? 'text-sig-pos' : 'text-sig-neg'
}

export function SectorFundamentalsTable({ data }: { data: SectorFundamentals }) {
  const rows = [
    { label: 'EBITDA margin', s: data.ebitda_margin, u: data.u_ebitda_margin, fmt: pct, low: false, term: 'ebitda_margin' },
    { label: 'Net margin', s: data.net_margin, u: data.u_net_margin, fmt: pct, low: false, term: 'net_margin' },
    { label: 'Debt / equity', s: data.debt_equity, u: data.u_debt_equity, fmt: num, low: true, term: 'debt_equity' },
  ]
  return (
    <section className="px-8 py-10 border-b border-edge-hair" aria-label="Sector fundamentals">
      <div className="mb-5">
        <h2 className="font-display text-[28px] font-normal tracking-tight text-txt-1">Sector fundamentals</h2>
        <p className="font-sans text-[13px] text-txt-3 max-w-[760px] leading-[1.45] mt-1">
          Constituent-average profitability and leverage (latest filed quarter) vs the all-stock universe.
          {' '}{data.n} of the sector&apos;s stocks have financials.
        </p>
      </div>
      <table className="w-full text-right max-w-[640px]">
        <thead>
          <tr className="font-num text-[10px] text-txt-3 uppercase tracking-wider border-b border-edge-hair">
            <th className="text-left py-1.5 font-medium">Metric</th>
            <th className="py-1.5 font-medium">Sector</th>
            <th className="py-1.5 font-medium">Universe</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.label} className="border-b border-edge-hair">
              <td className="text-left py-1.5 font-sans text-xs text-txt-2">{r.label}{r.term && <TermInfo term={r.term} />}</td>
              <td className={`py-1.5 font-num text-xs tabular-nums ${cmp(r.s, r.u, r.low)}`}>{r.fmt(r.s)}</td>
              <td className="py-1.5 font-num text-xs tabular-nums text-txt-3">{r.fmt(r.u)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
