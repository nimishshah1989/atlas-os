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
    return { label: 'Bootstrap', cls: 'bg-surface-inset text-txt-2 border-edge-rule' }
  }
  if (daysBelow === nTrail) {
    return { label: 'Revert imminent', cls: 'bg-sig-neg-soft text-sig-neg border-sig-neg/40' }
  }
  if (daysBelow >= 15) {
    return { label: 'Watch', cls: 'bg-sig-warn/10 text-sig-warn border-sig-warn/40' }
  }
  return { label: 'OK', cls: 'bg-brand-soft text-brand border-brand/30' }
}

export default async function WeightPerformancePage() {
  const [activeSets, reverts] = await Promise.all([
    getActiveWeightSetsWithTrail(),
    getRecentReverts(),
  ])

  return (
    <main className="min-h-screen bg-surface-panel px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <div className="font-sans text-[10px] text-txt-3 uppercase tracking-wider">
          Atlas · Admin · Stage 4c
        </div>
        <h1 className="font-display text-2xl text-txt-1 mt-1">
          Weight-Set Live Performance
        </h1>
        <p className="font-sans text-xs text-txt-2 mt-1">
          Realized IC of every currently-active weight set over the last 30 days.
          Red dashed line in each sparkline is the 0.5× predicted-IC auto-revert
          threshold. Grey dashed line is the predicted IC from the seed metadata.
        </p>
      </header>

      <RevertBanner reverts={reverts} />

      <div className="space-y-3">
        {activeSets.length === 0 ? (
          <div className="border border-edge-hair rounded-panel bg-surface-panel p-6">
            <p className="font-sans text-sm text-txt-3">
              No active weight sets found.
            </p>
          </div>
        ) : (
          activeSets.map((s) => {
            const pill = statusPill(s.days_below_threshold, s.n_trail_rows)
            return (
              <div
                key={s.version}
                className="border border-edge-hair rounded-panel bg-surface-panel p-4"
              >
                <div className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4">
                  <div>
                    <div className="font-display text-base text-txt-1">
                      {TIER_LABEL[s.tier] ?? s.tier}
                    </div>
                    <div className="font-num text-[10px] text-txt-3 truncate">
                      {s.version}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-sans text-[10px] text-txt-3">
                      Predicted IC
                    </div>
                    <div className="font-num text-xs text-txt-1 tabular-nums">
                      {s.predicted_ic
                        ? parseFloat(s.predicted_ic).toFixed(4)
                        : '—'}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-sans text-[10px] text-txt-3">
                      Below threshold
                    </div>
                    <div className="font-num text-xs text-txt-1 tabular-nums">
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
                    className={`inline-flex px-2 py-0.5 rounded-tile text-[10px] font-semibold border ${pill.cls}`}
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
