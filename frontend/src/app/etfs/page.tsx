export const dynamic = 'force-dynamic'

import { getAllETFs } from '@/lib/queries/etfs'
import { getCurrentRegime } from '@/lib/queries/regime'
import { getComponentValidations } from '@/lib/queries/component_validation'
import { ETFScreener } from '@/components/etfs/ETFScreener'
import { ETFMetricTiles } from '@/components/etfs/ETFMetricTiles'
import { ETFIntelligencePanel } from '@/components/etfs/ETFIntelligencePanel'
import { ETFBubbleChart } from '@/components/etfs/ETFBubbleChart'

export default async function ETFsPage() {
  const [etfs, regime, validations] = await Promise.all([getAllETFs(), getCurrentRegime(), getComponentValidations()])

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

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header band */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            ETF Universe
          </h1>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-teal" />
              {investableCount} Investable
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {leaderCount} Leader/Strong
            </span>
          </div>
        </div>
      </div>

      {/* Metric tiles strip */}
      <div className="px-6 pt-4">
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
    </div>
  )
}
