// frontend/src/components/v6/RegimeIndicator.tsx
//
// Compact regime header: current state, deploy %, breadth, 252-d strip thumb.
// Used in sidebars + the /regime hero strip.

import type { MarketRegime } from '@/lib/api/v1'
import { StateBadge } from '@/components/ui/StateBadge'
import { Sparkline } from '@/components/ui/Sparkline'
import { CHART_COLORS } from '@/lib/chart-colors'

type Props = {
  regime: MarketRegime
  compact?: boolean
}

export function RegimeIndicator({ regime, compact = false }: Props) {
  const breadthPct = regime.pct_above_ema_50 != null ? Math.round(regime.pct_above_ema_50 * 100) : null
  const stripData = regime.history.map(h => h.pct_above_ema_50)

  if (compact) {
    return (
      <div className="inline-flex items-center gap-3 px-3 py-1.5 border border-paper-rule rounded-[2px] bg-paper">
        <StateBadge state={regime.regime_state} size="sm" />
        <span className="font-mono text-xs tabular-nums text-ink-primary">
          {regime.deployment_pct}% deploy
        </span>
        <span className="font-mono text-xs tabular-nums text-ink-secondary">
          {breadthPct != null ? `${breadthPct}% above EMA-50` : '—'}
        </span>
        <span className="text-ink-tertiary">
          <Sparkline data={stripData} width={60} height={18} color={CHART_COLORS.constructive} />
        </span>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
      <div className="flex items-baseline justify-between mb-3">
        <div>
          <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
            Market Regime
          </div>
          <div className="flex items-baseline gap-3">
            <span className="font-serif text-3xl font-semibold leading-none text-ink-primary">
              {regime.regime_state}
            </span>
            <span className="font-mono text-sm tabular-nums text-ink-secondary">
              · deploy {regime.deployment_pct}%
            </span>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Metric label="Above EMA-50" value={breadthPct != null ? `${breadthPct}%` : '—'} />
        <Metric label="Net Stage-2 (5d)" value={regime.net_stage_2_5d != null ? `${regime.net_stage_2_5d >= 0 ? '+' : ''}${regime.net_stage_2_5d}` : '—'} />
        <Metric label="Participation" value={regime.participation != null ? `${Math.round(regime.participation * 100)}%` : '—'} />
      </div>
      <div>
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          252-day breadth
        </div>
        <Sparkline data={stripData} width={400} height={48} color={CHART_COLORS.constructive} refLine={0.5} className="w-full" />
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</div>
      <div className="font-mono text-lg font-semibold tabular-nums text-ink-primary leading-none mt-1">
        {value}
      </div>
    </div>
  )
}
