export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import {
  getStockBySymbol,
  getStockMetricHistory,
  getStockOBVSeries,
  getStockATRContraction,
  getStockFooterMetrics,
} from '@/lib/queries/stocks'
import {
  getStockState,
  getCohortBaseline,
  getStockCohortKey,
  getWithinStatePeers,
  getStateHistory,
} from '@/lib/queries/states'
import { getComponentValidations } from '@/lib/queries/component_validation'
import { getHitRateForStock } from '@/lib/queries/weight_performance'
import { StockDeepDiveHeader } from '@/components/stocks/StockDeepDiveHeader'
import { StockDeepDiveBody } from '@/components/stocks/StockDeepDiveBody'
import { IntradayStockBadge } from '@/components/stocks/IntradayStockBadge'
import { MasterStateCard } from '@/components/stocks/MasterStateCard'
import { ComponentScorecard } from '@/components/stocks/ComponentScorecard'
import { OBVContinuousChart } from '@/components/stocks/OBVContinuousChart'
import { ATRContractionGauge } from '@/components/stocks/ATRContractionGauge'
import { WithinStatePeers } from '@/components/stocks/WithinStatePeers'
import { DwellTimeline } from '@/components/stocks/DwellTimeline'
import { HitRateRow } from '@/components/stocks/HitRateRow'

export default async function StockPage({
  params,
}: {
  params: Promise<{ symbol: string }>
}) {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase()
  const stock = await getStockBySymbol(symbol)
  if (!stock) notFound()

  const [
    metricHistory,
    stockState,
    cohortKey,
    stateHistory,
    obvSeries,
    atrContraction,
    validations,
    hitRate,
    footerMetrics,
  ] = await Promise.all([
    getStockMetricHistory(stock.instrument_id, 365),
    getStockState(stock.instrument_id),
    getStockCohortKey(stock.instrument_id),
    getStateHistory(stock.instrument_id, 252),
    getStockOBVSeries(stock.instrument_id, 50),
    getStockATRContraction(stock.instrument_id),
    getComponentValidations(),
    getHitRateForStock(stock.instrument_id, 20),
    getStockFooterMetrics(stock.instrument_id),
  ])

  const [cohortBaseline, peers] = stockState
    ? await Promise.all([
        getCohortBaseline(cohortKey, stockState.state),
        getWithinStatePeers(stockState.state, stockState.date, 30),
      ])
    : [null, []]

  const peerRank = stockState && peers.length > 0
    ? (peers.findIndex(p => p.instrument_id === stock.instrument_id) + 1) || null
    : null

  return (
    <div className="max-w-[1200px] mx-auto">
      <StockDeepDiveHeader stock={stock} />

      {stockState && (
        <MasterStateCard
          symbol={stock.symbol}
          state={stockState}
          cohortBaseline={cohortBaseline}
          peerRank={peerRank}
          peerTotal={peers.length}
        />
      )}

      <div className="px-6 py-2 border-b border-paper-rule">
        <IntradayStockBadge instrumentId={stock.instrument_id} />
      </div>

      {!stockState && (
        <div className="px-6 py-6 border-b border-paper-rule">
          <p className="font-sans text-sm text-ink-tertiary">
            No state classification available for this stock yet.
          </p>
        </div>
      )}

      {stockState && (
        <section className="px-6 py-6 border-b border-paper-rule space-y-6">
          <h2 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Signal evidence
          </h2>
          <OBVContinuousChart series={obvSeries} />
          <ATRContractionGauge data={atrContraction} />
        </section>
      )}

      {stockState && peers.length > 0 && (
        <section className="px-6 py-6 border-b border-paper-rule">
          <WithinStatePeers
            peers={peers}
            currentInstrumentId={stock.instrument_id}
            state={stockState.state}
          />
        </section>
      )}

      {stockState && stateHistory.length > 0 && (
        <section className="px-6 py-6 border-b border-paper-rule">
          <DwellTimeline history={stateHistory} />
        </section>
      )}

      {stockState && (
        <ComponentScorecard
          state={stockState}
          validations={validations}
          obvSlope={footerMetrics.obv_slope}
          atrRatio={footerMetrics.atr_ratio}
          realizedVolTier={footerMetrics.realized_vol_tier}
        />
      )}

      <StockDeepDiveBody
        stock={stock}
        metricHistory={metricHistory}
      />

      <div className="px-6 pb-10">
        <HitRateRow hitRate={hitRate} />
      </div>
    </div>
  )
}
