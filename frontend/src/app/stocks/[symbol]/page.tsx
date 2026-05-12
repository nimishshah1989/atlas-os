export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import { getStockBySymbol, getStockMetricHistory, getStockStateHistory } from '@/lib/queries/stocks'
import { getStockConviction, getConvictionBreakdown } from '@/lib/queries/conviction'
import { StockDeepDiveHeader } from '@/components/stocks/StockDeepDiveHeader'
import { StockSnapshotTiles } from '@/components/stocks/StockSnapshotTiles'
import { StockDeepDiveBody } from '@/components/stocks/StockDeepDiveBody'
import { ConvictionBreakdownPanel } from '@/components/stocks/ConvictionBreakdownPanel'

export default async function StockPage({
  params,
}: {
  params: Promise<{ symbol: string }>
}) {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase()
  const stock = await getStockBySymbol(symbol)
  if (!stock) notFound()

  const [metricHistory, stateHistory, conviction, breakdown] = await Promise.all([
    getStockMetricHistory(stock.instrument_id, 180),
    getStockStateHistory(stock.instrument_id, 180),
    getStockConviction(stock.instrument_id),
    getConvictionBreakdown(stock.instrument_id),
  ])

  return (
    <div className="max-w-[1200px] mx-auto">
      <StockDeepDiveHeader stock={stock} />
      <StockSnapshotTiles stock={stock} />
      <StockDeepDiveBody
        stock={stock}
        metricHistory={metricHistory}
        stateHistory={stateHistory}
      />
      <div className="px-6 pb-10">
        <ConvictionBreakdownPanel conviction={conviction} breakdown={breakdown} />
      </div>
    </div>
  )
}
