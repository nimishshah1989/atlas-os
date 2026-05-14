export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import {
  getUSSectorByName,
  getUSStocksInSector,
  getUSSectorMetricHistory,
} from '@/lib/queries/us-sectors'
import { USSectorDeepDiveHeader } from '@/components/us/USSectorDeepDiveHeader'
import { USSectorDetailTabs } from '@/components/us/USSectorDetailTabs'

type Params = Promise<{ name: string }>
type SearchParams = Promise<{ range?: string; tab?: string }>

export default async function USSectorDetailPage({
  params,
  searchParams,
}: {
  params: Params
  searchParams: SearchParams
}) {
  const { name: rawName } = await params
  const { range = '6M', tab = 'overview' } = await searchParams

  const sectorName = decodeURIComponent(rawName)
  const VALID_RANGES: TimeRange[] = ['1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)
  const activeTab = (['overview', 'stocks'] as const).includes(tab as 'overview' | 'stocks')
    ? (tab as 'overview' | 'stocks')
    : 'overview'

  const [sector, stocks, metricHistory] = await Promise.all([
    getUSSectorByName(sectorName),
    getUSStocksInSector(sectorName).catch(() => []),
    getUSSectorMetricHistory(sectorName, days).catch(() => []),
  ])

  if (!sector) notFound()

  return (
    <div className="max-w-[1400px] mx-auto">
      <USSectorDeepDiveHeader sector={sector} sectorName={sectorName} />
      <USSectorDetailTabs
        sectorName={sectorName}
        sector={sector}
        stocks={stocks}
        metricHistory={metricHistory}
        activeTab={activeTab}
        range={historyRange}
      />
    </div>
  )
}
