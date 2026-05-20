// frontend/src/app/page.tsx
import { Suspense } from 'react'
import { getCurrentRegime, getRegimeHistory } from '@/lib/queries/regime'
import { getRegimeScorecard } from '@/lib/queries/regime-scorecard'
import { RegimeVerdict } from '@/components/regime/RegimeVerdict'
import { SignalScorecard } from '@/components/regime/SignalScorecard'
import { TodayWorklist } from '@/components/regime/TodayWorklist'
import { RegimeHeadline } from '@/components/regime/RegimeHeadline'
import { IntradayNiftyStrip } from '@/components/regime/IntradayNiftyStrip'
import { RegimeOverlayChart } from '@/components/regime/RegimeOverlayChart'
import { TrendSection } from '@/components/regime/TrendSection'
import { BreadthSection } from '@/components/regime/BreadthSection'
import { MomentumSection } from '@/components/regime/MomentumSection'
import { ParticipationSection } from '@/components/regime/ParticipationSection'
import { TimeRangeToggle } from '@/components/ui/TimeRangeToggle'
import { rangeToDays, type TimeRange } from '@/lib/time-range'

type SearchParams = Promise<{ range?: string }>

export default async function RegimePage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '6M' } = await searchParams
  const historyRange = range as TimeRange
  const historyDays = rangeToDays(historyRange)

  const [current, history] = await Promise.all([
    getCurrentRegime(),
    getRegimeHistory(historyDays),
  ])

  if (!current) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No regime data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  // Fetch scorecard signals. Breadth is passed in from the regime row to avoid
  // a duplicate DB round-trip (pct_above_ema_50 already fetched above).
  const { scorecard, worklist } = await getRegimeScorecard(current.pct_above_ema_50)

  const deploymentPct = Math.round(parseFloat(current.deployment_multiplier) * 100)

  // Derive leading sectors from the worklist for the verdict sentence.
  // "Leading sectors" here means sectors that recently entered Overweight
  // (worklist.sectorsEnteredFavour > 0 indicates transitions happened today,
  //  but we don't yet have the sector names from this query path — render
  //  without sector names when none entered today).
  const leadingSectors: string[] = []

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ── NEW: Verdict + scorecard + worklist (above existing content) ── */}
      <RegimeVerdict
        regimeState={current.regime_state}
        deploymentPct={deploymentPct}
        leadingSectors={leadingSectors}
      />
      <SignalScorecard data={scorecard} />
      <TodayWorklist data={worklist} />

      {/* Compact regime headline — unchanged */}
      <RegimeHeadline regime={current} />

      {/* SP10: Intraday Nifty strip */}
      <div className="px-6 py-3 border-b border-paper-rule">
        <IntradayNiftyStrip />
      </div>

      {/* Nifty 500 with regime background shading + master time range toggle */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
            Nifty 500 — Regime History
          </h2>
          <Suspense>
            <TimeRangeToggle value={historyRange} options={['1M', '3M', '6M', '1Y']} />
          </Suspense>
        </div>
        <RegimeOverlayChart history={history} />
      </div>

      {/* Four category sections — unchanged */}
      <TrendSection current={current} history={history} />
      <BreadthSection current={current} history={history} />
      <MomentumSection current={current} history={history} />
      <ParticipationSection current={current} history={history} />
    </div>
  )
}
