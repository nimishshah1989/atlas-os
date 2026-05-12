// SP04 Stage 4c — single-line hit-rate summary on the stock deep-dive
// breakdown panel. Greyed-out copy when n < MIN_OBSERVATIONS.
import type { HitRateRow as HRRow } from '@/lib/queries/weight_performance'

type Props = {
  hitRate: HRRow | null
}

export function HitRateRow({ hitRate }: Props) {
  if (!hitRate) {
    return (
      <div className="font-sans text-[11px] text-ink-tertiary mb-2">
        Hit-rate: insufficient history for this stock.
      </div>
    )
  }
  const n_high = hitRate.n_high_conviction_days
  const n_pos = hitRate.n_positive_outcomes
  if (hitRate.hit_rate === null) {
    return (
      <div className="font-sans text-[11px] text-ink-tertiary mb-2">
        Hit-rate: only {n_high} high-conviction day{n_high === 1 ? '' : 's'} in
        the last {hitRate.lookback_window}; need more observations.
      </div>
    )
  }
  const pct = Math.round(parseFloat(hitRate.hit_rate) * 100)
  const color = pct >= 60 ? 'text-signal-pos' : pct <= 40 ? 'text-signal-neg' : 'text-ink-primary'
  return (
    <div className="font-sans text-[11px] text-ink-secondary mb-2">
      Last {hitRate.lookback_window} trading days:{' '}
      <span className={`font-mono ${color}`}>
        {n_pos}/{n_high}
      </span>{' '}
      high-conviction days outperformed tier median (
      <span className={`font-mono ${color}`}>{pct}%</span>).
    </div>
  )
}
