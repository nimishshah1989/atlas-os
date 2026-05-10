import type { FundRow } from '@/lib/queries/funds'
import type { CommentaryResult } from '@/lib/commentary/stocks'
import { CommentaryBlock } from '@/components/ui/CommentaryBlock'
import { CHART_COLORS } from '@/lib/chart-colors'

const NAV_STATES = [
  'Leader NAV',
  'Strong NAV',
  'Emerging NAV',
  'Average NAV',
  'Weak NAV',
  'Laggard NAV',
  'DISLOCATION_SUSPENDED',
]

const REC_STATES = ['Recommended', 'Hold', 'Reduce', 'Exit']

const REC_COLORS: Record<string, string> = {
  Recommended: CHART_COLORS.rsLeader,
  Hold:        CHART_COLORS.rsConsolidating,
  Reduce:      CHART_COLORS.rsWeak,
  Exit:        CHART_COLORS.rsLaggard,
}

function navStateColor(state: string): string {
  if (state === 'Leader NAV')   return CHART_COLORS.rsLeader
  if (state === 'Strong NAV')   return CHART_COLORS.rsStrong
  if (state === 'Emerging NAV') return CHART_COLORS.rsEmerging
  if (state === 'Average NAV')  return CHART_COLORS.rsAverage
  if (state === 'Weak NAV' || state === 'Laggard NAV') return CHART_COLORS.rsWeak
  return CHART_COLORS.inkTertiary  // DISLOCATION_SUSPENDED
}

function navStateLabel(state: string): string {
  if (state === 'DISLOCATION_SUSPENDED') return 'Susp'
  return state.replace(/ NAV$/, '')
}

function DistBar({
  label,
  count,
  total,
  color,
}: {
  label: string
  count: number
  total: number
  color: string
}) {
  const pct = total > 0 ? (count / total) * 100 : 0
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="w-16 text-ink-tertiary font-mono shrink-0 text-right">{label}</span>
      <div className="flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-6 text-ink-tertiary font-mono text-right">{count}</span>
    </div>
  )
}

type Props = {
  funds: FundRow[]
  commentary: CommentaryResult
  medianRsPctile: number
  medianReturn: number | null
  topCategory: { name: string; mean: number } | null
}

export function FundIntelligencePanel({
  funds,
  commentary,
  medianRsPctile,
  medianReturn,
  topCategory,
}: Props) {
  const n = funds.length
  if (n === 0) return null

  const navCounts: Record<string, number> = Object.fromEntries(NAV_STATES.map(s => [s, 0]))
  const recCounts: Record<string, number> = Object.fromEntries(REC_STATES.map(s => [s, 0]))

  for (const fund of funds) {
    if (fund.nav_state && navCounts[fund.nav_state] !== undefined) {
      navCounts[fund.nav_state]++
    }
    if (fund.recommendation && recCounts[fund.recommendation] !== undefined) {
      recCounts[fund.recommendation]++
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* Left: NAV State distribution */}
        <div className="space-y-1.5">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
            NAV State
          </div>
          {NAV_STATES.map(s => (
            <DistBar
              key={s}
              label={navStateLabel(s)}
              count={navCounts[s] ?? 0}
              total={n}
              color={navStateColor(s)}
            />
          ))}
        </div>

        {/* Right: Recommendation distribution + top category */}
        <div className="space-y-1.5">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
            Recommendation
          </div>
          {REC_STATES.map(s => (
            <DistBar
              key={s}
              label={s}
              count={recCounts[s] ?? 0}
              total={n}
              color={REC_COLORS[s] ?? CHART_COLORS.inkTertiary}
            />
          ))}

          {/* Top category callout */}
          <div className="pt-2">
            {topCategory && (
              <div className="rounded-sm bg-paper-rule/10 border border-paper-rule/40 px-3 py-2">
                <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
                  Top Category (RS)
                </div>
                <div className="font-sans text-sm font-semibold text-ink-primary">
                  {topCategory.name}
                </div>
                <div className="font-mono text-[10px] text-ink-tertiary">
                  {(topCategory.mean * 100).toFixed(0)}th pctile avg
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Median stats row */}
      <div className="flex gap-4 text-[10px] font-mono text-ink-tertiary">
        <span>
          Median RS:{' '}
          <span className="text-ink-primary">{(medianRsPctile * 100).toFixed(0)}th</span>
        </span>
        {medianReturn != null && (
          <span>
            Median Ret:{' '}
            <span className={medianReturn >= 0 ? 'text-signal-pos' : 'text-signal-neg'}>
              {medianReturn >= 0 ? '+' : ''}
              {(medianReturn * 100).toFixed(1)}%
            </span>
          </span>
        )}
      </div>

      {/* Commentary */}
      <div className="border-t border-paper-rule pt-3">
        <CommentaryBlock narrative={commentary.narrative} contextCards={commentary.contextCards} />
      </div>
    </div>
  )
}
