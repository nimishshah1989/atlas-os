// SP04 Stage 4c — top-of-page banner when any auto-revert fired in the
// last 24 hours. Rendered on /admin/composite-proposals and
// /admin/weight-performance.
import type { RevertLogRow } from '@/lib/queries/weight_performance'

type Props = {
  reverts: RevertLogRow[]
}

const TIER_LABEL: Record<string, string> = {
  tier_1_megacap: 'Tier 1 (mega-cap)',
  tier_2_largecap: 'Tier 2 (large-cap)',
  tier_3_uppermid: 'Tier 3 (upper mid-cap)',
  tier_4_lowermid: 'Tier 4 (lower mid-cap)',
  tier_5_smallcap: 'Tier 5 (small-cap)',
}

function within24Hours(d: Date | string): boolean {
  const date = typeof d === 'string' ? new Date(d) : d
  return Date.now() - date.getTime() < 24 * 60 * 60 * 1000
}

export function RevertBanner({ reverts }: Props) {
  const recent = reverts.filter((r) => within24Hours(r.applied_at))
  if (recent.length === 0) return null

  return (
    <div className="border border-sig-neg/30 bg-sig-neg-soft rounded-panel px-4 py-3 mb-4">
      <div className="flex items-baseline justify-between mb-1">
        <h2 className="font-sans text-[11px] text-sig-neg uppercase tracking-wider font-semibold">
          ⚠ Auto-revert{recent.length === 1 ? '' : 's'} fired
        </h2>
        <span className="font-sans text-[10px] text-txt-3">
          last 24 hours
        </span>
      </div>
      <ul className="space-y-1">
        {recent.map((r) => (
          <li key={r.id} className="font-sans text-xs text-txt-2">
            {TIER_LABEL[r.tier] ?? r.tier}: realized IC averaged{' '}
            <span className="font-num tabular-nums">
              {r.realized_ic_avg ? parseFloat(r.realized_ic_avg).toFixed(4) : '—'}
            </span>{' '}
            vs predicted{' '}
            <span className="font-num tabular-nums">
              {r.predicted_holdout_ic
                ? parseFloat(r.predicted_holdout_ic).toFixed(4)
                : '—'}
            </span>{' '}
            for {r.days_below_threshold} days. Reverted to previous version.
          </li>
        ))}
      </ul>
    </div>
  )
}
