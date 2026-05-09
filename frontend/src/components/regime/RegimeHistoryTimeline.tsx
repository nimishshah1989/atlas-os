// frontend/src/components/regime/RegimeHistoryTimeline.tsx
import { Suspense } from 'react'
import { StateTimeline } from '@/components/ui/StateTimeline'
import { LineChart } from '@/components/ui/LineChart'
import { TimeRangeToggle, type TimeRange } from '@/components/ui/TimeRangeToggle'
import { BenchmarkSelector } from '@/components/ui/BenchmarkSelector'
import type { RegimeHistoryRow } from '@/lib/queries/regime'
import type { BenchmarkRow } from '@/lib/queries/benchmarks'

type Props = {
  history: RegimeHistoryRow[]
  benchmarkData: BenchmarkRow[]
  benchmarkCode: string
  range: TimeRange
}

function buildPriceChartData(
  history: RegimeHistoryRow[],
  benchmarkData: BenchmarkRow[]
): { date: string; primary: number | null; benchmark: number | null }[] {
  const bmMap = new Map(benchmarkData.map((b) => [b.date.toISOString().slice(0, 10), b]))

  // Index both series to 100 at start
  let firstClose: number | null = null
  let firstBm: number | null = null

  return history.map((row) => {
    const dateKey = row.date instanceof Date
      ? row.date.toISOString().slice(0, 10)
      : String(row.date)
    const close = row.nifty500_close ? parseFloat(row.nifty500_close) : null
    const bmEntry = bmMap.get(dateKey)
    const bm = bmEntry?.close ? parseFloat(bmEntry.close) : null

    if (close !== null && firstClose === null) firstClose = close
    if (bm !== null && firstBm === null) firstBm = bm

    return {
      date: dateKey,
      primary: close !== null && firstClose !== null ? (close / firstClose) * 100 : null,
      benchmark: bm !== null && firstBm !== null ? (bm / firstBm) * 100 : null,
    }
  })
}

const BENCHMARK_LABELS: Record<string, string> = {
  NIFTY50:  'Nifty 50',
  NIFTY500: 'Nifty 500',
  NIFTY100: 'Nifty 100',
  GOLD:     'Gold',
}

export function RegimeHistoryTimeline({ history, benchmarkData, benchmarkCode, range }: Props) {
  const timelineRows = history.map((r) => ({
    date: r.date instanceof Date ? r.date : new Date(r.date),
    state: r.regime_state,
  }))

  const priceData = buildPriceChartData(history, benchmarkData)

  // Build labeled segments for legend
  const uniqueStates = [...new Set(timelineRows.map((r) => r.state))]

  const STATE_LEGEND: Record<string, string> = {
    'Risk-On':      'bg-signal-pos',
    'Constructive': 'bg-teal',
    'Cautious':     'bg-signal-warn',
    'Risk-Off':     'bg-signal-neg',
  }

  return (
    <div className="px-6 py-5 border-b border-paper-rule">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <h2 className="font-sans text-sm font-medium text-ink-primary">Regime history</h2>
          <div className="flex items-center gap-2">
            {uniqueStates.map((s) => (
              <span key={s} className="flex items-center gap-1 text-xs font-sans text-ink-secondary">
                <span className={`inline-block w-2.5 h-2.5 rounded-[1px] ${STATE_LEGEND[s] ?? 'bg-paper-rule'}`} />
                {s}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Suspense>
            <BenchmarkSelector
              value={benchmarkCode}
              availableCodes={['NIFTY50', 'NIFTY500', 'NIFTY100', 'GOLD', 'MSCIWORLD', 'SP500']}
            />
            <TimeRangeToggle value={range} options={['1M', '3M', '6M', '1Y']} />
          </Suspense>
        </div>
      </div>

      {/* State strip */}
      <StateTimeline rows={timelineRows} height={16} className="mb-3" />

      {/* Nifty 500 price line indexed to 100, with benchmark overlay */}
      <LineChart
        data={priceData}
        primaryLabel="Nifty 500"
        benchmarkLabel={BENCHMARK_LABELS[benchmarkCode] ?? benchmarkCode}
        height={100}
      />
    </div>
  )
}
