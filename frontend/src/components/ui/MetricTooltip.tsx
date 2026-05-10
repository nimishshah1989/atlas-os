'use client'
import { InfoTooltip } from './InfoTooltip'

export const METRIC_DEFINITIONS = {
  rs_pctile_3m:       'RS Percentile (3M): rank of this stock\'s 3-month relative strength vs Nifty 500 peers. 90th = beats 90% of stocks.',
  ret_1m:             '1-month total return (price change, unadjusted for dividends).',
  ret_3m:             '3-month total return.',
  ret_6m:             '6-month total return.',
  ret_1y:             '12-month total return.',
  realized_vol_63:    'Annualized realized volatility over the last 63 trading days (~3 months). Lower = smoother ride for the same return.',
  avg_volume_20:      '20-day average daily traded volume. Used to judge liquidity and inform position sizing.',
  days_in_state:      'Calendar days this instrument has been in its current RS state without a state change. Longer tenures in Leader/Strong = established trend.',
  rs_state:           'Relative-strength state: Leader / Strong / Emerging / Consolidating / Average / Weak / Laggard. Computed daily from RS percentile trajectory.',
  momentum_state:     'Momentum state: direction and acceleration of the RS trend. Accelerating = RS at a 20-day high. Collapsing = RS at a 20-day low.',
  risk_state:         'Risk state: Low / Normal / Elevated / High — based on realized volatility vs the universe median.',
  volume_state:       'Volume state: Accumulation / Steady-Buying / Neutral / Distribution / Heavy Distribution — based on volume pattern vs 20-day average.',
  position_size_pct:  'Recommended position size as % of portfolio. Scaled by RS state, momentum, and the current regime deployment multiplier.',
  extension:          'Extension above the 20-day EMA (%). High extension = price stretched above short-term trend — higher reversion risk for new entries.',
  drawdown_from_peak: 'Drawdown from the 52-week closing high. Greater than 20% is a significant pull-back; context-dependent for entries.',
  gold_rs:            'RS percentile vs Gold (₹ terms). Values above 50 mean this instrument has outperformed Gold over the last 3 months.',
  weinstein_gate:     'Weinstein Stage 2 pass/fail. PASS = price above a rising 30-week MA. FAIL = do not enter regardless of RS rank.',
} as const

export type MetricKey = keyof typeof METRIC_DEFINITIONS

type Props = {
  metricKey: MetricKey
  className?: string
}

export function MetricTooltip({ metricKey, className }: Props) {
  const content = METRIC_DEFINITIONS[metricKey]
  if (!content) return null
  return <InfoTooltip content={content} className={className} />
}
