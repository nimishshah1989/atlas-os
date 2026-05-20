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
import { getEffectivePolicy } from '@/lib/queries/policy'
import { getCurrentRegime } from '@/lib/queries/regime'
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
import { ActButton } from '@/components/portfolio/ActButton'

// ---------------------------------------------------------------------------
// Position-sizing helper (TS port of atlas/intelligence/policy/sizing.py)
// All values in whole-number percent as strings for safe Decimal arithmetic.
// ---------------------------------------------------------------------------

type SizingResult = { suggestedPct: string; bindingConstraint: string }

function computeSizing(
  maxPerStockPct: string,
  deploymentMultiplier: string,
): SizingResult {
  // max_per_stock and regime_cap are real values.
  // target_gap: not yet wired → treat as max_per_stock (gap cap does not bind tighter).
  // current_invested: not yet wired → treat as 0 (upper bound, conservative).
  const maxPs = parseFloat(maxPerStockPct)
  // deployment_multiplier is a fraction 0.0–1.0 → convert to whole-number percent
  const regimeCap = parseFloat(deploymentMultiplier) * 100
  const regimeRoom = regimeCap - 0 // current_invested assumed 0
  const targetGap = maxPs // not wired: defaults to maxPs so it doesn't bind

  const raw = Math.min(targetGap, maxPs, regimeRoom)
  const suggested = Math.max(raw, 0)

  let binding: string
  if (suggested <= 0) {
    if (targetGap <= 0) binding = 'target_gap'
    else binding = 'regime_cap'
  } else if (raw === targetGap && raw === maxPs) {
    binding = 'max_per_stock' // tie: max_per_stock wins (targetGap == maxPs by design)
  } else if (raw === maxPs) {
    binding = 'max_per_stock'
  } else {
    binding = 'regime_cap'
  }

  return { suggestedPct: suggested.toFixed(1), bindingConstraint: binding }
}

export default async function StockPage({
  params,
  searchParams,
}: {
  params: Promise<{ symbol: string }>
  searchParams?: Promise<{ portfolio?: string }>
}) {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase()
  const stock = await getStockBySymbol(symbol)
  if (!stock) notFound()

  // Read ?portfolio= searchParam for the Act affordance.
  const resolvedSearch = searchParams ? await searchParams : {}
  const portfolioId = resolvedSearch.portfolio?.trim() || undefined

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

  // ---- Act affordance: load policy + regime when a portfolio is active ----
  // Both values are real data from the DB. target_gap and current_invested
  // are not yet wired (stock-detail has no portfolio holdings) — see approach doc.
  let actSuggestedPct: string | null = null
  let actBindingConstraint: string | null = null
  let actPortfolioName: string | undefined

  if (portfolioId) {
    try {
      const [policy, regime] = await Promise.all([
        getEffectivePolicy(portfolioId),
        getCurrentRegime(),
      ])
      // Portfolio display name: not available without an extra query.
      // Use the portfolioId as a fallback label for now (Task 3.5 will surface names).
      actPortfolioName = `Portfolio ${portfolioId.slice(0, 8)}`
      if (policy !== null && regime !== null) {
        const maxPerStock = (policy.max_per_stock_pct.value as string | null) ?? '5'
        const deployMult = regime.deployment_multiplier ?? '1'
        const sizing = computeSizing(maxPerStock, deployMult)
        actSuggestedPct = sizing.suggestedPct
        actBindingConstraint = sizing.bindingConstraint
      }
    } catch {
      // Non-fatal: ActButton will render disabled if sizing not available.
    }
  }

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

      <div className="px-6 pb-10 border-t border-paper-rule pt-6">
        <div className="flex flex-col gap-2">
          <h2 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Act
          </h2>
          <ActButton
            portfolioId={portfolioId}
            portfolioName={actPortfolioName}
            instrumentId={stock.instrument_id}
            suggestedPct={actSuggestedPct}
            bindingConstraint={actBindingConstraint}
          />
        </div>
      </div>
    </div>
  )
}
