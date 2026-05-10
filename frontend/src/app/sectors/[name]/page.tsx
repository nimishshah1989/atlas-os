// frontend/src/app/sectors/[name]/page.tsx
import { notFound } from 'next/navigation'
import { Suspense } from 'react'
import {
  getSectorSnapshotByName,
  getStocksInSector,
} from '@/lib/queries/sector-deep-dive'
import {
  getBreadthWaterfallData,
  getSectorMetricHistory,
  getSectorStateHistory,
} from '@/lib/queries/sectors'
import { getLinkedETFsForSector } from '@/lib/queries/etfs'
import { getSectorFunds } from '@/lib/queries/sector-funds'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { getSectorDecision } from '@/lib/sectors-decision'
import { getCurrentRegime } from '@/lib/queries/regime'
import { SectorDeepDiveHeader } from '@/components/sectors/SectorDeepDiveHeader'
import { SectorDeepDiveTabs } from '@/components/sectors/SectorDeepDiveTabs'
import { SectorOverviewTab } from '@/components/sectors/SectorOverviewTab'
import { SectorStocksTab } from '@/components/sectors/SectorStocksTab'
import { SectorETFTab } from '@/components/sectors/SectorETFTab'
import { SectorFundsTab } from '@/components/sectors/SectorFundsTab'

type SearchParams = Promise<{ range?: string; tab?: string }>
type Params = Promise<{ name: string }>

export default async function SectorDeepDivePage({
  params,
  searchParams,
}: {
  params: Params
  searchParams: SearchParams
}) {
  const { name: rawName } = await params
  const { range = '6M', tab = 'overview' } = await searchParams

  const sectorName = decodeURIComponent(rawName)
  const VALID_RANGES: TimeRange[] = ['1W', '1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)
  const activeTab = (['overview', 'stocks', 'etf', 'funds'] as const).includes(
    tab as 'overview' | 'stocks' | 'etf' | 'funds',
  )
    ? (tab as 'overview' | 'stocks' | 'etf' | 'funds')
    : 'overview'

  const [snapshot, metricHistory, stateHistory, stocks, regime, breadthData, linkedETFs, sectorFunds] =
    await Promise.all([
      getSectorSnapshotByName(sectorName),
      getSectorMetricHistory(sectorName, days).catch(() => [] as Awaited<ReturnType<typeof getSectorMetricHistory>>),
      getSectorStateHistory(days).catch(() => [] as Awaited<ReturnType<typeof getSectorStateHistory>>),
      getStocksInSector(sectorName).catch(() => [] as Awaited<ReturnType<typeof getStocksInSector>>),
      getCurrentRegime(),
      getBreadthWaterfallData(sectorName, 1095).catch(() => [] as Awaited<ReturnType<typeof getBreadthWaterfallData>>),
      getLinkedETFsForSector(sectorName).catch(() => []),
      getSectorFunds(sectorName).catch(() => []),
    ])

  if (!snapshot) {
    notFound()
  }

  const decision = getSectorDecision(
    snapshot.sector_state,
    snapshot.bottomup_rs_state,
    snapshot.bottomup_momentum_state,
  )
  const sectorWithDecision = { ...snapshot, decision }
  const sectorStateHistoryForThis = stateHistory.filter(h => h.sector_name === sectorName)

  return (
    <div className="max-w-[1400px] mx-auto">
      <SectorDeepDiveHeader
        snapshot={sectorWithDecision}
        range={historyRange}
      />
      <Suspense fallback={null}>
        <SectorDeepDiveTabs
          sectorName={sectorName}
          activeTab={activeTab}
          range={historyRange}
        />
      </Suspense>

      {activeTab === 'overview' && (
        <SectorOverviewTab
          snapshot={sectorWithDecision}
          metricHistory={metricHistory}
          stateHistory={sectorStateHistoryForThis}
          range={historyRange}
          regime={regime}
          breadthData={breadthData}
        />
      )}
      {activeTab === 'stocks' && (
        <SectorStocksTab
          sectorName={sectorName}
          stocks={stocks}
          range={historyRange}
          regime={regime}
        />
      )}
      {activeTab === 'etf' && (
        <SectorETFTab etfs={linkedETFs} sectorName={sectorName} />
      )}
      {activeTab === 'funds' && (
        <SectorFundsTab funds={sectorFunds} sectorName={sectorName} />
      )}
    </div>
  )
}
