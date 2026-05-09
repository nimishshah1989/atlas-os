import {
  getStrengthLevel,
  getStrengthDots,
  getStrengthColorClass,
  getStrengthDotFillClass,
} from '@/lib/regime-narrative'

type Props = {
  bullish: number
  total: number
  size?: 'sm' | 'md'
}

export function SignalGauge({ bullish, total, size = 'md' }: Props) {
  const level = getStrengthLevel(bullish, total)
  const dots = getStrengthDots(bullish, total)
  const colorClass = getStrengthColorClass(level)
  const dotFill = getStrengthDotFillClass(level)
  const dotSize = size === 'sm' ? 'w-[6px] h-[6px]' : 'w-[7px] h-[7px]'

  return (
    <div className="flex items-center gap-1.5">
      <div className="flex gap-[3px]">
        {dots.map((filled, i) => (
          <span
            key={i}
            className={`inline-block rounded-full ${dotSize} ${filled ? dotFill : 'bg-paper-rule'}`}
          />
        ))}
      </div>
      <span className={`font-sans text-xs font-medium ${colorClass}`}>{level}</span>
    </div>
  )
}
