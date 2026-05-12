// SP04 Stage 4a — side-by-side current vs proposed weight diff for one
// proposal. Sorted by |delta| desc so the biggest movers are at top.
import type { WeightDict } from '@/lib/queries/proposals'

type Props = {
  current: WeightDict
  proposed: WeightDict
}

const SIGNAL_LABELS: Record<string, string> = {
  ma_30w_slope_4w: '30-week MA slope (trend)',
  ret_6m: '6-month return',
  ret_12m_1m: '12-1m momentum factor',
  extension_pct: 'Distance from MA',
  vol_ratio_63: '63-day vol ratio',
  effort_ratio_63: 'Effort ratio (vol/range)',
  realized_vol_63: '63-day realized volatility',
  max_drawdown_252: '1-year max drawdown',
  rs_pctile_3m: '3-month RS percentile',
  ema_10_ratio: '10-day EMA ratio',
  atr_21: '21-day ATR',
}

export function ProposalDiffTable({ current, proposed }: Props) {
  const keys = Array.from(new Set([...Object.keys(current), ...Object.keys(proposed)]))
  const rows = keys
    .map((sig) => {
      const c = parseFloat(current[sig] ?? '0')
      const p = parseFloat(proposed[sig] ?? '0')
      return { signal: sig, current: c, proposed: p, delta: p - c }
    })
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-paper-rule bg-paper">
            <th className="px-3 py-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
              Signal
            </th>
            <th className="px-3 py-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
              Current
            </th>
            <th className="px-3 py-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
              Proposed
            </th>
            <th className="px-3 py-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
              Δ
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const deltaColor =
              r.delta > 0.01
                ? 'text-signal-pos'
                : r.delta < -0.01
                  ? 'text-signal-neg'
                  : 'text-ink-tertiary'
            const sign = r.delta >= 0 ? '+' : ''
            return (
              <tr key={r.signal} className="border-b border-paper-rule/40">
                <td className="px-3 py-1 font-sans text-ink-primary" title={r.signal}>
                  {SIGNAL_LABELS[r.signal] ?? r.signal}
                </td>
                <td className="px-3 py-1 text-right font-mono text-ink-secondary tabular-nums">
                  {r.current.toFixed(3)}
                </td>
                <td className="px-3 py-1 text-right font-mono text-ink-primary tabular-nums">
                  {r.proposed.toFixed(3)}
                </td>
                <td className={`px-3 py-1 text-right font-mono tabular-nums ${deltaColor}`}>
                  {sign}
                  {r.delta.toFixed(3)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
