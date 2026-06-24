// allow-large: ETF detail page composes 14 sections (verdict, gates, returns, sector context, mini-sparklines, chart+commentary, NAV-fair-value, tracking error, peer matrix, sparkline trajectory grid, technical analysis, holdings, news, supporting drawers). Mirrors the stock detail template; splitting into sub-shells would obscure the page assembly contract.
export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import {
  getETFByTicker,
  getETFMetricHistory,
  getETFStateHistory,
  getETFHoldings,
} from '@/lib/queries/etfs'
import { getETFLeaderHoldings } from '@/lib/queries/leaders'
import { getEtfDeepdive } from '@/lib/queries/v6/etfs'
import { getMarketRegime } from '@/lib/queries/v6/stock-detail-extra'
import { ETFDeepDiveTabs } from '@/components/etfs/ETFDeepDiveTabs'
import { LeaderHoldingsPanel } from '@/components/ui/LeaderHoldingsPanel'
import { EtfHeroStrip } from '@/components/v6/etfs/EtfHeroStrip'
import { PriceMultidim180d } from '@/components/v6/etfs/PriceMultidim180d'
import { NavVsMarketPrice } from '@/components/v6/etfs/NavVsMarketPrice'
import { TrackingError12m } from '@/components/v6/etfs/TrackingError12m'
import { PeerSetTable } from '@/components/v6/etfs/PeerSetTable'
import { ETFGatesPanel } from '@/components/v6/etf-detail/ETFGatesPanel'
import { ETFReturnsTable } from '@/components/v6/etf-detail/ETFReturnsTable'
import { ETFSparklineTrajectoryGrid } from '@/components/v6/etf-detail/ETFSparklineTrajectoryGrid'
import {
  TVTechnicalAnalysis,
  TVNews,
  TVCompanyProfile,
  TVMiniOverview,
} from '@/components/v6/stock-detail/TVWidgets'
import { LENS_V4_ENABLED } from '@/lib/feature-flags'
import { ETFDetailV4 } from '@/components/v6/etfs/ETFDetailV4'

type Params = Promise<{ ticker: string }>
type SearchParams = Promise<{ tab?: string; range?: string }>

export default async function ETFPage({
  params,
  searchParams,
}: {
  params: Params
  searchParams: SearchParams
}) {
  const { ticker } = await params
  const { tab = 'overview' } = await searchParams
  const decoded = decodeURIComponent(ticker)

  // v4 lens-first ETF detail (fcode-keyed). Flag-off path below is byte-identical.
  if (LENS_V4_ENABLED) return <ETFDetailV4 fcode={decoded} />

  // Batch 1 — core ETF data (6 connections concurrent)
  const [etf, metricHistory, stateHistory, holdings, leaderHoldings, deepdive] = await Promise.all([
    getETFByTicker(decoded),
    getETFMetricHistory(decoded, 365),
    getETFStateHistory(decoded, 365),
    getETFHoldings(decoded, 20),
    getETFLeaderHoldings(decoded).catch(() => []),
    getEtfDeepdive(decoded).catch(() => null),
  ])

  if (!etf) notFound()

  // Batch 2 — independent context fetch (regime)
  const regimeState = await getMarketRegime().catch(() => null)

  const hasV6 = deepdive != null
  const latest = metricHistory.length > 0 ? metricHistory[metricHistory.length - 1] : null

  // TE in bps from deepdive te_60d (Atlas convention: stored as fraction; multiply by 10000)
  // If te_60d > 1, it's already in bps; else multiply by 10000.
  const teBps = deepdive?.te_60d != null
    ? (deepdive.te_60d > 1 ? deepdive.te_60d : deepdive.te_60d * 10000)
    : null

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ────────────── Breadcrumb ────────────── */}
      <div className="px-6 pt-4 pb-1 text-[12px] text-ink-tertiary font-sans">
        <a href="/etfs" className="text-accent hover:underline">Atlas › ETFs</a>
        {' › '}{decoded}
      </div>

      {/* ────────────── 1. Verdict / Hero strip ────────────── */}
      {hasV6 ? (
        <section className="px-6 py-4 border-b border-paper-rule">
          <EtfHeroStrip deepdive={deepdive} />
        </section>
      ) : (
        <section className="px-6 py-5 border-b border-paper-rule bg-paper">
          <div className="flex items-baseline gap-3 mb-2">
            <span className="font-mono text-[28px] font-semibold text-ink leading-none">{etf.ticker}</span>
            <span className="font-sans text-base text-ink-3">{etf.etf_name}</span>
            {etf.fund_house && (
              <span className="inline-block border border-paper-rule rounded-[2px] px-2 py-0.5 font-mono text-[10px] text-ink-4 tracking-wide">
                {etf.fund_house}
              </span>
            )}
          </div>
          <p className="font-sans text-[12px] text-ink-3">
            v6 deepdive data unavailable for {decoded} — showing legacy view.
          </p>
        </section>
      )}

      {/* ────────────── 2. Gates + Returns ────────────── */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4 px-6 py-4 border-b border-paper-rule bg-paper-deep">
        <ETFGatesPanel
          adv20dInr={deepdive?.adv_20d_inr ?? null}
          trackingErrorBps={teBps}
          etfCategory={deepdive?.etf_category ?? null}
          premiumBps={deepdive?.premium_bps ?? null}
          compositeScore={deepdive?.composite_score ?? null}
          sectorState={null}
          regimeState={regimeState}
        />
        <ETFReturnsTable latest={latest} />
      </section>

      {/* ────────────── 3. Sparklines: ETF vs linked index 12M ────────────── */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-4 px-6 py-4 border-b border-paper-rule bg-paper-deep">
        <div className="border border-paper-rule rounded p-4 bg-paper">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-1">
            {decoded} · 12-Month Sparkline
          </p>
          <TVMiniOverview symbol={decoded} exchange="NSE" dateRange="12M" />
        </div>
        <div className="border border-paper-rule rounded p-4 bg-paper">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-1">
            Nifty 50 · 12-Month Sparkline
          </p>
          <TVMiniOverview symbol="NIFTY" exchange="NSE" dateRange="12M" />
        </div>
      </section>

      {/* ────────────── 4. Price chart (Atlas multidim, 180D) ────────────── */}
      {hasV6 && deepdive.price_180d && deepdive.price_180d.length > 0 && (
        <section className="px-6 py-6 border-b border-paper-rule">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">
            Price · multidim view — 180D OHLCV + 20D MA + volume
          </p>
          <div className="border border-paper-rule rounded p-4 bg-paper">
            <PriceMultidim180d ticker={decoded} priceData={deepdive.price_180d} />
          </div>
        </section>
      )}

      {/* ────────────── 5. NAV-fair-value + Tracking Error ────────────── */}
      {hasV6 && (
        <section className="px-6 py-6 border-b border-paper-rule">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">
            ETF-specific Checks — NAV-fair-value + Tracking Quality
          </p>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <NavVsMarketPrice ticker={decoded} premiumBps={deepdive.premium_bps} />
            <TrackingError12m ticker={decoded} te60d={deepdive.te_60d} category={deepdive.etf_category} />
          </div>
        </section>
      )}

      {/* ────────────── 6. ETF Signal Trajectory Grid ────────────── */}
      <ETFSparklineTrajectoryGrid metricHistory={metricHistory} />

      {/* ────────────── 7. TradingView composite technical analysis ────────────── */}
      <section className="px-6 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">
          TradingView Composite Technical Analysis — multi-timeframe consensus
        </p>
        <div className="border border-paper-rule rounded overflow-hidden bg-paper">
          <TVTechnicalAnalysis symbol={decoded} interval="1D" />
        </div>
      </section>

      {/* ────────────── 8. Peer matrix (within category) ────────────── */}
      {hasV6 && deepdive.peer_set && (
        <section className="px-6 py-6 border-b border-paper-rule">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">
            Peer Matrix — same category, ranked by composite score
          </p>
          <PeerSetTable ticker={decoded} peers={deepdive.peer_set} category={deepdive.etf_category} />
        </section>
      )}

      {/* ────────────── 9. Holdings + Leader-owned holdings ────────────── */}
      {leaderHoldings.length > 0 && (
        <section className="px-6 py-6 border-b border-paper-rule">
          <LeaderHoldingsPanel holdings={leaderHoldings} />
        </section>
      )}

      {/* ────────────── 10. Latest news ────────────── */}
      <section className="px-6 py-6 border-b border-paper-rule">
        <p className="font-mono text-[10px] uppercase tracking-wider text-ink-3 mb-3">
          Latest News — auto-updated from TradingView
        </p>
        <div className="border border-paper-rule rounded overflow-hidden bg-paper">
          <TVNews symbol={decoded} />
        </div>
      </section>

      {/* ────────────── 11. Supporting Detail drawers ────────────── */}
      <section className="px-6 py-6 border-b border-paper-rule space-y-4">
        <h2 className="font-mono text-[10px] uppercase tracking-wider text-ink-3">Supporting Detail</h2>

        <details className="font-sans text-[12px] text-ink-3 border border-paper-rule rounded p-3 bg-paper">
          <summary className="cursor-pointer text-accent font-medium select-none">
            Show fund profile (about, sponsor, AMC)
          </summary>
          <div className="pt-3">
            <TVCompanyProfile symbol={decoded} />
          </div>
        </details>

        <details className="font-sans text-[12px] text-ink-3 border border-paper-rule rounded p-3 bg-paper">
          <summary className="cursor-pointer text-accent font-medium select-none">
            Show legacy deep-dive tabs (history, holdings table, intelligence)
          </summary>
          <div className="pt-3">
            <ETFDeepDiveTabs
              etf={etf}
              metricHistory={metricHistory}
              stateHistory={stateHistory}
              holdings={holdings}
              range="1Y"
              initialTab={tab}
            />
          </div>
        </details>
      </section>

      {/* ────────────── 12. Footnote ────────────── */}
      <div className="px-6 pb-12 pt-4 border-t border-paper-rule">
        <p className="font-sans text-[12px] text-ink-tertiary leading-relaxed max-w-[880px]">
          <strong className="text-ink-secondary">Data sources:</strong> Scorecard from atlas_etf_scorecard.
          Price history (180d) from de_etf_ohlcv via mv_etf_deepdive. Peer set: same etf_category, latest snapshot.
          Premium-to-NAV: AMFI iNAV (migration 108). Tracking error: 60d annualised, category-aware threshold.{' '}
          <strong className="text-ink-secondary">Data as of:</strong>{' '}
          {deepdive?.as_of_date ?? 'latest snapshot'}.
        </p>
      </div>
    </div>
  )
}
