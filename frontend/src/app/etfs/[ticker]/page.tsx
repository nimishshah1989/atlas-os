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
import { rangeToDays, type TimeRange } from '@/lib/time-range'
import { ETFDeepDiveHeader } from '@/components/etfs/ETFDeepDiveHeader'
import { ETFSnapshotTiles } from '@/components/etfs/ETFSnapshotTiles'
import { ETFDeepDiveTabs } from '@/components/etfs/ETFDeepDiveTabs'
import { LeaderHoldingsPanel } from '@/components/ui/LeaderHoldingsPanel'
import { EtfHeroStrip } from '@/components/v6/etfs/EtfHeroStrip'
import { PriceMultidim180d } from '@/components/v6/etfs/PriceMultidim180d'
import { NavVsMarketPrice } from '@/components/v6/etfs/NavVsMarketPrice'
import { TrackingError12m } from '@/components/v6/etfs/TrackingError12m'
import { PeerSetTable } from '@/components/v6/etfs/PeerSetTable'

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
  const { tab = 'overview', range = '6M' } = await searchParams
  const decoded = decodeURIComponent(ticker)

  const VALID_RANGES: TimeRange[] = ['1M', '3M', '6M', '1Y']
  const historyRange: TimeRange = VALID_RANGES.includes(range as TimeRange)
    ? (range as TimeRange)
    : '6M'
  const days = rangeToDays(historyRange)

  const [etf, metricHistory, stateHistory, holdings, leaderHoldings, deepdive] =
    await Promise.all([
      getETFByTicker(decoded),
      getETFMetricHistory(decoded, days),
      getETFStateHistory(decoded, days),
      getETFHoldings(decoded, 20),
      getETFLeaderHoldings(decoded).catch(() => []),
      getEtfDeepdive(decoded).catch(() => null),
    ])

  if (!etf) notFound()

  const hasV6Deep = deepdive != null

  return (
    <div className="max-w-[1400px] mx-auto">

      {/* ── Breadcrumb ──────────────────────────────────────────────────────── */}
      <div className="px-6 pt-4 pb-1 text-[12px] text-ink-tertiary font-sans">
        <a href="/etfs" className="text-accent hover:underline">Atlas › ETFs</a>
        {' › '}{decoded}
      </div>

      {/* ── v6 Hero strip (from mv_etf_deepdive) ────────────────────────────── */}
      {hasV6Deep && (
        <div className="px-6 py-4 border-b border-paper-rule">
          <EtfHeroStrip deepdive={deepdive} />
        </div>
      )}

      {/* ── Legacy deep-dive header + snapshot tiles ───────────────────────────
         Suppressed when v6 hero is present to avoid two competing top-of-page
         headers (per design review 2026-05-28 — "Visible duplication" finding). */}
      {!hasV6Deep && (
        <>
          <ETFDeepDiveHeader etf={etf} />
          <ETFSnapshotTiles etf={etf} />
        </>
      )}

      {/* ── v6 Price multidim chart ────────────────────────────────────────── */}
      {hasV6Deep && (
        <div className="px-6 py-6 border-b border-paper-rule">
          <div className="mb-3">
            <h2 className="font-serif text-[26px] font-normal tracking-tight text-ink-primary mb-1">
              Price · multidim view
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px]">
              180-day daily OHLCV — price line + 20D moving average + volume bars.
              Same 4-lane structure as Markets RS · Sectors deep-dive · Stocks deep-dive.
            </p>
          </div>
          <div className="border border-paper-rule rounded-sm p-4 bg-paper">
            <PriceMultidim180d
              ticker={decoded}
              priceData={deepdive.price_180d}
            />
          </div>
        </div>
      )}

      {/* ── Legacy deep-dive tabs ────────────────────────────────────────────── */}
      <ETFDeepDiveTabs
        etf={etf}
        metricHistory={metricHistory}
        stateHistory={stateHistory}
        holdings={holdings}
        range={historyRange}
        initialTab={tab}
      />

      {/* ── v6 NAV vs market price + TE + peers (2-col layout) ──────────────── */}
      {hasV6Deep && (
        <div className="px-6 py-6 border-t border-paper-rule">
          <div className="mb-4">
            <h2 className="font-serif text-[26px] font-normal tracking-tight text-ink-primary mb-1">
              ETF-specific checks
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px]">
              The three checks that matter most for ETF selection beyond the cell score: NAV-fair-value,
              tracking quality, and peer comparison within category.
            </p>
          </div>

          {/* 2-up: NAV + TE */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-4">
            <NavVsMarketPrice
              ticker={decoded}
              premiumBps={deepdive.premium_bps}
            />
            <TrackingError12m
              ticker={decoded}
              te60d={deepdive.te_60d}
              category={deepdive.etf_category}
            />
          </div>

          {/* Peer set table */}
          <PeerSetTable
            ticker={decoded}
            peers={deepdive.peer_set}
            category={deepdive.etf_category}
          />
        </div>
      )}

      {/* ── Leader holdings ──────────────────────────────────────────────────── */}
      {leaderHoldings.length > 0 && (
        <div className="px-6 py-6 border-t border-paper-rule">
          <LeaderHoldingsPanel holdings={leaderHoldings} />
        </div>
      )}

      {/* ── Footnote ─────────────────────────────────────────────────────────── */}
      <div className="px-6 pb-12 pt-4 border-t border-paper-rule">
        <p className="font-sans text-[12px] text-ink-tertiary leading-relaxed max-w-[880px]">
          <strong className="text-ink-secondary">Data sources:</strong> Scorecard from atlas_etf_scorecard.
          Price history (180d) from de_etf_ohlcv via mv_etf_deepdive. Peer set: same etf_category, latest snapshot.
          Premium-to-NAV: AMFI iNAV (migration 108). Tracking error: 60d annualised.{' '}
          <strong className="text-ink-secondary">Data as of:</strong>{' '}
          {deepdive?.as_of_date ?? 'latest snapshot'}.
        </p>
      </div>
    </div>
  )
}
