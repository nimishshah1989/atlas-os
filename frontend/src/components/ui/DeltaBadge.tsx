import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

type Direction = 'up' | 'down' | 'unchanged'

type Props = {
  direction: Direction
  label?: string
  className?: string
}

export function DeltaBadge({ direction, label, className = '' }: Props) {
  const config = {
    up:        { icon: TrendingUp,   color: 'text-signal-pos' },
    down:      { icon: TrendingDown, color: 'text-signal-neg' },
    unchanged: { icon: Minus,        color: 'text-ink-tertiary' },
  }[direction]

  const Icon = config.icon

  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-sans ${config.color} ${className}`}>
      <Icon size={12} strokeWidth={1.5} />
      {label && <span>{label}</span>}
    </span>
  )
}
