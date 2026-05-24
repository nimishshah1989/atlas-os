import { TrendingUp } from 'lucide-react'
import type { LeaderHoldingRow } from '@/lib/queries/leaders'
import { RSStateChip, RSPctileBar, MomentumChip } from '@/lib/stock-formatters'
import { LinkedTicker } from '@/components/ui/LinkedToken'

function pct(v: string | null): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

interface Props {
  holdings: LeaderHoldingRow[]
  /** Disclosure date of the underlying holdings data */
  asOfDate?: string | null
}

export function LeaderHoldingsPanel({ holdings, asOfDate }: Props) {
  if (holdings.length === 0) {
    return (
      <div className="border border-paper-rule rounded-sm">
        <div className="px-4 py-3 border-b border-paper-rule flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5 text-teal" />
          <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
            RS Leader &amp; Strong Holdings
          </span>
        </div>
        <div className="px-4 py-4">
          <p className="font-sans text-xs text-ink-tertiary">
            None of the current holdings are classified as RS Leader or Strong.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-sm">
      <div className="px-4 py-3 border-b border-paper-rule flex items-center gap-2">
        <TrendingUp className="w-3.5 h-3.5 text-teal" />
        <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
          RS Leader &amp; Strong Holdings
        </span>
        <span className="font-sans text-[11px] text-ink-tertiary">
          {holdings.length} of current portfolio
        </span>
        {asOfDate && (
          <span className="ml-auto font-sans text-[11px] text-ink-tertiary">{asOfDate}</span>
        )}
      </div>
      <div className="px-4 py-3 overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Symbol</th>
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden sm:table-cell">Sector</th>
              <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Weight</th>
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary pl-4">RS State</th>
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden md:table-cell">Momentum</th>
              <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">RS Pctile</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map(h => (
              <tr key={h.instrument_id} className="border-b border-paper-rule last:border-0 hover:bg-paper-rule/10">
                <td className="py-1.5 pr-3">
                  <LinkedTicker symbol={h.symbol} className="font-semibold" />
                  <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[140px]">{h.company_name}</div>
                </td>
                <td className="py-1.5 pr-3 hidden sm:table-cell">
                  <span className="font-sans text-[10px] text-ink-secondary">{h.sector ?? '—'}</span>
                </td>
                <td className="py-1.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                  {pct(h.weight)}
                </td>
                <td className="py-1.5 pl-4 pr-3">
                  <RSStateChip value={h.rs_state} />
                </td>
                <td className="py-1.5 pr-3 hidden md:table-cell">
                  <MomentumChip value={h.momentum_state} />
                </td>
                <td className="py-1.5 text-right">
                  <RSPctileBar value={h.rs_pctile_3m} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
