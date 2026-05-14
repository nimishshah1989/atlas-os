export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import {
  getCountryByTicker,
  getCountryMetricHistory,
  getCountryStateHistory,
} from '@/lib/queries/global'
import { CountryDeepDiveHeader } from '@/components/global/CountryDeepDiveHeader'
import { CountrySnapshotTiles } from '@/components/global/CountrySnapshotTiles'
import { CountryDeepDiveTabs } from '@/components/global/CountryDeepDiveTabs'

type Params = Promise<{ ticker: string }>
type SearchParams = Promise<{ range?: string; tab?: string }>

export default async function CountryDetailPage({
  params,
  searchParams,
}: {
  params: Params
  searchParams: SearchParams
}) {
  const { ticker: rawTicker } = await params
  const { range = '6M', tab = 'overview' } = await searchParams

  const ticker = decodeURIComponent(rawTicker).toLowerCase()
  const VALID_RANGES: TimeRange[] = ['1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)
  const activeTab = (['overview', 'matrix'] as const).includes(tab as 'overview' | 'matrix')
    ? (tab as 'overview' | 'matrix')
    : 'overview'

  const [country, metricHistory, stateHistory] = await Promise.all([
    getCountryByTicker(ticker),
    getCountryMetricHistory(ticker, days).catch(() => []),
    getCountryStateHistory(ticker, days).catch(() => []),
  ])

  if (!country) notFound()

  return (
    <div className="max-w-[1400px] mx-auto">
      <CountryDeepDiveHeader country={country} />
      <CountrySnapshotTiles country={country} />
      <CountryDeepDiveTabs
        country={country}
        metricHistory={metricHistory}
        stateHistory={stateHistory}
        activeTab={activeTab}
        range={historyRange}
      />
    </div>
  )
}
