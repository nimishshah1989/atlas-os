export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import {
  getETFByTicker,
  getETFMetricHistory,
  getETFStateHistory,
  getETFHoldings,
} from '@/lib/queries/etfs'
import { getETFLeaderHoldings } from '@/lib/queries/leaders'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { ETFDeepDiveHeader } from '@/components/etfs/ETFDeepDiveHeader'
import { ETFSnapshotTiles } from '@/components/etfs/ETFSnapshotTiles'
import { ETFDeepDiveTabs } from '@/components/etfs/ETFDeepDiveTabs'
import { LeaderHoldingsPanel } from '@/components/ui/LeaderHoldingsPanel'

type Params = Promise<{ ticker: string }>
type SearchParams = Promise<{ tab?: string; range?: string }>

export default async function ETFPage({
  params,
  searchParams,
}: {
  params: Params
  searchParams: SearchParams
}) {
  const { ticker } = await params
  const { tab = 'overview', range = '6M' } = await searchParams
  const decoded = decodeURIComponent(ticker)

  const VALID_RANGES: TimeRange[] = ['1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)

  const [etf, metricHistory, stateHistory, holdings, leaderHoldings] = await Promise.all([
    getETFByTicker(decoded),
    getETFMetricHistory(decoded, days),
    getETFStateHistory(decoded, days),
    getETFHoldings(decoded, 20),
    getETFLeaderHoldings(decoded).catch(() => []),
  ])

  if (!etf) notFound()

  return (
    <div className="max-w-[1400px] mx-auto">
      <ETFDeepDiveHeader etf={etf} />
      <ETFSnapshotTiles etf={etf} />
      <ETFDeepDiveTabs
        etf={etf}
        metricHistory={metricHistory}
        stateHistory={stateHistory}
        holdings={holdings}
        range={historyRange}
        initialTab={tab}
      />
      {leaderHoldings.length > 0 && (
        <div className="px-6 py-6 border-t border-paper-rule">
          <LeaderHoldingsPanel holdings={leaderHoldings} />
        </div>
      )}
    </div>
  )
}
