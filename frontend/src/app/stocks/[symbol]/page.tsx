export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import { getStockBySymbol, getStockMetricHistory, getStockStateHistory } from '@/lib/queries/stocks'
import { StockDeepDiveHeader } from '@/components/stocks/StockDeepDiveHeader'
import { StockSnapshotTiles } from '@/components/stocks/StockSnapshotTiles'
import { StockDeepDiveBody } from '@/components/stocks/StockDeepDiveBody'

export default async function StockPage({
  params,
}: {
  params: Promise<{ symbol: string }>
}) {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase()
  const stock = await getStockBySymbol(symbol)
  if (!stock) notFound()

  const [metricHistory, stateHistory] = await Promise.all([
    getStockMetricHistory(stock.instrument_id, 180),
    getStockStateHistory(stock.instrument_id, 180),
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
    </div>
  )
}
