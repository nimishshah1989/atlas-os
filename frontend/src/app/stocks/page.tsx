// allow-large: Page 05 stocks landscape — stories + bubble + 24-cell matrix + trajectories + cards + table. Cleanup tracked post-presentation.
export const dynamic = 'force-dynamic'

import { getAllStocks } from '@/lib/queries/stocks'
import { getCurrentRegime } from '@/lib/queries/regime'
import { getComponentValidations } from '@/lib/queries/component_validation'
import { getRSLeaders, getBreakoutCandidates, getDeteriorationWatch } from '@/lib/queries/leaders'
import { getEffectivePolicy } from '@/lib/queries/policy'
import { getStocksLandscape, getMatrixCells, getHeroStories } from '@/lib/queries/v6/stocks-landscape'
import { StocksClientShell } from '@/components/stocks/StocksClientShell'
import { HeroStories } from '@/components/v6/stocks/HeroStories'
import { ConvictionLandscapeSection } from '@/components/v6/stocks/ConvictionLandscapeSection'
import { CompositeTrajectoriesGrid } from '@/components/v6/stocks/CompositeTrajectoriesGrid'
import { SixPicksWorthClick } from '@/components/v6/stocks/SixPicksWorthClick'
import type { PolicyEntryParams } from '@/lib/policy-entry-filter'

export default async function StocksPage({
  searchParams,
}: {
  searchParams: Promise<{ sector?: string; index?: string; portfolio?: string }>
}) {
  const params = await searchParams
  const sectorFilter  = params.sector?.trim() || undefined
  const indexFilter   = params.index?.trim() || undefined
  const portfolioId   = params.portfolio?.trim() || undefined

  // Flow mode: active portfolio + sector filter → load effective policy for entry-rule filter.
  // If no portfolio param, policy stays undefined (engine view — no constraints applied).
  let policyEntryParams: PolicyEntryParams | undefined

  if (portfolioId && sectorFilter) {
    try {
      const policy = await getEffectivePolicy(portfolioId)
      if (policy !== null) {
        const buyStates = policy.buy_states.value as string[] | null
        policyEntryParams = {
          buy_states: buyStates ?? [],
          min_within_state_rank: parseFloat(
            (policy.min_within_state_rank.value as string | null) ?? '0'
          ),
          min_rs_rank: parseFloat(
            (policy.min_rs_rank.value as string | null) ?? '0'
          ),
        }
      }
    } catch {
      // Non-fatal: policy load failure degrades to unfiltered engine view.
    }
  }

  // Load all data in parallel — landscape queries are independent of screener queries.
  const [
    stocks, regime, validations, leaders, breakouts, deterioration,
    landscapeData, matrixCells, heroStories,
  ] = await Promise.all([
    getAllStocks({ sectorFilter, indexFilter }),
    getCurrentRegime(),
    getComponentValidations(),
    getRSLeaders(null, 50),
    getBreakoutCandidates(),
    getDeteriorationWatch(),
    // v6 landscape extension — non-fatal: catch individually to avoid blocking screener
    getStocksLandscape().catch(() => []),
    getMatrixCells().catch(() => []),
    getHeroStories().catch(() => ({
      freshBuys: [], freshAvoids: [], highConfBuys: [], exitCandidates: [],
      stats: { totalUniverse: 0, buyCount: 0, watchCount: 0, avoidCount: 0, highConfBuyCount: 0 },
    })),
  ])

  // Hero stats derived from landscape data (preferred) or screener data (fallback)
  const universeCount = landscapeData.length > 0 ? landscapeData.length : stocks.length
  const buyCount = heroStories.stats.buyCount
  const watchCount = heroStories.stats.watchCount
  const avoidCount = heroStories.stats.avoidCount
  const highConfBuyCount = heroStories.stats.highConfBuyCount
  // "Data as of" = the market-data date (as_of_date), not refreshed_at (the
  // wall-clock instant the nightly MV cron ran — which is the next calendar day
  // after a post-midnight refresh, e.g. Sat 30 May for Fri 29 May data).
  const asOfDate = landscapeData[0]?.as_of_date ?? null

  // Screener fallback for empty stocks
  if (stocks.length === 0 && landscapeData.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No stock data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const investableCount = stocks.filter(s => s.is_investable).length
  const leaderCount     = stocks.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length
  const improvingCount  = stocks.filter(s => s.momentum_state === 'Improving' || s.momentum_state === 'Accelerating').length

  return (
    <div>
      {/* ── Page header ────────────────────────────────────────────────────── */}
      <section className="py-8 pb-6 border-b border-paper-rule">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="font-sans text-[12px] text-ink-tertiary mb-3">
            <span className="text-accent">Atlas</span> › Stocks
          </div>
          <div className="flex items-baseline gap-4 flex-wrap mb-2">
            <h1 className="font-serif text-[44px] font-normal tracking-tight text-ink-primary leading-none">
              Stocks
            </h1>
            <span className="font-mono text-[12px] text-ink-tertiary">
              {universeCount} instruments · M1 universe
            </span>
          </div>
          <p className="font-sans text-[15px] text-ink-secondary max-w-[880px]">
            Every instrument in the v6 universe, scored nightly against the 24-cell methodology matrix.
            This page tells the <strong>story</strong> first — what fired today, what carries highest conviction,
            what&apos;s transitioning — then shows the landscape (bubble chart + cell-firing matrix), the
            trajectories, the six picks worth a click, and finally the full table.
          </p>

          {/* Hero stats strip */}
          <div
            className="mt-6 bg-paper-soft border border-paper-rule rounded-sm overflow-hidden grid"
            style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}
          >
            {[
              {
                label: 'Universe',
                value: String(universeCount),
                cls: 'text-ink-primary',
                foot: `M1 locked · Large · Mid · Small`,
              },
              {
                label: 'BUY firing',
                value: String(buyCount),
                cls: 'text-signal-pos',
                foot: `${universeCount > 0 ? ((buyCount / universeCount) * 100).toFixed(1) : '0'}% of universe`,
              },
              {
                label: 'WATCH',
                value: String(watchCount),
                cls: 'text-signal-warn',
                foot: 'Near-threshold names — trending neutral',
              },
              {
                label: 'AVOID firing',
                value: String(avoidCount),
                cls: 'text-signal-neg',
                foot: `${universeCount > 0 ? ((avoidCount / universeCount) * 100).toFixed(1) : '0'}% of universe`,
              },
              {
                label: 'HIGH-conf BUYs',
                value: String(highConfBuyCount),
                cls: 'text-signal-pos',
                foot: `${buyCount > 0 ? ((highConfBuyCount / buyCount) * 100).toFixed(0) : '0'}% of BUYs in HIGH-conf band`,
              },
              {
                label: 'Data as of',
                value: asOfDate
                  ? new Date(asOfDate + 'T12:00:00Z').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
                  : '—',
                cls: 'text-ink-primary font-mono text-[14px]',
                foot: 'Last trading session · refreshed nightly 20:00 IST',
              },
            ].map((tile, i) => (
              <div
                key={tile.label}
                className={`px-[18px] py-[14px] ${i < 5 ? 'border-r border-paper-rule' : ''}`}
              >
                <div className="font-sans text-[9px] tracking-[0.18em] uppercase text-ink-tertiary font-semibold mb-1">
                  {tile.label}
                </div>
                <div className={`font-mono text-[22px] font-medium leading-none ${tile.cls}`}>
                  {tile.value}
                </div>
                <div className="font-sans text-[11px] text-ink-tertiary mt-1 leading-snug">
                  {tile.foot}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Hero stories (4 columns) ──────────────────────────────────────── */}
      {heroStories.freshBuys.length > 0 || heroStories.freshAvoids.length > 0 ? (
        <HeroStories data={heroStories} />
      ) : null}

      {/* ── Conviction landscape (bubble + 24-cell matrix) ───────────────── */}
      {landscapeData.length > 0 ? (
        <ConvictionLandscapeSection
          landscapeData={landscapeData}
          matrixCells={matrixCells}
        />
      ) : null}

      {/* ── Composite trajectories (30-day sparklines) ───────────────────── */}
      {landscapeData.length > 0 ? (
        <CompositeTrajectoriesGrid data={landscapeData} />
      ) : null}

      {/* ── Six picks worth a click ───────────────────────────────────────── */}
      {landscapeData.length > 0 ? (
        <SixPicksWorthClick data={landscapeData} />
      ) : null}

      {/* ── Existing screener (preserved) ────────────────────────────────── */}
      <section className="py-9">
        <div className="max-w-[1400px] mx-auto px-8">
          <div className="flex items-baseline justify-between mb-4 flex-wrap gap-3">
            <div>
              <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary leading-none">
                Full universe table
              </h2>
              <p className="font-sans text-[13px] text-ink-tertiary mt-1">
                All {stocks.length} instruments. Sortable, filterable, with column chooser.
              </p>
            </div>
            <div className="flex items-center gap-4 flex-wrap">
              <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
                <span className="inline-block w-2 h-2 rounded-full bg-teal" />
                {investableCount} Investable
                <span className="text-ink-tertiary">(of {stocks.length})</span>
              </span>
              <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
                <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
                {leaderCount} Leader/Strong
              </span>
              <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
                <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
                {improvingCount} Accel/Improving
              </span>
              {portfolioId && sectorFilter && policyEntryParams && (
                <span className="flex items-center gap-1.5 font-sans text-xs text-teal">
                  <span className="inline-block w-2 h-2 rounded-full bg-teal" />
                  Policy active
                </span>
              )}
            </div>
          </div>

          <StocksClientShell
            stocks={stocks}
            regimeState={regime?.regime_state ?? 'Unknown'}
            deploymentMultiplier={Number(regime?.deployment_multiplier ?? '0')}
            validations={validations}
            leaders={leaders}
            breakouts={breakouts}
            deterioration={deterioration}
            initialSectorFilter={sectorFilter}
            initialIndexFilter={indexFilter}
            policyEntryParams={policyEntryParams}
          />
        </div>
      </section>
    </div>
  )
}
