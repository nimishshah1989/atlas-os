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
// v6 landing extensions — 12-week journey + today's conviction tabs
import { getRegimeJourney12w, getTopConvictionCalls } from '@/lib/queries/v6/landing'
import { RegimeJourney12w } from '@/components/v6/landing/RegimeJourney12w'
import { TodayConvictionTabs } from '@/components/v6/landing/TodayConvictionTabs'
import { RegimeClassifierInputs } from '@/components/regime/RegimeClassifierInputs'

type SearchParams = Promise<{ range?: string }>

export default async function RegimePage({ searchParams }: { searchParams: SearchParams }) {
  const { range = '1Y' } = await searchParams
  const historyRange = range as TimeRange
  const historyDays = rangeToDays(historyRange)

  const [current, history, journey12w, convictionCalls] = await Promise.all([
    getCurrentRegime(),
    getRegimeHistory(historyDays),
    getRegimeJourney12w(),
    getTopConvictionCalls(),
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
  const { scorecard, worklist, leadingSectorNames } = await getRegimeScorecard(current.pct_above_ema_50)

  const deploymentPct = Math.round(parseFloat(current.deployment_multiplier) * 100)

  // leadingSectorNames = sectors that entered Overweight today (were not Overweight yesterday).
  // Empty list on days with no new entries — verdict renders without the sector clause.
  const leadingSectors: string[] = leadingSectorNames

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ── NEW: Verdict + scorecard + worklist (above existing content) ── */}
      <RegimeVerdict
        regimeState={current.regime_state}
        deploymentPct={deploymentPct}
        leadingSectors={leadingSectors}
      />
      <SignalScorecard data={scorecard} regime={current} />
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

      {/* NEW (2026-05-29 pilot): "How we got here" — 4 LC small-multiples for
          the regime classifier inputs. First production use of
          AtlasLightweightChart. Sits ABOVE the four sections so you can
          A/B them by scrolling: LC pilot at top, Recharts originals below. */}
      <RegimeClassifierInputs
        history={history}
        asOf={current.date instanceof Date ? current.date.toISOString().slice(0, 10) : String(current.date).slice(0, 10)}
      />

      {/* Four category sections — unchanged */}
      <TrendSection current={current} history={history} />
      <BreadthSection current={current} history={history} />
      <MomentumSection current={current} history={history} />
      <ParticipationSection current={current} history={history} />

      {/* ── NEW: 12-week regime journey (Page 01 mockup section) ── */}
      <RegimeJourney12w cells={journey12w} />

      {/* ── NEW: Today's conviction — 3-tab panel ── */}
      <TodayConvictionTabs data={convictionCalls} />
    </div>
  )
}
