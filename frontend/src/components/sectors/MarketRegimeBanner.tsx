// frontend/src/components/sectors/MarketRegimeBanner.tsx
import { TrendingUp, Minus, TrendingDown } from 'lucide-react'
import type { MarketRegimeRow } from '@/lib/queries/regime'

type RegimeConfig = {
  bg: string
  border: string
  textColor: string
  Icon: typeof TrendingUp
  label: string
}

const REGIME_CONFIG: Record<string, RegimeConfig> = {
  'Risk-On':  { bg: 'bg-signal-pos/5', border: 'border-signal-pos/20', textColor: 'text-signal-pos',  Icon: TrendingUp,   label: 'Risk-On'  },
  'Cautious': { bg: 'bg-signal-warn/5', border: 'border-signal-warn/20', textColor: 'text-signal-warn', Icon: Minus,        label: 'Cautious' },
  'Risk-Off': { bg: 'bg-signal-neg/5', border: 'border-signal-neg/20', textColor: 'text-signal-neg',  Icon: TrendingDown, label: 'Risk-Off' },
}

function fmtPct(v: string | null, digits = 0): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n.toFixed(digits)}%`
}

export function MarketRegimeBanner({ regime }: { regime: MarketRegimeRow }) {
  const cfg = REGIME_CONFIG[regime.regime_state] ?? REGIME_CONFIG['Cautious']
  const { Icon } = cfg

  return (
    <div className={`px-5 py-2 border-b ${cfg.bg} ${cfg.border} flex items-center gap-3 flex-wrap`}>
      <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">Market</span>
      <div className={`flex items-center gap-1 ${cfg.textColor}`}>
        <Icon className="w-3 h-3" />
        <span className="font-sans text-xs font-semibold">{cfg.label}</span>
      </div>
      <span className="text-paper-rule select-none">·</span>
      <div className="flex items-center gap-1">
        <span className="font-sans text-[11px] text-ink-tertiary">Deploy</span>
        <span className="font-mono text-xs font-semibold text-ink-primary">
          {fmtPct(regime.deployment_multiplier)}
        </span>
      </div>
      <span className="text-paper-rule select-none">·</span>
      <div className="flex items-center gap-1">
        <span className="font-sans text-[11px] text-ink-tertiary">Market above EMA-50</span>
        <span className="font-mono text-xs font-semibold text-ink-primary">
          {fmtPct(regime.pct_above_ema_50)}
        </span>
      </div>
    </div>
  )
}
