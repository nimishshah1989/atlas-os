// Six-lens vector panel for stock detail page.
// Shows the 6 lens scores as horizontal bars with subcomponent breakdown.
// Pure server component — no interactivity needed.

import type { LensScore } from '@/lib/queries/lens-scores'

interface LensVectorPanelProps {
  lens: LensScore
}

type LensConfig = {
  key: string
  label: string
  color: string
  subkeys: { key: keyof LensScore; label: string }[]
}

const LENSES: LensConfig[] = [
  {
    key: 'technical', label: 'Technical', color: 'bg-blue-500',
    subkeys: [
      { key: 'tech_trend', label: 'Trend' },
      { key: 'tech_rs', label: 'RS' },
      { key: 'tech_vol_contraction', label: 'Vol Contraction' },
      { key: 'tech_volume', label: 'Volume' },
    ],
  },
  {
    key: 'fundamental', label: 'Fundamental', color: 'bg-emerald-500',
    subkeys: [
      { key: 'fund_profitability', label: 'Profitability' },
      { key: 'fund_margin', label: 'Margin' },
      { key: 'fund_growth', label: 'Growth' },
      { key: 'fund_balance_sheet', label: 'Balance Sheet' },
      { key: 'fund_op_leverage', label: 'Op Leverage' },
    ],
  },
  {
    key: 'valuation', label: 'Valuation', color: 'bg-amber-500',
    subkeys: [
      { key: 'val_pe_vs_sector', label: 'PE vs Sector' },
      { key: 'val_absolute_pe', label: 'Absolute PE' },
      { key: 'val_pb', label: 'P/B' },
      { key: 'val_ev_ebitda', label: 'EV/EBITDA' },
      { key: 'val_52w_position', label: '52W Position' },
    ],
  },
  {
    key: 'catalyst', label: 'Catalyst', color: 'bg-violet-500',
    subkeys: [
      { key: 'cat_earnings_strategy', label: 'Earnings' },
      { key: 'cat_capital_action', label: 'Capital Action' },
      { key: 'cat_governance', label: 'Governance' },
    ],
  },
  {
    key: 'flow', label: 'Flow', color: 'bg-cyan-500',
    subkeys: [
      { key: 'flow_promoter', label: 'Promoter' },
      { key: 'flow_institutional', label: 'Institutional' },
      { key: 'flow_smart_money', label: 'Smart Money' },
    ],
  },
  {
    key: 'policy', label: 'Policy', color: 'bg-rose-500',
    subkeys: [
      { key: 'policy_tailwind', label: 'Tailwind' },
    ],
  },
]

function scoreColor(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  if (v >= 70) return 'text-signal-pos'
  if (v >= 40) return 'text-ink-secondary'
  return 'text-signal-neg'
}

function tierBadge(tier: string | null): { label: string; cls: string } {
  switch (tier) {
    case 'HIGHEST': return { label: 'HIGHEST', cls: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300' }
    case 'HIGH': return { label: 'HIGH', cls: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300' }
    case 'MEDIUM': return { label: 'MEDIUM', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300' }
    case 'WATCH': return { label: 'WATCH', cls: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300' }
    case 'BELOW_THRESHOLD': return { label: 'BELOW', cls: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' }
    default: return { label: tier ?? '—', cls: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400' }
  }
}

export function LensVectorPanel({ lens }: LensVectorPanelProps) {
  const tier = tierBadge(lens.conviction_tier)
  const riskFlags = lens.risk_flags?.length ? lens.risk_flags : null

  return (
    <section className="rounded-lg border border-ink-border bg-surface-card p-4">
      {/* Header: composite + conviction */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-ink-primary">Six-Lens Vector</h3>
          <p className="text-xs text-ink-tertiary mt-0.5">
            {lens.lenses_active ?? 6} lenses · coverage {((lens.coverage_factor ?? 1) * 100).toFixed(0)}%
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-2xl font-bold text-ink-primary">{lens.composite?.toFixed(1) ?? '—'}</div>
            <div className="text-[10px] text-ink-tertiary uppercase tracking-wide">Composite</div>
          </div>
          <span className={`px-2 py-1 rounded text-xs font-semibold ${tier.cls}`}>{tier.label}</span>
        </div>
      </div>

      {/* Risk flags */}
      {riskFlags && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {riskFlags.map((flag) => (
            <span key={flag} className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
              ⚑ {flag}
            </span>
          ))}
        </div>
      )}

      {/* Lens bars */}
      <div className="space-y-3">
        {LENSES.map((cfg) => {
          const score = lens[cfg.key as keyof LensScore] as number | null
          return (
            <div key={cfg.key}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-ink-secondary">{cfg.label}</span>
                <span className={`text-xs font-semibold tabular-nums ${scoreColor(score)}`}>
                  {score?.toFixed(1) ?? '—'}
                </span>
              </div>
              {/* Main bar */}
              <div className="h-2 rounded-full bg-ink-border/30 overflow-hidden">
                <div
                  className={`h-full rounded-full ${cfg.color} transition-all`}
                  style={{ width: `${Math.min(score ?? 0, 100)}%` }}
                />
              </div>
              {/* Subcomponents — small inline pills */}
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
                {cfg.subkeys.map((sub) => {
                  const sv = lens[sub.key] as number | null
                  return (
                    <span key={sub.key} className="text-[10px] text-ink-tertiary">
                      {sub.label}{' '}
                      <span className={`font-semibold tabular-nums ${scoreColor(sv)}`}>
                        {sv?.toFixed(0) ?? '—'}
                      </span>
                    </span>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {/* Valuation zone */}
      {lens.valuation_zone && (
        <div className="mt-3 pt-3 border-t border-ink-border/30 flex items-center gap-2 text-xs text-ink-secondary">
          <span>Valuation Zone:</span>
          <span className="font-semibold">{lens.valuation_zone}</span>
          {lens.valuation_multiplier != null && (
            <span className="text-ink-tertiary">({lens.valuation_multiplier.toFixed(2)}×)</span>
          )}
        </div>
      )}
    </section>
  )
}
