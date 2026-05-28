export const dynamic = 'force-dynamic'

import { notFound, redirect } from 'next/navigation'
import { lookupSymbolAlias } from '@/lib/queries/symbol-aliases'
import {
  getStockBySymbol,
  getStockMetricHistory,
  getStockOBVSeries,
  getStockATRContraction,
  getStockFooterMetrics,
} from '@/lib/queries/stocks'
import { getTVMetrics } from '@/lib/api/v1'
import {
  getStockState,
  getCohortBaseline,
  getStockCohortKey,
  getWithinStatePeers,
  getStateHistory,
} from '@/lib/queries/states'
import { getComponentValidations } from '@/lib/queries/component_validation'
import { getHitRateForStock } from '@/lib/queries/weight_performance'
import { getStaticPortfolioById } from '@/lib/queries/portfolios'
import { getEffectivePolicy } from '@/lib/queries/policy'
import { getCurrentRegime } from '@/lib/queries/regime'
import { StockDeepDiveHeader } from '@/components/stocks/StockDeepDiveHeader'
import { TraderViewHeader } from '@/components/v6/stocks/TraderViewHeader'
import { getStockTraderHeader } from '@/lib/queries/v6/stock-trader-header'
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
import { computeSizing } from '@/lib/position-sizing'

export default async function StockPage({
  params,
  searchParams,
}: {
  params: Promise<{ symbol: string }>
  searchParams?: Promise<{ portfolio?: string }>
}) {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase()
  const stock = await getStockBySymbol(symbol)
  if (!stock) {
    // Try alias lookup (NSE renames / demergers) before giving up.
    // e.g. TATAMOTORS -> TMPV, ZOMATO -> ETERNAL, L&TFH -> LTF
    const alias = await lookupSymbolAlias(symbol)
    if (alias) redirect(`/stocks/${alias}?renamed_from=${symbol}`)
    notFound()
  }

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
    traderHeader,
    tvMetrics,
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
    getStockTraderHeader(symbol),
    // TV-05: TradingView screener metrics for Chart tab + hero badge.
    // Graceful null if symbol not in tv_metrics table or network failure.
    getTVMetrics(symbol).catch(() => null),
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
  let actSectorGapApplied = false

  if (portfolioId) {
    try {
      const [policy, regime, portfolioDetail] = await Promise.all([
        getEffectivePolicy(portfolioId),
        getCurrentRegime(),
        getStaticPortfolioById(portfolioId),
      ])
      // Real portfolio name from DB; fall back to ID prefix only if detail is null.
      actPortfolioName = portfolioDetail?.name ?? `Portfolio ${portfolioId.slice(0, 8)}`
      // current_invested = sum of existing holding weights (whole-number percent).
      // weight_pct in the JSONB is stored as a numeric value; coerce with Number()
      // to handle any cases where the postgres.js driver returns it as a string.
      const currentInvested =
        portfolioDetail?.instruments.reduce(
          (acc, i) => acc + Number(i.weight_pct),
          0,
        ) ?? 0
      if (policy !== null && regime !== null) {
        const maxPerStock = (policy.max_per_stock_pct.value as string | null) ?? '5'
        const deployMult = regime.deployment_multiplier ?? '1'
        const sizing = computeSizing(maxPerStock, deployMult, currentInvested)
        actSuggestedPct = sizing.suggestedPct
        actBindingConstraint = sizing.bindingConstraint
        actSectorGapApplied = sizing.sectorGapApplied
      }
    } catch {
      // Non-fatal: ActButton will render disabled if sizing not available.
    }
  }

  return (
    <div className="max-w-[1200px] mx-auto">
      <TraderViewHeader data={traderHeader} />
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
        <section className="px-6 py-6 border-b border-paper-rule">
          <h2 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-4">
            Signal evidence
          </h2>
          {/* ATR contraction is a Stage-2 breakout signal — irrelevant for
              Stage 1 (still basing) and Stage 4 (declining) stocks. Show
              OBV alone in those states; 2-up layout when both apply.
              Matches [[two-up-chart-layout]] memory. */}
          {(stockState.state === 'stage_2a' || stockState.state === 'stage_2b' || stockState.state === 'stage_2c') ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <OBVContinuousChart series={obvSeries} />
              <ATRContractionGauge data={atrContraction} />
            </div>
          ) : (
            <OBVContinuousChart series={obvSeries} />
          )}
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

      {/* State history (Weinstein stage timeline) demoted to expandable
          "Show the math" per A3 amendment 2026-05-28 — Weinstein is a
          context signal, not a prominent verdict input. The cell-math
          composite carries the verdict load. See
          docs/v6/2026-05-28-weinstein-a3-report.md. */}
      {stockState && stateHistory.length > 0 && (
        <section className="px-6 py-4 border-b border-paper-rule">
          <details className="font-sans text-[12px] text-ink-secondary">
            <summary className="cursor-pointer text-accent font-medium select-none">
              Show Weinstein stage history (context only — not a verdict input)
            </summary>
            <div className="pt-4">
              <DwellTimeline history={stateHistory} />
            </div>
          </details>
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
            sectorGapApplied={actSectorGapApplied}
          />
        </div>
      </div>
    </div>
  )
}
