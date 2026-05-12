// frontend/src/app/sectors/page.tsx
export const dynamic = 'force-dynamic'

import { Suspense } from 'react'
import {
  getSectorsWithMomentum,
  getSectorStateHistory,
  getRRGHistory,
  getBreadthWaterfallData,
  getDaysInStateForAllSectors,
  getSectorPlaybook,
  type PlaybookEntry,
} from '@/lib/queries/sectors'
import { getCurrentRegime } from '@/lib/queries/regime'
import { getSectorRotationState, type SectorRotationRow } from '@/lib/queries/rotation'
import { getLeadersBySector } from '@/lib/queries/leaders'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { getSectorDecision } from '@/lib/sectors-decision'
import { filterSectors } from '@/lib/sectors-filter'
import { TimeRangeToggle } from '@/components/ui/TimeRangeToggle'
import { SectorViews } from '@/components/sectors/SectorViews'
import { SectorRiskWatch } from '@/components/sectors/SectorRiskWatch'

type SearchParams = Promise<{ range?: string; tab?: string }>

export default async function SectorsPage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '6M' } = await searchParams
  const VALID_RANGES: TimeRange[] = ['1W', '1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)

  // Fetch regime first (fast: 1 row, indexed) — used to parameterise getSectorPlaybook
  const regime = await getCurrentRegime().catch(() => null)
  const regimeState = regime?.regime_state ?? 'Unknown'

  // 7 parallel queries — non-critical queries degrade to empty arrays.
  // rotation pulls from mv_sector_rotation_state (refreshed nightly by pg_cron)
  // and enriches sectors with rrg_quadrant / rs_velocity / rs_pctile_cross_sector.
  const [allRaw, stateHistory, rrgHistory, breadthData, daysInState, playbook, rotation, leadersBySectorArr] = await Promise.all([
    getSectorsWithMomentum(),
    getSectorStateHistory(days).catch(() => [] as Awaited<ReturnType<typeof getSectorStateHistory>>),
    getRRGHistory(30).catch(() => [] as Awaited<ReturnType<typeof getRRGHistory>>),
    getBreadthWaterfallData(null, 1095).catch(() => [] as Awaited<ReturnType<typeof getBreadthWaterfallData>>),
    getDaysInStateForAllSectors().catch(() => [] as Awaited<ReturnType<typeof getDaysInStateForAllSectors>>),
    getSectorPlaybook(regimeState).catch(() => [] as PlaybookEntry[]),
    getSectorRotationState().catch(() => [] as SectorRotationRow[]),
    getLeadersBySector().catch(() => []),
  ])

  const leadersBySector = Object.fromEntries(leadersBySectorArr.map(r => [r.sector, r]))

  // Build a name → rotation lookup so downstream components can read
  // rrg_quadrant / rs_velocity off the snapshot without re-querying.
  const rotationByName = new Map(rotation.map(r => [r.sector_name, r]))

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

      <Suspense fallback={
        <div className="px-6 py-8 animate-pulse space-y-3">
          <div className="h-8 bg-paper-rule/30 rounded w-1/3" />
          <div className="h-64 bg-paper-rule/20 rounded" />
        </div>
      }>
        <SectorViews
          actionable={actionableWithDecision}
          allSectors={allWithDecision}
          excluded={excluded}
          stateHistory={stateHistory}
          rrgHistory={rrgHistory}
          breadthData={breadthData}
          daysInState={daysInState}
          playbook={playbook}
          range={historyRange}
          rotation={rotation}
          leadersBySector={leadersBySector}
        />
      </Suspense>
    </div>
  )
}
