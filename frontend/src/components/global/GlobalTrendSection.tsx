'use client'
import { TrendingUp } from 'lucide-react'
import { SectionHeader } from '@/components/regime/SectionHeader'
import { CategorySummary } from '@/components/regime/CategorySummary'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { GlobalRegimeRow, GlobalRegimeHistoryRow } from '@/lib/queries/global'

type Props = {
  current: GlobalRegimeRow
  history: GlobalRegimeHistoryRow[]
}

const f = (s: string | null | undefined): number => (s == null ? 0 : parseFloat(s))

const dateStr = (row: GlobalRegimeHistoryRow): string =>
  String(row.date).slice(0, 10)

export function GlobalTrendSection({ current, history }: Props) {
  const ema50Slope  = f(current.benchmark_ema_50_slope)
  const ema200Slope = f(current.benchmark_ema_200_slope)

  // 4 bullish signals
  const bullishSignals = [
    current.benchmark_above_ema_50  === true,
    current.benchmark_above_ema_200 === true,
    ema50Slope  > 0,
    ema200Slope > 0,
  ]
  const bullishCount = bullishSignals.filter(Boolean).length
  const totalCount   = bullishSignals.length

  const slope50Word  = ema50Slope  > 0.01 ? 'rising'  : ema50Slope  < -0.01 ? 'falling' : 'flat'
  const slope200Word = ema200Slope > 0.01 ? 'rising'  : ema200Slope < -0.01 ? 'falling' : 'flat'
  const trendLabel   =
    bullishCount >= 3 ? 'TREND IS HEALTHY' :
    bullishCount === 2 ? 'TREND IS MIXED' :
    'TREND IS WEAK'
  const trendSummary =
    `VT (World ETF) is ${current.benchmark_above_ema_50 ? 'above' : 'below'} its 50-day EMA` +
    ` and ${current.benchmark_above_ema_200 ? 'above' : 'below'} its 200-day EMA. ` +
    `50-day slope is ${slope50Word} (${ema50Slope.toFixed(3)}σ); ` +
    `200-day slope is ${slope200Word} (${ema200Slope.toFixed(3)}σ). ` +
    (bullishCount >= 3
      ? 'Global primary trend is intact.'
      : bullishCount === 2
        ? 'Mixed signals — proceed with caution globally.'
        : 'Global trend is under pressure. Reduce international exposure.')

  const ema50Data = history.map((row) => ({
    date: dateStr(row),
    value: row.benchmark_ema_50_slope != null ? parseFloat(row.benchmark_ema_50_slope) : null,
  }))

  const ema200Data = history.map((row) => ({
    date: dateStr(row),
    value: row.benchmark_ema_200_slope != null ? parseFloat(row.benchmark_ema_200_slope) : null,
  }))

  return (
    <section>
      <SectionHeader
        icon={<TrendingUp className="w-4 h-4" strokeWidth={2} />}
        title="Trend"
        description="Global trend analysis tells us whether VT (the Vanguard Total World ETF) is in a healthy uptrend relative to its key moving averages. When VT is above both its 50 and 200-day EMAs and those averages are rising, the global primary trend is up. The 50-day slope is an early warning system — it turns negative weeks before the ETF itself breaks down."
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
        <div className="flex items-center gap-3 mb-5 flex-wrap">
          <div className="flex items-center gap-1.5">
            <span className="font-sans text-xs text-ink-tertiary">VT above 50-day EMA</span>
            {current.benchmark_above_ema_50 ? (
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
            <span className="font-sans text-xs text-ink-tertiary">VT above 200-day EMA</span>
            {current.benchmark_above_ema_200 ? (
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
            title="50-day EMA Slope (VT)"
            description="Measures the rate of change of VT's 50-day average. Positive means the average is rising and the global medium-term trend is strengthening. Turns negative weeks before VT itself breaks down — a leading indicator of global risk-off."
            currentValue={`${ema50Slope.toFixed(3)}σ`}
            isBullish={ema50Slope > 0}
            data={ema50Data}
            refLine={0}
            refLabel="0"
            variant="line"
            yFormat="sigma"
          />
          <IndicatorChart
            title="200-day EMA Slope (VT)"
            description="Long-term global trend direction. A declining 200-day slope — even while VT holds above it — signals structural global trend weakness. Most institutional global allocation frameworks require this to be positive before full deployment."
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
