// frontend/src/app/sectors/page.tsx
import { Suspense } from 'react'
import {
  getSectorsWithMomentum,
  getSectorStateHistory,
  getRRGHistory,
  getBreadthWaterfallData,
  getDaysInStateForAllSectors,
  type DaysInStateRow,
} from '@/lib/queries/sectors'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { getSectorDecision } from '@/lib/sectors-decision'
import { filterSectors } from '@/lib/sectors-filter'
import { TimeRangeToggle } from '@/components/ui/TimeRangeToggle'
import { SectorViews } from '@/components/sectors/SectorViews'
import { SectorRiskWatch } from '@/components/sectors/SectorRiskWatch'

type SearchParams = Promise<{ range?: string }>

export default async function SectorsPage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '6M' } = await searchParams
  const VALID_RANGES: TimeRange[] = ['1W', '1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)

  const [allRaw, stateHistory] = await Promise.all([
    getSectorsWithMomentum(),
    getSectorStateHistory(days),
  ])

  if (allRaw.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No sector data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const { actionable, excluded } = filterSectors(allRaw)

  const withDecision = (s: typeof allRaw[number]) => ({
    ...s,
    decision: getSectorDecision(s.sector_state, s.bottomup_rs_state, s.bottomup_momentum_state),
  })
  const actionableWithDecision = actionable.map(withDecision)
  const allWithDecision = allRaw.map(withDecision)

  const overweightCount  = actionableWithDecision.filter(s => s.sector_state === 'Overweight').length
  const neutralCount     = actionableWithDecision.filter(s => s.sector_state === 'Neutral').length
  const underweightCount = actionableWithDecision.filter(s => s.sector_state === 'Underweight').length
  const avoidCount       = actionableWithDecision.filter(s => s.sector_state === 'Avoid').length
  const dataDate = allRaw[0]?.data_date

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
            {avoidCount > 0 && (
              <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
                <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" />
                {avoidCount} Avoid
              </span>
            )}
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

      <SectorRiskWatch sectors={actionableWithDecision} />

      <SectorViews
        actionable={actionableWithDecision}
        allSectors={allWithDecision}
        excluded={excluded}
        stateHistory={stateHistory}
        range={historyRange}
      />
    </div>
  )
}
