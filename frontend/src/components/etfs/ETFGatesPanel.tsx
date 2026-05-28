import { CheckCircle2, XCircle } from 'lucide-react'
import type { ETFRow } from '@/lib/queries/etfs'

type Gate = {
  key: keyof Pick<ETFRow, 'strength_gate' | 'direction_gate' | 'risk_gate' | 'sector_gate' | 'market_gate'>
  label: string
  description: string
  threshold: string
}

const GATES: Gate[] = [
  {
    key: 'strength_gate',
    label: 'Strength',
    description: 'RS state is Leader or Strong — ETF outperforming peers.',
    threshold: 'Pass when RS 3M percentile ≥ 70th (top 30th percentile of universe). Leader = ≥85th.',
  },
  {
    key: 'direction_gate',
    label: 'Direction',
    description: 'Momentum is Accelerating or Improving — RS trend is rising.',
    threshold: 'Pass when EMA10/EMA20 ratio > 1.0 and improving week-over-week.',
  },
  {
    key: 'risk_gate',
    label: 'Risk',
    description: 'Risk state is Low or Normal — extension and volatility within bounds.',
    threshold: 'Fail when price is >40% above 200-day MA (over-extended) or realized vol > 1.5× benchmark.',
  },
  {
    key: 'sector_gate',
    label: 'Sector',
    description: 'Linked sector is not in Avoid state.',
    threshold: 'Fail when the sector this ETF tracks has sector_state = Avoid (bottom-up deterioration).',
  },
  {
    key: 'market_gate',
    label: 'Market',
    description: 'Market regime is not in Risk-off — broad market supports new positions.',
    threshold: 'Fail when NIFTY50 regime_state is Risk-Off or Dislocation. Blocks all new entries.',
  },
]

function GateRow({
  label,
  description,
  threshold,
  pass,
}: {
  label: string
  description: string
  threshold: string
  pass: boolean | null
}) {
  const Icon = pass ? CheckCircle2 : XCircle
  const iconClass = pass == null
    ? 'text-ink-tertiary'
    : pass ? 'text-signal-pos' : 'text-signal-neg'

  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-paper-rule last:border-0">
      <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${iconClass}`} />
      <div className="flex-1 min-w-0">
        <div className="font-sans text-xs font-semibold text-ink-primary">{label}</div>
        <div className="font-sans text-[11px] text-ink-tertiary leading-snug mt-0.5">{description}</div>
        <div className="font-sans text-[10px] text-ink-tertiary/70 leading-snug mt-1 italic">{threshold}</div>
      </div>
      <div className="ml-auto font-sans text-xs font-semibold shrink-0">
        <span className={pass == null ? 'text-ink-tertiary' : pass ? 'text-signal-pos' : 'text-signal-neg'}>
          {pass == null ? '—' : pass ? 'Pass' : 'Fail'}
        </span>
      </div>
    </div>
  )
}

export function ETFGatesPanel({ etf }: { etf: ETFRow }) {
  const passCount = GATES.filter(g => etf[g.key] === true).length

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      <div className="px-4 py-3 border-b border-paper-rule flex items-center justify-between">
        <div>
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Decision Gates
          </div>
          <div className="font-sans text-[10px] text-ink-tertiary/60 mt-0.5">
            All 5 must pass for investable status
          </div>
        </div>
        <div className="font-sans text-xs text-ink-secondary">
          <span className={passCount >= 5 ? 'text-signal-pos font-semibold' : passCount >= 3 ? 'text-signal-warn font-semibold' : 'text-signal-neg font-semibold'}>
            {passCount}
          </span>
          <span className="text-ink-tertiary">/5 passing</span>
        </div>
      </div>
      <div className="px-4">
        {GATES.map(g => (
          <GateRow
            key={g.key}
            label={g.label}
            description={g.description}
            threshold={g.threshold}
            pass={etf[g.key] ?? null}
          />
        ))}
      </div>
      {etf.is_investable && etf.pct_stage_2 != null && etf.weinstein_gate_pass === false && (
        <div className="px-4 py-2.5 border-t border-paper-rule bg-signal-warn/10">
          <div className="font-sans text-xs font-semibold text-signal-warn mb-0.5">● 5/5 statutory gates pass — but Weinstein advisory says WAIT</div>
          <div className="font-sans text-[11px] text-ink-tertiary leading-[1.45]">The 5 gates above (strength · direction · risk · sector · market) all pass, but the ETF is currently below its 30-week MA or in Stage 3/4. Hold existing; wait for Stage 2 confirmation before adding new positions.</div>
        </div>
      )}
      {etf.is_investable && etf.pct_stage_2 != null && etf.weinstein_gate_pass !== false && (
        <div className="px-4 py-2.5 border-t border-paper-rule bg-signal-pos/5">
          <span className="font-sans text-xs font-semibold text-signal-pos">
            ● All gates passed — Investable
          </span>
        </div>
      )}
    </div>
  )
}
