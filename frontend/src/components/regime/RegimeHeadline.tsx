// frontend/src/components/regime/RegimeHeadline.tsx
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { Commentary } from '@/components/ui/Commentary'
import { TOOLTIPS } from '@/lib/tooltips'
import { generateRegimeCommentary } from '@/lib/commentary/regime'
import type { MarketRegimeRow } from '@/lib/queries/regime'

type Props = {
  regime: MarketRegimeRow
}

const DEPLOYMENT_LABELS: Record<string, string> = {
  '1':   'Full deployment',
  '0.7': 'Reduced deployment',
  '0.4': 'Minimal deployment',
  '0':   'No new exposure',
}

export function RegimeHeadline({ regime }: Props) {
  const vix = regime.india_vix ? parseFloat(regime.india_vix).toFixed(1) : null
  const deployment = parseFloat(regime.deployment_multiplier)
  const deploymentPct = Math.round(deployment * 100)
  const deploymentLabel = DEPLOYMENT_LABELS[regime.deployment_multiplier] ?? `${deploymentPct}%`
  const commentary = generateRegimeCommentary(regime)
  const dataAsOf = regime.date instanceof Date
    ? regime.date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
    : String(regime.date)

  return (
    <div className="px-8 pt-8 pb-6 border-b border-paper-rule">
      <div className="flex items-start justify-between mb-2">
        {/* Regime state — dominant headline */}
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="font-serif text-4xl font-semibold text-ink-primary leading-none">
              {regime.regime_state}
            </h1>
            {regime.dislocation_active && (
              <span className="inline-flex items-center px-2 py-1 text-xs font-sans font-medium text-signal-neg border border-signal-neg/40 rounded-[2px] bg-signal-neg/5">
                Dislocation active since {regime.dislocation_started
                  ? new Date(regime.dislocation_started).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
                  : '–'}
              </span>
            )}
          </div>
          <div className="flex items-center gap-4 text-sm font-sans text-ink-secondary">
            <span className="font-mono tabular-nums">
              Deployment: <span className="font-medium text-ink-primary">{deploymentPct}%</span>
              {' '}
              <span className="text-ink-tertiary">({deploymentLabel})</span>
              <InfoTooltip content={TOOLTIPS.deployment_multiplier} />
            </span>
            {vix && (
              <span className="font-mono tabular-nums">
                India VIX: <span className="font-medium text-ink-primary">{vix}</span>
                <InfoTooltip content={TOOLTIPS.india_vix} />
              </span>
            )}
          </div>
        </div>

        {/* Data freshness */}
        <span className="font-sans text-xs text-ink-tertiary mt-1">
          Data as of {dataAsOf}
        </span>
      </div>

      <Commentary text={commentary} className="mt-3 max-w-2xl" />
    </div>
  )
}
