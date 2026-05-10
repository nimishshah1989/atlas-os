export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import {
  getETFByTicker,
  getETFMetricHistory,
  getETFStateHistory,
  getETFHoldings,
} from '@/lib/queries/etfs'
import { ETFDeepDiveHeader } from '@/components/etfs/ETFDeepDiveHeader'
import { ETFSnapshotTiles } from '@/components/etfs/ETFSnapshotTiles'
import { ETFDeepDiveTabs } from '@/components/etfs/ETFDeepDiveTabs'

export default async function ETFPage({
  params,
}: {
  params: Promise<{ ticker: string }>
}) {
  const { ticker } = await params
  const decoded = decodeURIComponent(ticker)

  const [etf, metricHistory, stateHistory, holdings] = await Promise.all([
    getETFByTicker(decoded),
    getETFMetricHistory(decoded, 180),
    getETFStateHistory(decoded, 180),
    getETFHoldings(decoded, 20),
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
      />
    </div>
  )
}
