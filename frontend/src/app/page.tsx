// frontend/src/app/page.tsx
import { Suspense } from 'react'
import { getCurrentRegime, getRegimeHistory } from '@/lib/queries/regime'
import { getBenchmarkHistory } from '@/lib/queries/benchmarks'
import { RegimeHeadline } from '@/components/regime/RegimeHeadline'
import { RegimeHistoryTimeline } from '@/components/regime/RegimeHistoryTimeline'
import { BreadthIndicators } from '@/components/regime/BreadthIndicators'
import { rangeToDays, type TimeRange } from '@/components/ui/TimeRangeToggle'

type SearchParams = Promise<{ range?: string; benchmark?: string; breadth_range?: string }>

export default async function RegimePage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '6M', benchmark = 'NIFTY500', breadth_range = '3M' } = await searchParams

  const historyRange = range as TimeRange
  const breadthRange = breadth_range as TimeRange
  const historyDays = rangeToDays(historyRange)
  const breadthDays = rangeToDays(breadthRange)

  const [current, historyFull, breadthHistory, benchmarkData] = await Promise.all([
    getCurrentRegime(),
    getRegimeHistory(historyDays),
    getRegimeHistory(breadthDays),
    getBenchmarkHistory(benchmark, historyDays),
  ])

  if (!current) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No regime data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto">
      {/* Band 1 — Current regime state */}
      <RegimeHeadline regime={current} />

      {/* Band 2 — History timeline */}
      <Suspense fallback={<div className="px-8 py-6 border-b border-paper-rule h-48 animate-pulse bg-paper-rule/10" />}>
        <RegimeHistoryTimeline
          history={historyFull}
          benchmarkData={benchmarkData}
          benchmarkCode={benchmark}
          range={historyRange}
        />
      </Suspense>

      {/* Band 3 — Breadth indicators */}
      <BreadthIndicators
        current={current}
        history={breadthHistory}
        range={breadthRange}
      />
    </div>
  )
}
