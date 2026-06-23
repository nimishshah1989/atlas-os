// SectorBreadthWithin — within-sector breadth from the per-stock deciles: how many of the
// sector's stocks are top-decile (and top-2-decile) on each lens, plus the leadership
// distribution. Native (decile-derived). Server component.
import type { SectorStock } from '@/lib/queries/v6/sector_lens'

const LENSES: { key: keyof SectorStock; label: string }[] = [
  { key: 'd_tech', label: 'Technical' },
  { key: 'd_fund', label: 'Fundamental' },
  { key: 'd_cat', label: 'Catalyst' },
  { key: 'd_flow', label: 'Flow' },
  { key: 'd_val', label: 'Valuation' },
]

export function SectorBreadthWithin({ stocks }: { stocks: SectorStock[] }) {
  const n = stocks.length
  if (n === 0) return null
  const count = (key: keyof SectorStock, min: number) =>
    stocks.filter(s => (s[key] as number | null) != null && (s[key] as number) >= min).length
  const leadDist = [4, 3, 2, 1, 0].map(l => ({ l, c: stocks.filter(s => s.lead === l).length }))

  return (
    <section className="px-8 py-10 border-b border-paper-rule" aria-label="Within-sector breadth">
      <div className="mb-5">
        <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Within-sector breadth</h2>
        <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
          How many of the sector's {n} stocks rank top-decile (and top-two-decile) on each lens, within their cap cohort.
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-6">
        <table className="w-full text-right">
          <thead>
            <tr className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider border-b border-paper-rule">
              <th className="text-left py-1.5 font-medium">Lens</th>
              <th className="py-1.5 font-medium">Top decile</th>
              <th className="py-1.5 font-medium">Top 2 deciles</th>
            </tr>
          </thead>
          <tbody>
            {LENSES.map(l => (
              <tr key={l.key} className="border-b border-paper-rule/40">
                <td className="text-left py-1.5 font-sans text-xs text-ink-secondary">{l.label}</td>
                <td className="py-1.5 font-mono text-xs tabular-nums text-signal-pos">{count(l.key, 10)}</td>
                <td className="py-1.5 font-mono text-xs tabular-nums text-ink-secondary">{count(l.key, 9)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div>
          <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-2">Leadership distribution (# lenses top-decile)</div>
          <div className="space-y-1.5">
            {leadDist.map(({ l, c }) => (
              <div key={l} className="flex items-center gap-3">
                <span className="w-[60px] shrink-0 font-mono text-xs text-ink-secondary">{l} / 4</span>
                <span className="w-[28px] shrink-0 font-mono text-xs tabular-nums text-ink-primary text-right">{c}</span>
                <span className="flex-1 h-[7px] bg-paper-deep rounded-[2px] overflow-hidden">
                  <span className={`block h-full rounded-[2px] ${l >= 2 ? 'bg-signal-pos' : l === 1 ? 'bg-signal-warn' : 'bg-ink-tertiary/40'}`}
                    style={{ width: `${n ? (100 * c / n) : 0}%` }} />
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
