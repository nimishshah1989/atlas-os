// allow-large: stock detail page composes 14 sections (verdict, returns table, chart, RS confirmation, sparkline grid, lifecycle, TV technical analysis, peer matrix, financials, news, supporting detail drawers, act). Each section is a single line render — splitting into sub-shells would obscure the page assembly contract.
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
import { SparklineTrajectoryGrid } from '@/components/v6/stock-detail/SparklineTrajectoryGrid'
import { MultiTimeframeReturnsTable } from '@/components/v6/stock-detail/MultiTimeframeReturnsTable'
import { GatesPanel } from '@/components/v6/stock-detail/GatesPanel'
import { ConvictionDecompositionPanel } from '@/components/v6/stock-detail/ConvictionDecompositionPanel'
import { SectorContextStrip } from '@/components/v6/stock-detail/SectorContextStrip'
import { SignalCallHistoryTable } from '@/components/v6/stock-detail/SignalCallHistoryTable'
import { getConvictionWithSignals, getSectorContextForStock, getMarketRegime } from '@/lib/queries/v6/stock-detail-extra'
import { getSignalCallsByIid } from '@/lib/queries/v6/recent_signal_calls'
import {
  TVTechnicalAnalysis,
  TVFinancials,
  TVCompanyProfile,
  TVNews,
  TVMiniOverview,
} from '@/components/v6/stock-detail/TVWidgets'

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
    const alias = await lookupSymbolAlias(symbol)
    if (alias) redirect(`/stocks/${alias}?renamed_from=${symbol}`)
    notFound()
  }

  const resolvedSearch = searchParams ? await searchParams : {}
  const portfolioId = resolvedSearch.portfolio?.trim() || undefined

  // Batch 1 — core stock data (8 connections concurrent)
  const [
    metricHistory,
    stockState,
    cohortKey,
    stateHistory,
    validations,
    hitRate,
    footerMetrics,
    traderHeader,
  ] = await Promise.all([
    getStockMetricHistory(stock.instrument_id, 365),
    getStockState(stock.instrument_id),
    getStockCohortKey(stock.instrument_id),
    getStateHistory(stock.instrument_id, 252),
    getComponentValidations(),
    getHitRateForStock(stock.instrument_id, 20),
    getStockFooterMetrics(stock.instrument_id),
    getStockTraderHeader(symbol),
  ])

  // Batch 2 — external/dependent data (after batch 1 connections released)
  const [tvMetrics, rsRatios, peerMatrix, peers, conviction, signalCalls, regimeState] = await Promise.all([
    getTVMetrics(symbol).catch(() => null),
    getRSRatios(symbol).catch(() => null),
    getPeerMatrix(symbol).catch(() => []),
    stockState ? getWithinStatePeers(stockState.state, stockState.date, 30) : Promise.resolve([]),
    getConvictionWithSignals(stock.instrument_id).catch(() => null),
    getSignalCallsByIid(stock.instrument_id, 20).catch(() => []),
    getMarketRegime().catch(() => null),
  ])

  // Sector context needs sector name — fetch after we know it exists
  const sectorContext = stock.sector
    ? await getSectorContextForStock(stock.sector, stock.instrument_id).catch(() => null)
    : null

  // cohortKey used by getCohortBaseline upstream; keep ref to silence lint
  void cohortKey

  const peerRank = stockState && peers.length > 0
    ? (peers.findIndex(p => p.instrument_id === stock.instrument_id) + 1) || null
    : null

  // ---- Act affordance: load policy + regime when a portfolio is active ----
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
      actPortfolioName = portfolioDetail?.name ?? `Portfolio ${portfolioId.slice(0, 8)}`
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
      // non-fatal
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

  // Sector index for the RS mini overview (lookup of well-known Nifty sectoral indices)
  const sectorIndex = sectorIndexForSector(stock.sector)

  return (
    <div className="max-w-[1400px] mx-auto">
      <TraderViewHeader data={traderHeader} />

      {/* ────────────── 1. Event Header ────────────── */}
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

      {/* ────────────── 2a. Investability Gates + Returns table ────────────── */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4 px-6 py-4 border-b border-paper-rule bg-paper-deep">
        <GatesPanel
          rsPctile3m={latestMetrics?.rs_pctile_3m != null ? parseFloat(latestMetrics.rs_pctile_3m) : null}
          ema20Ratio={latestMetrics?.ema_20_ratio != null ? parseFloat(latestMetrics.ema_20_ratio) : null}
          extensionPct={latestMetrics?.extension_pct != null ? parseFloat(latestMetrics.extension_pct) : null}
          sectorState={sectorContext?.sector_state ?? null}
          regimeState={regimeState}
        />
        <MultiTimeframeReturnsTable latest={latestMetrics ?? null} />
      </section>

      {/* ────────────── 2b. Sector context strip ────────────── */}
      <SectorContextStrip
        sectorName={stock.sector ?? null}
        sectorState={sectorContext?.sector_state ?? null}
        breadth={sectorContext?.breadth ?? null}
        sectorRank={sectorContext?.sector_rank ?? null}
        totalSectors={sectorContext?.total_sectors ?? null}
        stockRankInSector={sectorContext?.stock_rank_in_sector ?? null}
        sectorSize={sectorContext?.sector_size ?? null}
      />

      {/* ────────────── 2c. Sector vs stock 12M sparklines ────────────── */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4 px-6 py-4 border-b border-paper-rule bg-paper-deep">
        <div className="border border-paper-rule rounded p-4 bg-paper">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-1">
            {sectorIndex ? `${sectorIndex.label}` : 'Nifty 50'} · 12-Month Sparkline
          </p>
          <TVMiniOverview symbol={sectorIndex?.tvSymbol ?? 'NIFTY'} exchange="NSE" dateRange="12M" />
        </div>
        <div className="border border-paper-rule rounded p-4 bg-paper">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-1">
            {stock.symbol} · 12-Month Sparkline
          </p>
          <TVMiniOverview symbol={stock.symbol} exchange="NSE" dateRange="12M" />
        </div>
      </section>

      {/* ────────────── 3. The Chart + Atlas Commentary + Fundamentals strip ────────────── */}
      <StockChartPanel
        symbol={stock.symbol}
        commentary={commentary}
        pe={tvMetrics?.pe_ttm ?? null}
        ps={tvMetrics?.ps_current ?? null}
        pb={tvMetrics?.pb_fbs ?? null}
        debtToEquity={tvMetrics?.debt_to_equity ?? null}
        roe={tvMetrics?.roe ?? null}
      />

      {/* ────────────── 4. RS Confirmation ────────────── */}
      <RSConfirmationPanel rsData={rsRatios} symbol={stock.symbol} />

      {/* ────────────── 4b. Conviction Decomposition ────────────── */}
      {conviction && (
        <section className="px-6 py-4 border-b border-paper-rule bg-paper-deep">
          <ConvictionDecompositionPanel
            signals={conviction.signals}
            convictionScore={conviction.conviction_score}
            confidenceLabel={conviction.confidence_label}
            backingIc={conviction.backing_ic}
            tier={conviction.tier}
          />
        </section>
      )}

      {/* ────────────── 5. Sparkline Trajectory Grid (12 Atlas metrics × 365D) ────────────── */}
      <SparklineTrajectoryGrid metricHistory={metricHistory} />

      {/* ────────────── 6. Lifecycle Position ────────────── */}
      <LifecyclePanel
        state={stockState?.state ?? null}
        dwellDays={stockState?.dwell_days ?? null}
        ema20Ratio={latestMetrics?.ema_20_ratio != null ? parseFloat(latestMetrics.ema_20_ratio) : null}
        volRatio63={latestMetrics?.vol_ratio_63 != null ? parseFloat(latestMetrics.vol_ratio_63) : null}
        extensionPct={latestMetrics?.extension_pct != null ? parseFloat(latestMetrics.extension_pct) : null}
      />

      {/* ────────────── 7. TradingView Technical Analysis Widget ────────────── */}
      <section className="px-6 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">
          TradingView Composite Technical Analysis — multi-timeframe consensus
        </p>
        <div className="border border-paper-rule rounded overflow-hidden bg-paper">
          <TVTechnicalAnalysis symbol={stock.symbol} interval="1D" />
        </div>
      </section>

      {/* ────────────── 8. Peer Matrix ────────────── */}
      {peerMatrix.length > 0 && <PeerMatrix peers={peerMatrix} />}

      {/* ────────────── 9. Fundamentals Widget ────────────── */}
      <section className="px-6 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">
          Financial Statements — revenue, EBITDA, EPS over time
        </p>
        <div className="border border-paper-rule rounded overflow-hidden bg-paper">
          <TVFinancials symbol={stock.symbol} />
        </div>
      </section>

      {/* ────────────── 10. News ────────────── */}
      <section className="px-6 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">
          Latest News — auto-updated from TradingView
        </p>
        <div className="border border-paper-rule rounded overflow-hidden bg-paper">
          <TVNews symbol={stock.symbol} />
        </div>
      </section>

      {/* ────────────── 11. Supporting Detail (collapsed by default) ────────────── */}
      <section className="px-6 py-6 border-b border-paper-rule space-y-4">
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink-3">Supporting Detail</h2>

        <details className="font-sans text-[12px] text-ink-3 border border-paper-rule rounded p-3 bg-paper">
          <summary className="cursor-pointer text-accent font-medium select-none">
            Show company profile (about, sector, employees, IPO)
          </summary>
          <div className="pt-3">
            <TVCompanyProfile symbol={stock.symbol} />
          </div>
        </details>

        <details className="font-sans text-[12px] text-ink-3 border border-paper-rule rounded p-3 bg-paper">
          <summary className="cursor-pointer text-accent font-medium select-none">
            Show signal_call audit ledger ({signalCalls.length} {signalCalls.length === 1 ? 'event' : 'events'})
          </summary>
          <div className="pt-3">
            <SignalCallHistoryTable events={signalCalls} />
          </div>
        </details>

        {stateHistory.length > 0 && (
          <details className="font-sans text-[12px] text-ink-3 border border-paper-rule rounded p-3 bg-paper">
            <summary className="cursor-pointer text-accent font-medium select-none">
              Show Weinstein stage history (context only — not a verdict input)
            </summary>
            <div className="pt-3">
              <DwellTimeline history={stateHistory} />
            </div>
          </details>
        )}

        {stockState && (
          <details className="font-sans text-[12px] text-ink-3 border border-paper-rule rounded p-3 bg-paper">
            <summary className="cursor-pointer text-accent font-medium select-none">
              Show component scorecard (5-family R/A/G grades)
            </summary>
            <div className="pt-3">
              <ComponentScorecard
                state={stockState}
                validations={validations}
                obvSlope={footerMetrics.obv_slope}
                atrRatio={footerMetrics.atr_ratio}
                realizedVolTier={footerMetrics.realized_vol_tier}
              />
            </div>
          </details>
        )}

        <HitRateRow hitRate={hitRate} />
      </section>

      {/* ────────────── 12. Act ────────────── */}
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

// TV-confirmed NSE index symbols (verified against symbol-search.tradingview.com).
// Important: TV uses `NIFTY` for Nifty 50, `BANKNIFTY` for Nifty Bank, `CNXENERGY` for Nifty Energy.
function sectorIndexForSector(sector: string | null | undefined): { label: string; tvSymbol: string } | null {
  if (!sector) return null
  const map: Record<string, { label: string; tvSymbol: string }> = {
    'Energy':                              { label: 'Nifty Energy',           tvSymbol: 'CNXENERGY' },
    'Oil Gas & Consumable Fuels':          { label: 'Nifty Oil & Gas',        tvSymbol: 'NIFTY_OIL_AND_GAS' },
    'Information Technology':              { label: 'Nifty IT',               tvSymbol: 'CNXIT' },
    'Financial Services':                  { label: 'Nifty Financial',        tvSymbol: 'CNXFINANCE' },
    'Banks':                               { label: 'Nifty Bank',             tvSymbol: 'BANKNIFTY' },
    'Fast Moving Consumer Goods':          { label: 'Nifty FMCG',             tvSymbol: 'CNXFMCG' },
    'Pharmaceuticals & Biotechnology':     { label: 'Nifty Pharma',           tvSymbol: 'CNXPHARMA' },
    'Automobiles & Auto Components':       { label: 'Nifty Auto',             tvSymbol: 'CNXAUTO' },
    'Metals & Mining':                     { label: 'Nifty Metal',            tvSymbol: 'CNXMETAL' },
    'Realty':                              { label: 'Nifty Realty',           tvSymbol: 'CNXREALTY' },
    'Consumer Durables':                   { label: 'Nifty Consumer Durables', tvSymbol: 'NIFTY_CONSR_DURBL' },
    'Telecommunication':                   { label: 'Nifty Media',            tvSymbol: 'CNXMEDIA' },
    'Healthcare':                          { label: 'Nifty Healthcare',       tvSymbol: 'NIFTY_HEALTHCARE' },
    'Chemicals':                           { label: 'Nifty Chemicals',        tvSymbol: 'NIFTY_CHEMICALS' },
    'Power':                               { label: 'Nifty Energy',           tvSymbol: 'CNXENERGY' },
    'Capital Goods':                       { label: 'Nifty India Mfg.',       tvSymbol: 'NIFTY_INDIA_MFG' },
  }
  return map[sector] ?? null
}
