export const dynamic = 'force-dynamic'

import { notFound, redirect } from 'next/navigation'
import { lookupSymbolAlias } from '@/lib/queries/symbol-aliases'
import {
  getStockBySymbol,
  getStockMetricHistory,
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
import { TraderViewHeader } from '@/components/v6/stocks/TraderViewHeader'
import { getStockTraderHeader } from '@/lib/queries/v6/stock-trader-header'
import { ComponentScorecard } from '@/components/stocks/ComponentScorecard'
import { DwellTimeline } from '@/components/stocks/DwellTimeline'
import { HitRateRow } from '@/components/stocks/HitRateRow'
import { ActButton } from '@/components/portfolio/ActButton'
import { computeSizing } from '@/lib/position-sizing'
import { getRSRatios, getPeerMatrix } from '@/lib/queries/v6/stock-detail'
import { EventHeader } from '@/components/v6/stock-detail/EventHeader'
import { StockChartPanel } from '@/components/v6/stock-detail/StockChartPanel'
import { RSConfirmationPanel } from '@/components/v6/stock-detail/RSConfirmationPanel'
import { LifecyclePanel } from '@/components/v6/stock-detail/LifecyclePanel'
import { PeerMatrix } from '@/components/v6/stock-detail/PeerMatrix'
import { generateChartCommentary } from '@/components/v6/stock-detail/ChartCommentary'

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
    validations,
    hitRate,
    footerMetrics,
    traderHeader,
    tvMetrics,
    rsRatios,
    peerMatrix,
  ] = await Promise.all([
    getStockMetricHistory(stock.instrument_id, 365),
    getStockState(stock.instrument_id),
    getStockCohortKey(stock.instrument_id),
    getStateHistory(stock.instrument_id, 252),
    getComponentValidations(),
    getHitRateForStock(stock.instrument_id, 20),
    getStockFooterMetrics(stock.instrument_id),
    getStockTraderHeader(symbol),
    // TV-05: TradingView screener metrics for Chart tab + hero badge.
    // Graceful null if symbol not in tv_metrics table or network failure.
    getTVMetrics(symbol).catch(() => null),
    getRSRatios(symbol).catch(() => null),
    getPeerMatrix(symbol).catch(() => []),
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

  const latestMetrics = metricHistory.length > 0 ? metricHistory[metricHistory.length - 1] : null

  const commentary = generateChartCommentary({
    state: stockState?.state ?? null,
    dwellDays: stockState?.dwell_days ?? null,
    stateSinceDate: null,
    ema20Ratio: latestMetrics?.ema_20_ratio != null ? parseFloat(latestMetrics.ema_20_ratio) : null,
    volRatio63: latestMetrics?.vol_ratio_63 != null ? parseFloat(latestMetrics.vol_ratio_63) : null,
    extension: latestMetrics?.extension_pct != null ? parseFloat(latestMetrics.extension_pct) : null,
    high52w: tvMetrics?.high_52w != null ? parseFloat(tvMetrics.high_52w) : null,
    price: tvMetrics?.price != null ? parseFloat(tvMetrics.price) : null,
  })

  return (
    <div className="max-w-[1200px] mx-auto">
      <TraderViewHeader data={traderHeader} />

      <EventHeader
        symbol={stock.symbol}
        companyName={stock.company_name ?? stock.symbol}
        sector={stock.sector ?? null}
        indexBadges={[
          stock.in_nifty_50  ? 'Nifty 50'  : null,
          stock.in_nifty_100 ? 'Nifty 100' : null,
          stock.in_nifty_500 ? 'Nifty 500' : null,
        ].filter(Boolean) as string[]}
        state={stockState?.state ?? null}
        dwellDays={stockState?.dwell_days ?? null}
        peerRank={peerRank}
        peerTotal={peers.length}
        convictionDirection={null}
        convictionTenure="3m"
        currentPrice={tvMetrics?.price != null ? parseFloat(tvMetrics.price) : null}
        ret3m={latestMetrics?.ret_3m != null ? parseFloat(latestMetrics.ret_3m) : null}
        rsVsNifty={latestMetrics?.rs_pctile_3m != null ? parseFloat(latestMetrics.rs_pctile_3m) : null}
      />

      <StockChartPanel
        symbol={stock.symbol}
        commentary={commentary}
        pe={tvMetrics?.pe_ttm ?? null}
        ps={tvMetrics?.ps_current ?? null}
        pb={tvMetrics?.pb_fbs ?? null}
        debtToEquity={tvMetrics?.debt_to_equity ?? null}
        roe={tvMetrics?.roe ?? null}
      />

      <RSConfirmationPanel rsData={rsRatios} symbol={stock.symbol} />

      <LifecyclePanel
        state={stockState?.state ?? null}
        dwellDays={stockState?.dwell_days ?? null}
        ema20Ratio={latestMetrics?.ema_20_ratio != null ? parseFloat(latestMetrics.ema_20_ratio) : null}
        volRatio63={latestMetrics?.vol_ratio_63 != null ? parseFloat(latestMetrics.vol_ratio_63) : null}
        extensionPct={latestMetrics?.extension_pct != null ? parseFloat(latestMetrics.extension_pct) : null}
      />

      {peerMatrix.length > 0 && <PeerMatrix peers={peerMatrix} />}

      <section className="px-6 py-6 border-b border-paper-rule space-y-6">
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink-3">Supporting Detail</h2>
        {stateHistory.length > 0 && (
          <details className="font-sans text-[12px] text-ink-3">
            <summary className="cursor-pointer text-accent font-medium select-none">
              Show Weinstein stage history (context only — not a verdict input)
            </summary>
            <div className="pt-4">
              <DwellTimeline history={stateHistory} />
            </div>
          </details>
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
        <HitRateRow hitRate={hitRate} />
      </section>

      <div className="px-6 pb-10 border-t border-paper-rule pt-6">
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-4">Act</h2>
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
  )
}
