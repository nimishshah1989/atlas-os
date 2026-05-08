type StateColor = 'pos' | 'neg' | 'warn' | 'neutral' | 'accent'

const STATE_COLORS: Record<string, StateColor> = {
  // Regime
  'Risk-On':     'pos',
  'Constructive':'accent',
  'Cautious':    'warn',
  'Risk-Off':    'neg',
  'DISLOCATION_SUSPENDED': 'neg',
  // Sector
  'Overweight':  'pos',
  'Neutral':     'neutral',
  'Underweight': 'warn',
  'Avoid':       'neg',
  // RS states
  'Leader':      'pos',
  'Strong':      'pos',
  'Emerging':    'accent',
  'Average':     'neutral',
  'Consolidating': 'neutral',
  'Weak':        'warn',
  'Laggard':     'neg',
  // Momentum
  'Accelerating': 'pos',
  'Improving':    'pos',
  'Flat':         'neutral',
  'Deteriorating':'warn',
  'Collapsing':   'neg',
  // Risk
  'Low':          'pos',
  'Normal':       'neutral',
  'Elevated':     'warn',
  'High':         'neg',
  'Below Trend':  'neutral',
  // Fund
  'Recommended':  'pos',
  'Hold':         'neutral',
  'Reduce':       'warn',
  'Exit':         'neg',
  // Composition
  'Aligned':      'pos',
  'Mixed':        'neutral',
  'Misaligned':   'neg',
  // Holdings
  'Strong-Holdings': 'pos',
  'Decent':          'neutral',
  'Weak-Holdings':   'neg',
}

const COLOR_CLASSES: Record<StateColor, string> = {
  pos:     'text-signal-pos bg-signal-pos/10 border-signal-pos/20',
  neg:     'text-signal-neg bg-signal-neg/10 border-signal-neg/20',
  warn:    'text-signal-warn bg-signal-warn/10 border-signal-warn/20',
  neutral: 'text-ink-secondary bg-paper-rule/20 border-paper-rule',
  accent:  'text-accent bg-accent/10 border-accent/20',
}

type Props = {
  state: string
  size?: 'sm' | 'md'
  className?: string
}

export function StateBadge({ state, size = 'md', className = '' }: Props) {
  const color = STATE_COLORS[state] ?? 'neutral'
  const classes = COLOR_CLASSES[color]
  const sizeClasses = size === 'sm'
    ? 'text-xs px-1.5 py-0.5'
    : 'text-xs px-2 py-1'

  return (
    <span
      className={`inline-flex items-center font-sans font-medium border rounded-[2px] tabular-nums ${sizeClasses} ${classes} ${className}`}
    >
      {state}
    </span>
  )
}
