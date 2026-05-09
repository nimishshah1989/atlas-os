// frontend/src/app/sectors/page.tsx
import { Suspense } from 'react'
import { getCurrentSectors, getSectorStateHistory } from '@/lib/queries/sectors'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { getSectorDecision } from '@/lib/sectors-decision'
import { TimeRangeToggle } from '@/components/ui/TimeRangeToggle'
import { SectorBubbleChart } from '@/components/sectors/SectorBubbleChart'
import { SectorDecisionTable } from '@/components/sectors/SectorDecisionTable'
import { SectorHeatmap } from '@/components/sectors/SectorHeatmap'

type SearchParams = Promise<{ range?: string }>

export default async function SectorsPage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '6M' } = await searchParams
  const VALID_RANGES: TimeRange[] = ['1W', '1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)

  const [sectors, stateHistory] = await Promise.all([
    getCurrentSectors(),
    getSectorStateHistory(days),
  ])

  const overweightCount  = sectors.filter(s => s.sector_state === 'Overweight').length
  const neutralCount     = sectors.filter(s => s.sector_state === 'Neutral').length
  const underweightCount = sectors.filter(s => s.sector_state === 'Underweight').length
  const dataDate = sectors[0]?.data_date

  const sectorsWithDecision = sectors.map(s => ({
    ...s,
    decision: getSectorDecision(s.sector_state, s.bottomup_rs_state, s.bottomup_momentum_state),
  }))

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header band */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            Sector Regime
          </h1>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {overweightCount} Overweight
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-warn" />
              {neutralCount} Neutral
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" />
              {underweightCount} Underweight
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {dataDate && (
            <span className="font-sans text-xs text-ink-tertiary">
              Data as of {dataDate.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
            </span>
          )}
          <Suspense fallback={null}>
            <TimeRangeToggle value={historyRange} options={['1M', '3M', '6M', '1Y']} />
          </Suspense>
        </div>
      </div>

      {/* View 1: Bubble Matrix */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector Positioning Matrix — RS vs Breadth
        </h2>
        <SectorBubbleChart data={sectorsWithDecision} range={historyRange} />
      </div>

      {/* View 2: Decision Table */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector Decision Table
        </h2>
        <SectorDecisionTable data={sectorsWithDecision} />
      </div>

      {/* View 3: State History Heatmap */}
      <div className="px-6 py-6">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector State History — {historyRange}
        </h2>
        <SectorHeatmap
          history={stateHistory}
          sectors={sectorsWithDecision.map(s => s.sector_name)}
        />
      </div>
    </div>
  )
}
