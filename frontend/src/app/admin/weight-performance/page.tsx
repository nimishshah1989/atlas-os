// SP04 Stage 4c — admin page showing realized IC of every active weight
// set + recent reverts.
export const dynamic = 'force-dynamic'

import {
  getActiveWeightSetsWithTrail,
  getRecentReverts,
} from '@/lib/queries/weight_performance'
import { RealizedICSparkline } from '@/components/admin/RealizedICSparkline'
import { RevertBanner } from '@/components/admin/RevertBanner'

const TIER_LABEL: Record<string, string> = {
  tier_1_megacap: 'Tier 1 (mega-cap)',
  tier_2_largecap: 'Tier 2 (large-cap)',
  tier_3_uppermid: 'Tier 3 (upper mid-cap)',
  tier_4_lowermid: 'Tier 4 (lower mid-cap)',
  tier_5_smallcap: 'Tier 5 (small-cap)',
}

function statusPill(daysBelow: number, nTrail: number) {
  if (nTrail < 60) {
    return { label: 'Bootstrap', cls: 'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30' }
  }
  if (daysBelow === nTrail) {
    return { label: 'Revert imminent', cls: 'bg-signal-neg/10 text-signal-neg border-signal-neg/30' }
  }
  if (daysBelow >= 15) {
    return { label: 'Watch', cls: 'bg-signal-warn/10 text-signal-warn border-signal-warn/30' }
  }
  return { label: 'OK', cls: 'bg-teal/10 text-teal border-teal/30' }
}

export default async function WeightPerformancePage() {
  const [activeSets, reverts] = await Promise.all([
    getActiveWeightSetsWithTrail(),
    getRecentReverts(),
  ])

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          Atlas · Admin · Stage 4c
        </div>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">
          Weight-Set Live Performance
        </h1>
        <p className="font-sans text-xs text-ink-secondary mt-1">
          Realized IC of every currently-active weight set over the last 30 days.
          Red dashed line in each sparkline is the 0.5× predicted-IC auto-revert
          threshold. Grey dashed line is the predicted IC from the seed metadata.
        </p>
      </header>

      <RevertBanner reverts={reverts} />

      <div className="space-y-3">
        {activeSets.length === 0 ? (
          <div className="border border-paper-rule rounded-sm bg-white p-6">
            <p className="font-sans text-sm text-ink-tertiary">
              No active weight sets found.
            </p>
          </div>
        ) : (
          activeSets.map((s) => {
            const pill = statusPill(s.days_below_threshold, s.n_trail_rows)
            return (
              <div
                key={s.version}
                className="border border-paper-rule rounded-sm bg-white p-4"
              >
                <div className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4">
                  <div>
                    <div className="font-serif text-base text-ink-primary">
                      {TIER_LABEL[s.tier] ?? s.tier}
                    </div>
                    <div className="font-mono text-[10px] text-ink-tertiary truncate">
                      {s.version}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-sans text-[10px] text-ink-tertiary">
                      Predicted IC
                    </div>
                    <div className="font-mono text-xs text-ink-primary tabular-nums">
                      {s.predicted_ic
                        ? parseFloat(s.predicted_ic).toFixed(4)
                        : '—'}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-sans text-[10px] text-ink-tertiary">
                      Below threshold
                    </div>
                    <div className="font-mono text-xs text-ink-primary tabular-nums">
                      {s.days_below_threshold}/{s.n_trail_rows}d
                    </div>
                  </div>
                  <RealizedICSparkline
                    trail={s.trail.map((t) => ({
                      as_of_date:
                        typeof t.as_of_date === 'string'
                          ? t.as_of_date
                          : t.as_of_date.toISOString(),
                      realized_ic: t.realized_ic,
                      ic_ratio: t.ic_ratio,
                    }))}
                    predictedIc={s.predicted_ic}
                  />
                </div>
                <div className="flex justify-end mt-2">
                  <span
                    className={`inline-flex px-2 py-0.5 rounded text-[10px] font-semibold border ${pill.cls}`}
                  >
                    {pill.label}
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>
    </main>
  )
}
