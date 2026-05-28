// allow-large: Page 07 ETF list — multi-section composition (AMC tiles + NAV scatter + story cards + table). Cleanup tracked post-presentation.
export const dynamic = 'force-dynamic'

import { getAllETFs } from '@/lib/queries/etfs'
import { getCurrentRegime } from '@/lib/queries/regime'
import { getComponentValidations } from '@/lib/queries/component_validation'
import { getEtfsList, getAmcAggregates } from '@/lib/queries/v6/etfs'
import { ETFScreener } from '@/components/etfs/ETFScreener'
import { ETFMetricTiles } from '@/components/etfs/ETFMetricTiles'
import { ETFIntelligencePanel } from '@/components/etfs/ETFIntelligencePanel'
import { ETFBubbleChart } from '@/components/etfs/ETFBubbleChart'
import { HeroStories } from '@/components/v6/etfs/HeroStories'
import { AmcTileRow } from '@/components/v6/etfs/AmcTileRow'
import { PremiumDiscountScatter } from '@/components/v6/etfs/PremiumDiscountScatter'
import { CategoryBands } from '@/components/v6/etfs/CategoryBands'

export default async function ETFsPage() {
  const [etfs, regime, validations, etfListV6] = await Promise.all([
    getAllETFs(),
    getCurrentRegime(),
    getComponentValidations(),
    getEtfsList().catch(() => []),
  ])

  if (etfs.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No ETF data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const investableCount = etfs.filter(e => e.is_investable).length
  const leaderCount     = etfs.filter(e => e.rs_state === 'Leader' || e.rs_state === 'Strong').length

  // v6 MV aggregates (derived from 34-row set — pure JS, no extra DB call)
  const amcAggregates = getAmcAggregates(etfListV6)
  const buyCount = etfListV6.filter(e => e.action === 'BUY').length
  const premiumOutlierCount = etfListV6.filter(
    e => e.premium_bps != null && Math.abs(e.premium_bps) > 25,
  ).length
  const hasV6Data = etfListV6.length > 0

  // Hero stats derived values
  const totalAdvCr = etfListV6.reduce((s, e) => s + (e.adv_20d_inr ?? 0) / 1e7, 0)
  const teValues = etfListV6.map(e => e.te_60d).filter((v): v is number => v != null)
  const teMedian = teValues.length > 0
    ? [...teValues].sort((a, b) => a - b)[Math.floor(teValues.length / 2)] ?? null
    : null
  const toBps = (v: number | null) => v != null ? (v < 1 ? v * 10000 : v) : null

  return (
    <div className="max-w-[1400px] mx-auto">

      {/* ── Page header ──────────────────────────────────────────────────────── */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <div className="text-[12px] text-ink-tertiary mb-2 font-sans">
          Atlas › ETFs
        </div>
        <div className="flex items-baseline gap-4 flex-wrap mb-2">
          <h1 className="font-serif text-[44px] font-normal tracking-tight text-ink-primary leading-tight">
            ETFs
          </h1>
          {hasV6Data && (
            <span className="font-mono text-[12px] text-ink-tertiary">
              {etfListV6.length} ETFs · {amcAggregates.length} AMCs
            </span>
          )}
        </div>
        <p className="font-sans text-[15px] text-ink-secondary max-w-[880px]">
          Exchange-traded funds scored on the same cell methodology as the stock universe — but with the ETF-specific
          lens added:{' '}
          <strong className="font-semibold text-ink-primary">tracking error</strong>,{' '}
          <strong className="font-semibold text-ink-primary">NAV-vs-market-price premium/discount</strong>, and{' '}
          <strong className="font-semibold text-ink-primary">average daily volume</strong>.
          Categorised into four canonical bands so passive selection has the same depth as active.
        </p>
      </div>

      {/* ── Hero stats strip (v6 data) ────────────────────────────────────────── */}
      {hasV6Data && (
        <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 bg-paper-soft border-b border-paper-rule divide-x divide-paper-rule">
          <div className="px-4 py-3">
            <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1">
              Universe
            </div>
            <div className="font-mono text-xl font-medium text-ink-primary">{etfListV6.length}</div>
            <div className="font-sans text-[11px] text-ink-tertiary mt-1">
              {amcAggregates.length} AMCs · 4 category bands
            </div>
          </div>
          <div className="px-4 py-3">
            <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1">
              BUY firing
            </div>
            <div className="font-mono text-xl font-medium text-signal-pos">{buyCount}</div>
            <div className="font-sans text-[11px] text-ink-tertiary mt-1">
              Cell-confirmed · {etfListV6.length > 0 ? Math.round((buyCount / etfListV6.length) * 100) : 0}%
            </div>
          </div>
          <div className="px-4 py-3">
            <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1">
              Premium-to-NAV outliers
            </div>
            <div className={`font-mono text-xl font-medium ${premiumOutlierCount > 0 ? 'text-signal-warn' : 'text-signal-pos'}`}>
              {premiumOutlierCount}
            </div>
            <div className="font-sans text-[11px] text-ink-tertiary mt-1">
              &gt; ±25 bps from NAV · liquidity attention
            </div>
          </div>
          <div className="px-4 py-3">
            <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1">
              Tracking error · median
            </div>
            <div className="font-mono text-xl font-medium text-ink-primary">
              {teMedian != null ? `${toBps(teMedian)?.toFixed(0)} bps` : '—'}
            </div>
            <div className="font-sans text-[11px] text-ink-tertiary mt-1">
              60-day annualised
            </div>
          </div>
          <div className="px-4 py-3">
            <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1">
              ADV · total
            </div>
            <div className="font-mono text-xl font-medium text-ink-primary">
              ₹{totalAdvCr.toFixed(0)} cr
            </div>
            <div className="font-sans text-[11px] text-ink-tertiary mt-1">
              Universe combined 20D avg ADV
            </div>
          </div>
          <div className="px-4 py-3">
            <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1">
              Investable (legacy)
            </div>
            <div className="font-mono text-xl font-medium text-ink-primary">{investableCount}</div>
            <div className="font-sans text-[11px] text-ink-tertiary mt-1">
              {leaderCount} Leader/Strong RS
            </div>
          </div>
        </div>
      )}

      {/* ── Today's story — 4 narrative blocks ───────────────────────────────── */}
      {hasV6Data && (
        <div className="px-6 py-8 border-b border-paper-rule">
          <div className="mb-4">
            <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary mb-1">
              Today&apos;s story
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px]">
              Four narrative blocks across the ETF-specific decision dimensions — cell-confirmed BUYs,
              tracking quality, liquidity risk, and pricing anomalies.
            </p>
          </div>
          <HeroStories etfs={etfListV6} />
        </div>
      )}

      {/* ── Category bands ────────────────────────────────────────────────────── */}
      {hasV6Data && (
        <div className="px-6 py-8 border-b border-paper-rule">
          <div className="mb-4">
            <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary mb-1">
              Category bands · the 4 ways ETFs come
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px]">
              The four canonical ETF categories with per-band ETF count, AUM proxy, Atlas verdict mix, and
              representative names. Selection criteria differ per band.
            </p>
          </div>
          <CategoryBands etfs={etfListV6} />
        </div>
      )}

      {/* ── AMC tile row ─────────────────────────────────────────────────────── */}
      {hasV6Data && amcAggregates.length > 0 && (
        <div className="px-6 py-8 border-b border-paper-rule">
          <div className="mb-4">
            <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary mb-1">
              AMC tile row · {amcAggregates.length} AMCs sized by ADV
            </h2>
            <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px]">
              Where each AMC sits in the ETF market. First-mover effect and ADV moat are structural —
              liquidity is winner-take-all.
            </p>
          </div>
          <AmcTileRow amcs={amcAggregates} />
        </div>
      )}

      {/* ── NAV vs market price scatter ─────────────────────────────────────── */}
      {hasV6Data && (
        <div className="px-6 py-8 border-b border-paper-rule">
          <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
            <div>
              <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary mb-1">
                NAV vs market price · premium/discount scatter
              </h2>
              <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px]">
                Every ETF plotted by <strong className="text-ink-secondary">premium to NAV</strong> (x, in bps) against{' '}
                <strong className="text-ink-secondary">30-day average ADV</strong> (y, log). The green zone at
                ±25 bps and high ADV is the clean-entry region. Outliers = liquidity-stress or AP-friction.
              </p>
            </div>
          </div>
          <div className="border border-paper-rule rounded-sm p-4 bg-paper">
            <PremiumDiscountScatter etfs={etfListV6} />
          </div>
        </div>
      )}

      {/* ── Legacy metric tiles strip ─────────────────────────────────────────── */}
      <div className="px-6 pt-6 border-b border-paper-rule pb-2">
        <h2 className="font-serif text-[22px] font-normal text-ink-primary mb-3">
          Full screener
        </h2>
        <ETFMetricTiles etfs={etfs} />
      </div>

      {/* Bubble chart: trend strength vs within-state rank */}
      <div className="px-6 pt-4">
        <div className="border border-paper-rule rounded-sm p-4">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
            ETF Trend Map — Holding Trend Strength vs Within-State Rank
          </div>
          <p className="font-sans text-[11px] text-ink-tertiary mb-3">
            X = holdings trend strength (stage&nbsp;2 − stage&nbsp;4 breadth). Y = mean within-state rank of holdings. Color = RS state. Bubble size = RS rank 12M. Strong-trend + high-rank (top-right) is the leadership zone.
          </p>
          <ETFBubbleChart etfs={etfs} />
        </div>
      </div>

      {/* Main content: screener + intelligence panel */}
      <div className="px-6 py-4 grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6 items-start">
        <ETFScreener etfs={etfs} validations={validations} />

        <div className="border border-paper-rule rounded-sm p-4 bg-paper sticky top-4">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
            ETF Intelligence
          </div>
          <ETFIntelligencePanel
            etfs={etfs}
            regimeState={regime?.regime_state ?? 'Unknown'}
            deploymentMultiplier={Number(regime?.deployment_multiplier ?? '0')}
          />
        </div>
      </div>

      {/* Footnote */}
      <div className="px-6 pb-12 pt-4 border-t border-paper-rule">
        <p className="font-sans text-[12px] text-ink-tertiary leading-relaxed max-w-[880px]">
          <strong className="text-ink-secondary">Data sources:</strong> ETF scorecard from atlas_etf_scorecard (nightly). Returns from atlas_etf_metrics_daily.
          Premium-to-NAV from AMFI iNAV (migration 108 — pending backfill). Tracking error: 60-day annualised window.
          ADV proxy = 20-day average daily value traded.{' '}
          <strong className="text-ink-secondary">Data as of:</strong>{' '}
          {etfListV6[0]?.as_of_date ?? 'latest snapshot'}.
        </p>
      </div>
    </div>
  )
}
