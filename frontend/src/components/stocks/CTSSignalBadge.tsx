'use client'

type Stage = 1 | 2 | 3 | 4 | null
type Signal = 'PPC' | 'NPC' | 'Contraction' | null

const STAGE_STYLES: Record<number, string> = {
  2: 'bg-signal-pos/10 text-signal-pos border border-signal-pos/30',
  1: 'bg-paper-rule/20 text-ink-secondary border border-paper-rule',
  3: 'bg-signal-warn/10 text-signal-warn border border-signal-warn/30',
  4: 'bg-signal-neg/10 text-signal-neg border border-signal-neg/30',
}

const STAGE_TOOLTIPS: Record<number, string> = {
  1: 'Stage 1 — Base-building: below declining 150-day MA. Range-bound, no directional bias.',
  2: 'Stage 2 — Advancing: price above rising 150-day MA. Primary uptrend in progress.',
  3: 'Stage 3 — Distribution: above MA but slope flattening. Potential topping.',
  4: 'Stage 4 — Decline: below declining 150-day MA. Avoid.',
}

export function StageBadge({ stage }: { stage: Stage }) {
  if (!stage) return (
    <span className="text-ink-tertiary text-xs" aria-label="No stage data">—</span>
  )
  const label = `S${stage}`
  return (
    <span
      data-testid="stage-badge"
      title={STAGE_TOOLTIPS[stage]}
      aria-label={STAGE_TOOLTIPS[stage]}
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] text-xs font-mono font-medium ${STAGE_STYLES[stage]}`}
    >
      {label}
    </span>
  )
}

const SIGNAL_STYLES: Record<string, string> = {
  PPC: 'bg-signal-pos/10 text-signal-pos border border-signal-pos/30',
  NPC: 'bg-signal-neg/10 text-signal-neg border border-signal-neg/30',
  Contraction: 'bg-signal-warn/10 text-signal-warn border border-signal-warn/30',
}

const SIGNAL_TOOLTIPS: Record<string, string> = {
  PPC: 'Positive Pivotal Candle — large-range up-close candle on elevated volume. Setup for continuation.',
  NPC: 'Negative Pivotal Candle — large-range down-close candle on elevated volume. Setup for reversal.',
  Contraction: 'Price contraction near highs on declining ATR. Coil before potential breakout.',
}

export function SignalBadge({ signal, date }: { signal: Signal; date?: Date | string }) {
  if (!signal) return (
    <span className="text-ink-tertiary text-xs" aria-label="No CTS signal">—</span>
  )
  const dateStr = date
    ? (date instanceof Date ? date : new Date(date)).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
    : undefined
  return (
    <div className="flex flex-col gap-0.5">
      <span
        data-testid="signal-badge"
        title={SIGNAL_TOOLTIPS[signal]}
        aria-label={`${signal}: ${SIGNAL_TOOLTIPS[signal]}`}
        className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] text-xs font-mono font-medium ${SIGNAL_STYLES[signal]}`}
      >
        {signal}
      </span>
      {dateStr && <span className="text-ink-tertiary text-[10px]">{dateStr}</span>}
    </div>
  )
}
