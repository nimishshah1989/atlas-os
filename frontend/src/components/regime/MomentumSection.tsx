import { Zap } from 'lucide-react'
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

export function MomentumSection({ current, history }: Props) {
  const f = (s: string | null | undefined): number => (s == null ? 0 : parseFloat(s))

  const mcOsc = f(current.mcclellan_oscillator)
  const mcSum = f(current.mcclellan_summation)
  const netHighs = current.net_new_highs ?? 0
  const lows52w = current.new_52w_lows ?? 0

  const bullishSignals = [
    mcOsc > 0,
    mcSum > 0,
    netHighs > 0,
    lows52w < 20,
  ]
  const bullishCount = bullishSignals.filter(Boolean).length
  const totalCount   = bullishSignals.length

  const momLabel   = bullishCount >= 3 ? 'MOMENTUM IS POSITIVE' : bullishCount === 2 ? 'MOMENTUM IS FADING' : 'MOMENTUM IS NEGATIVE'
  const momSummary =
    `McClellan Oscillator at ${mcOsc.toFixed(0)} — ${mcOsc > 0 ? 'breadth is accelerating' : 'breadth is decelerating'}. ` +
    `Summation Index at ${mcSum.toFixed(0)} — ${mcSum > 0 ? 'intermediate trend is up' : 'intermediate trend is down'}. ` +
    `Net new highs: ${netHighs > 0 ? '+' : ''}${netHighs}. ` +
    `${lows52w} stocks at new 52-week lows — ${lows52w < 20 ? 'manageable' : lows52w < 50 ? 'elevated — watch closely' : 'high — broad selling underway'}.`

  const mcOscData = history.map((row) => ({
    date: dateStr(row),
    value: row.mcclellan_oscillator != null ? parseFloat(row.mcclellan_oscillator) : null,
  }))
  const mcSumData = history.map((row) => ({
    date: dateStr(row),
    value: row.mcclellan_summation != null ? parseFloat(row.mcclellan_summation) : null,
  }))
  const netHighsData = history.map((row) => ({
    date: dateStr(row),
    value: row.net_new_highs ?? null,
  }))
  const lows52wData = history.map((row) => ({
    date: dateStr(row),
    value: row.new_52w_lows ?? null,
  }))

  return (
    <section>
      <SectionHeader
        icon={<Zap className="w-4 h-4" strokeWidth={2} />}
        title="Momentum"
        description="Momentum measures whether market breadth is accelerating or decelerating. The McClellan Oscillator captures the short-term pace of advances vs declines — think of it as the rate of change of breadth. The Summation Index accumulates these readings into an intermediate-term trend indicator. Zero-line crossovers on both are significant signals."
        bullishCount={bullishCount}
        totalCount={totalCount}
      />

      <CategorySummary
        bullishCount={bullishCount}
        totalCount={totalCount}
        headline={momLabel}
        summary={momSummary}
      />

      <div className="px-6 pb-6">
        <div className="grid grid-cols-2 gap-4">
          <IndicatorChart
            title="McClellan Oscillator"
            description="Short-term breadth momentum. Positive when advances are outpacing declines on an accelerating basis. Readings near ±100 suggest overbought/oversold conditions — not a sell/buy signal by itself, but combined with zero-line direction, it's a powerful timing tool."
            currentValue={mcOsc.toFixed(1)}
            isBullish={mcOsc > 0}
            data={mcOscData}
            refLine={0}
            refLabel="0"
            variant="bar"
            yFormat="count"
          />
          <IndicatorChart
            title="McClellan Summation Index"
            description="Cumulative sum of the Oscillator — the intermediate-term breadth trend. Above zero is structurally bullish. A turn below zero while the index holds its level is one of the most reliable bearish divergence signals. Requires sustained oscillator readings to reverse."
            currentValue={mcSum.toFixed(0)}
            isBullish={mcSum > 0}
            data={mcSumData}
            refLine={0}
            refLabel="0"
            variant="area"
            yFormat="count"
          />
          <IndicatorChart
            title="Net New Highs (21D)"
            description="New 52-week highs minus new lows, net. Positive means the market is internally healthy. A persistent negative reading — sustained for 30+ days — has historically defined bear markets. This is the internal market health metric."
            currentValue={String(current.net_new_highs ?? '–')}
            isBullish={netHighs > 0}
            data={netHighsData}
            refLine={0}
            refLabel="0"
            variant="bar"
            yFormat="count"
          />
          <IndicatorChart
            title="New 52-Week Lows"
            description="Count of stocks hitting new annual lows. Below 15-20 is healthy market territory. Spikes above 50 indicate panic selling across the universe. Sustained elevated readings — even without index collapse — signal significant internal market damage."
            currentValue={String(current.new_52w_lows ?? '–')}
            isBullish={lows52w < 20}
            data={lows52wData}
            variant="bar"
            yFormat="count"
            invertBarColors
          />
        </div>
      </div>
    </section>
  )
}
