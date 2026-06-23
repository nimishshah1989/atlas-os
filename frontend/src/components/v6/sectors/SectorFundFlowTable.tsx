// SectorFundFlowTable — sector fund-flow: constituent-average delivery (30d/60d), up/down
// delivery asymmetry (smart-money concentration), and the institutional flow sub-score, vs
// the universe. Native foundation_staging.delivery_daily + journal. Server component.
import type { SectorFundFlow } from '@/lib/queries/v6/sector_lens'

const pct = (v: number | null) => (v == null ? '—' : `${v.toFixed(1)}%`)
const signed = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`)
const num = (v: number | null) => (v == null ? '—' : v.toFixed(0))
const cmp = (s: number | null, u: number | null) =>
  s == null || u == null ? 'text-ink-secondary' : s > u ? 'text-signal-pos' : s < u ? 'text-signal-neg' : 'text-ink-secondary'

export function SectorFundFlowTable({ data }: { data: SectorFundFlow }) {
  const rows = [
    { label: 'Delivery % (30d avg)', s: data.deliv_30d, u: data.u_deliv_30d, fmt: pct },
    { label: 'Delivery % (60d avg)', s: data.deliv_60d, u: null, fmt: pct },
    { label: 'Up/down delivery asym', s: data.updown, u: data.u_updown, fmt: signed },
    { label: 'Institutional flow score', s: data.flow_inst, u: null, fmt: num },
  ]
  return (
    <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector fund flow">
      <div className="mb-5">
        <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Sector fund flow</h2>
        <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
          Constituent-average delivery (conviction of holding), up-vs-down-day delivery asymmetry
          (smart-money concentration), and the institutional-flow sub-score. {data.n} stocks with data.
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
              <td className={`py-1.5 font-mono text-xs tabular-nums ${cmp(r.s, r.u)}`}>{r.fmt(r.s)}</td>
              <td className="py-1.5 font-mono text-xs tabular-nums text-ink-tertiary">{r.u == null ? '—' : r.fmt(r.u)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
