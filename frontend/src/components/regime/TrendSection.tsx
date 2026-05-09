import { TrendingUp } from 'lucide-react'
import { SectionHeader } from './SectionHeader'
import { CategorySummary } from './CategorySummary'
import { IndicatorChart } from './IndicatorChart'
import type { MarketRegimeRow, RegimeHistoryRow } from '@/lib/queries/regime'

type Props = {
  current: MarketRegimeRow
  history: RegimeHistoryRow[]
}

const dateStr = (row: RegimeHistoryRow): string =>
  row.date instanceof Date
    ? row.date.toISOString().slice(0, 10)
    : String(row.date).slice(0, 10)

export function TrendSection({ current, history }: Props) {
  const ema50Slope = current.nifty500_ema_50_slope != null
    ? parseFloat(current.nifty500_ema_50_slope)
    : 0
  const ema200Slope = current.nifty500_ema_200_slope != null
    ? parseFloat(current.nifty500_ema_200_slope)
    : 0

  // Compute bullish count for gauge
  const bullishSignals = [
    current.nifty500_above_ema_50 === true,
    current.nifty500_above_ema_200 === true,
    ema50Slope > 0,
    ema200Slope > 0,
  ]
  const bullishCount = bullishSignals.filter(Boolean).length
  const totalCount   = bullishSignals.length

  const slope50Word  = ema50Slope > 0.01 ? 'rising' : ema50Slope < -0.01 ? 'falling' : 'flat'
  const slope200Word = ema200Slope > 0.01 ? 'rising' : ema200Slope < -0.01 ? 'falling' : 'flat'
  const trendLabel   = bullishCount >= 3 ? 'TREND IS HEALTHY' : bullishCount === 2 ? 'TREND IS MIXED' : 'TREND IS WEAK'
  const trendSummary =
    `Nifty 500 is ${current.nifty500_above_ema_50 ? 'above' : 'below'} the 50-day EMA` +
    ` and ${current.nifty500_above_ema_200 ? 'above' : 'below'} the 200-day EMA. ` +
    `50-day slope is ${slope50Word} (${ema50Slope.toFixed(3)}σ); ` +
    `200-day slope is ${slope200Word} (${ema200Slope.toFixed(3)}σ). ` +
    `${bullishCount >= 3 ? 'Primary trend is intact.' : bullishCount === 2 ? 'Mixed signals — proceed with caution.' : 'Trend is under pressure. Reduce exposure.'}`

  const ema50Data = history.map((row) => ({
    date: dateStr(row),
    value: row.nifty500_ema_50_slope != null ? parseFloat(row.nifty500_ema_50_slope) : null,
  }))

  const ema200Data = history.map((row) => ({
    date: dateStr(row),
    value: row.nifty500_ema_200_slope != null ? parseFloat(row.nifty500_ema_200_slope) : null,
  }))

  return (
    <section>
      <SectionHeader
        icon={<TrendingUp className="w-4 h-4" strokeWidth={2} />}
        title="Trend"
        description="Trend analysis tells us whether the Nifty 500 index is in a healthy uptrend relative to its key moving averages. When the index is above both its 50 and 200-day EMAs and those averages are rising, the primary trend is up. A rolling 50-day slope is an early warning system — it turns negative weeks before the index itself breaks down."
        bullishCount={bullishCount}
        totalCount={totalCount}
      />

      <CategorySummary
        bullishCount={bullishCount}
        totalCount={totalCount}
        headline={trendLabel}
        summary={trendSummary}
      />

      <div className="px-6 pb-6">
        {/* Status badges */}
        <div className="flex items-center gap-3 mb-5">
          <div className="flex items-center gap-1.5">
            <span className="font-sans text-xs text-ink-tertiary">Nifty 500 above 50-day EMA</span>
            {current.nifty500_above_ema_50 ? (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] text-[10px] font-sans font-medium bg-signal-pos/10 text-signal-pos">
                YES
              </span>
            ) : (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] text-[10px] font-sans font-medium bg-signal-neg/10 text-signal-neg">
                NO
              </span>
            )}
          </div>
          <span className="text-paper-rule">|</span>
          <div className="flex items-center gap-1.5">
            <span className="font-sans text-xs text-ink-tertiary">Nifty 500 above 200-day EMA</span>
            {current.nifty500_above_ema_200 ? (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] text-[10px] font-sans font-medium bg-signal-pos/10 text-signal-pos">
                YES
              </span>
            ) : (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] text-[10px] font-sans font-medium bg-signal-neg/10 text-signal-neg">
                NO
              </span>
            )}
          </div>
        </div>

        {/* 2-column chart grid */}
        <div className="grid grid-cols-2 gap-4">
          <IndicatorChart
            title="50-day EMA Slope"
            description="Measures the rate of change of the 50-day average. Positive means the average is rising and the medium-term trend is strengthening. Turns negative weeks before price breaks down."
            currentValue={`${ema50Slope.toFixed(3)}σ`}
            isBullish={ema50Slope > 0}
            data={ema50Data}
            refLine={0}
            refLabel="0"
            variant="line"
            yFormat="sigma"
          />
          <IndicatorChart
            title="200-day EMA Slope"
            description="The long-term trend direction. A declining 200-day slope — even while the index holds above it — signals that the structural trend is weakening. Most institutional strategies require this to be positive before deploying capital."
            currentValue={`${ema200Slope.toFixed(3)}σ`}
            isBullish={ema200Slope > 0}
            data={ema200Data}
            refLine={0}
            refLabel="0"
            variant="line"
            yFormat="sigma"
          />
        </div>
      </div>
    </section>
  )
}
