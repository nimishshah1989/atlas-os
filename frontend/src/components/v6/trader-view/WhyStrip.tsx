// Trader-view why-strip — colored chips that explain the verdict.

export type ChipState = 'pass' | 'warn' | 'fail' | 'neutral'

export interface Chip {
  label: string
  value: string
  state: ChipState
}

const STATE_CLS: Record<ChipState, string> = {
  pass:    'bg-signal-pos/10 text-ink-secondary',
  warn:    'bg-signal-warn/15 text-ink-secondary',
  fail:    'bg-signal-neg/10 text-ink-secondary',
  neutral: 'bg-paper-soft text-ink-tertiary',
}

const DOT_CLS: Record<ChipState, string> = {
  pass:    'bg-signal-pos',
  warn:    'bg-signal-warn',
  fail:    'bg-signal-neg',
  neutral: 'bg-ink-quaternary',
}

export function WhyStrip({ chips }: { chips: Chip[] }) {
  if (chips.length === 0) return null
  return (
    <div className="flex gap-2 flex-wrap py-3">
      {chips.map((c) => (
        <span
          key={c.label}
          className={`inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 border border-paper-rule rounded-full ${STATE_CLS[c.state]}`}
          data-testid="why-chip"
          data-state={c.state}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${DOT_CLS[c.state]}`} />
          <strong className="text-ink-primary font-semibold">{c.label}</strong>{' '}
          <span>{c.value}</span>
        </span>
      ))}
    </div>
  )
}
