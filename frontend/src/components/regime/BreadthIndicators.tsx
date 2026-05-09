// frontend/src/components/regime/BreadthIndicators.tsx
import { Suspense } from 'react'
import { BreadthCategory, type IndicatorRow } from './BreadthCategory'
import { TimeRangeToggle, type TimeRange } from '@/components/ui/TimeRangeToggle'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import type { RegimeHistoryRow, MarketRegimeRow } from '@/lib/queries/regime'

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const num = (v: number) => v.toFixed(2)
const int = (v: number) => v.toFixed(0)

type Props = {
  current: MarketRegimeRow
  history: RegimeHistoryRow[]
  range: TimeRange
}

export function BreadthIndicators({ current, history, range }: Props) {
  const f = (s: string | null | undefined) =>
    s == null ? null : parseFloat(s)

  // Extract sparkline data for a metric from history
  const spark = (getter: (r: RegimeHistoryRow) => string | number | null | undefined) =>
    history.map((r) => {
      const v = getter(r)
      return v !== null && v !== undefined ? parseFloat(String(v)) : null
    })

  const trendIndicators: IndicatorRow[] = [
    {
      key: 'above_ema_50',
      label: 'Above 50-day EMA',
      tooltipKey: 'nifty500_ema_50_slope',
      current: current.nifty500_above_ema_50 ? 1 : 0,
      isBullish: current.nifty500_above_ema_50,
      history: spark((r) => r.nifty500_ema_50_slope),
      format: (v) => v === 1 ? 'Yes' : 'No',
    },
    {
      key: 'above_ema_200',
      label: 'Above 200-day EMA',
      tooltipKey: 'nifty500_ema_200_slope',
      current: current.nifty500_above_ema_200 ? 1 : 0,
      isBullish: current.nifty500_above_ema_200,
      history: spark((r) => r.nifty500_ema_200_slope),
      format: (v) => v === 1 ? 'Yes' : 'No',
    },
    {
      key: 'ema50_slope',
      label: '50-day EMA slope',
      tooltipKey: 'nifty500_ema_50_slope',
      current: f(current.nifty500_ema_50_slope),
      isBullish: f(current.nifty500_ema_50_slope) !== null ? f(current.nifty500_ema_50_slope)! > 0 : null,
      history: spark((r) => r.nifty500_ema_50_slope),
      format: (v) => `${v.toFixed(2)}σ`,
      refLine: 0,
    },
    {
      key: 'ema200_slope',
      label: '200-day EMA slope',
      tooltipKey: 'nifty500_ema_200_slope',
      current: f(current.nifty500_ema_200_slope),
      isBullish: f(current.nifty500_ema_200_slope) !== null ? f(current.nifty500_ema_200_slope)! > 0 : null,
      history: spark((r) => r.nifty500_ema_200_slope),
      format: (v) => `${v.toFixed(2)}σ`,
      refLine: 0,
    },
  ]

  const breadthIndicators: IndicatorRow[] = [
    {
      key: 'pct_ema20',
      label: '% above 20-day EMA',
      tooltipKey: 'pct_above_ema_20',
      current: f(current.pct_above_ema_20),
      isBullish: f(current.pct_above_ema_20) !== null ? f(current.pct_above_ema_20)! > 0.5 : null,
      history: spark((r) => r.pct_above_ema_20),
      format: pct,
      refLine: 0.5,
    },
    {
      key: 'pct_ema50',
      label: '% above 50-day EMA',
      tooltipKey: 'pct_above_ema_50',
      current: f(current.pct_above_ema_50),
      isBullish: f(current.pct_above_ema_50) !== null ? f(current.pct_above_ema_50)! > 0.5 : null,
      history: spark((r) => r.pct_above_ema_50),
      format: pct,
      refLine: 0.5,
    },
    {
      key: 'pct_ema200',
      label: '% above 200-day EMA',
      tooltipKey: 'pct_above_ema_200',
      current: f(current.pct_above_ema_200),
      isBullish: f(current.pct_above_ema_200) !== null ? f(current.pct_above_ema_200)! > 0.5 : null,
      history: spark((r) => r.pct_above_ema_200),
      format: pct,
      refLine: 0.5,
    },
    {
      key: 'ad_ratio',
      label: 'Advance/Decline ratio',
      tooltipKey: 'ad_ratio',
      current: f(current.ad_ratio),
      isBullish: f(current.ad_ratio) !== null ? f(current.ad_ratio)! > 1 : null,
      history: spark((r) => r.ad_ratio),
      format: num,
      refLine: 1,
    },
    {
      key: 'ad_line_slope',
      label: 'A/D line slope (21D)',
      tooltipKey: 'ad_line_slope_21',
      current: f(current.ad_line_slope_21),
      isBullish: f(current.ad_line_slope_21) !== null ? f(current.ad_line_slope_21)! > 0 : null,
      history: spark((r) => r.ad_line),
      format: (v) => `${v.toFixed(2)}σ`,
      refLine: 0,
    },
    {
      key: 'new_highs',
      label: 'New 52W highs',
      tooltipKey: 'new_52w_highs',
      current: current.new_52w_highs,
      isBullish: current.new_52w_highs !== null && current.new_52w_lows !== null
        ? current.new_52w_highs > (current.new_52w_lows ?? 0)
        : null,
      history: spark((r) => r.new_52w_highs),
      format: int,
    },
    {
      key: 'hl_ratio',
      label: 'Highs/Lows ratio',
      tooltipKey: 'new_high_low_ratio',
      current: f(current.new_high_low_ratio),
      isBullish: f(current.new_high_low_ratio) !== null ? f(current.new_high_low_ratio)! > 1 : null,
      history: spark((r) => r.new_high_low_ratio),
      format: num,
      refLine: 1,
    },
  ]

  const momentumIndicators: IndicatorRow[] = [
    {
      key: 'mcclellan_osc',
      label: 'McClellan Oscillator',
      tooltipKey: 'mcclellan_oscillator',
      current: f(current.mcclellan_oscillator),
      isBullish: f(current.mcclellan_oscillator) !== null ? f(current.mcclellan_oscillator)! > 0 : null,
      history: spark((r) => r.mcclellan_oscillator),
      format: num,
      refLine: 0,
    },
    {
      key: 'mcclellan_sum',
      label: 'McClellan Summation',
      tooltipKey: 'mcclellan_summation',
      current: f(current.mcclellan_summation),
      isBullish: f(current.mcclellan_summation) !== null ? f(current.mcclellan_summation)! > 0 : null,
      history: spark((r) => r.mcclellan_summation),
      format: num,
      refLine: 0,
    },
    {
      key: 'net_new_highs',
      label: 'Net new highs',
      tooltipKey: 'new_52w_highs',
      current: current.net_new_highs,
      isBullish: current.net_new_highs !== null ? current.net_new_highs > 0 : null,
      history: spark((r) => r.net_new_highs),
      format: int,
      refLine: 0,
    },
    {
      key: 'new_lows',
      label: 'New 52W lows',
      tooltipKey: 'new_52w_lows',
      current: current.new_52w_lows,
      isBullish: current.new_52w_lows !== null ? current.new_52w_lows < 20 : null,
      history: spark((r) => r.new_52w_lows),
      format: int,
    },
  ]

  const participationIndicators: IndicatorRow[] = [
    {
      key: 'pct_strong',
      label: '% in Strong states',
      tooltipKey: 'pct_in_strong_states',
      current: f(current.pct_in_strong_states),
      isBullish: f(current.pct_in_strong_states) !== null ? f(current.pct_in_strong_states)! > 0.4 : null,
      history: spark((r) => r.pct_in_strong_states),
      format: pct,
      refLine: 0.4,
    },
    {
      key: 'pct_weinstein',
      label: '% Weinstein pass',
      tooltipKey: 'pct_weinstein_pass',
      current: f(current.pct_weinstein_pass),
      isBullish: f(current.pct_weinstein_pass) !== null ? f(current.pct_weinstein_pass)! > 0.4 : null,
      history: spark((r) => r.pct_weinstein_pass),
      format: pct,
      refLine: 0.4,
    },
    {
      key: 'participation_50',
      label: 'Broad participation (50D)',
      tooltipKey: 'pct_above_ema_50',
      current: f(current.pct_above_ema_50),
      isBullish: f(current.pct_above_ema_50) !== null ? f(current.pct_above_ema_50)! > 0.45 : null,
      history: spark((r) => r.pct_above_ema_50),
      format: pct,
      refLine: 0.45,
    },
  ]

  const countBullish = (inds: IndicatorRow[]) => inds.filter((i) => i.isBullish === true).length

  return (
    <div>
      {/* Section header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          Signal Details
          <InfoTooltip content="Breadth indicators measure market participation. When multiple independent measures align, the regime signal has higher conviction." />
        </h2>
        <Suspense>
          <TimeRangeToggle value={range} paramName="breadth_range" />
        </Suspense>
      </div>

      {/* 4-column signal breakdown */}
      <div className="grid grid-cols-4 divide-x divide-paper-rule">
        <BreadthCategory
          title="Trend"
          indicators={trendIndicators}
          bullishCount={countBullish(trendIndicators)}
          totalCount={trendIndicators.length}
        />
        <BreadthCategory
          title="Breadth"
          indicators={breadthIndicators}
          bullishCount={countBullish(breadthIndicators)}
          totalCount={breadthIndicators.length}
        />
        <BreadthCategory
          title="Momentum"
          indicators={momentumIndicators}
          bullishCount={countBullish(momentumIndicators)}
          totalCount={momentumIndicators.length}
        />
        <BreadthCategory
          title="Participation"
          indicators={participationIndicators}
          bullishCount={countBullish(participationIndicators)}
          totalCount={participationIndicators.length}
        />
      </div>
    </div>
  )
}
