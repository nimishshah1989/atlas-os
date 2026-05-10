'use client'
import { RSStateChip, MomentumChip, RiskChip, VolumeChip } from '@/lib/stock-formatters'

type ChipType = 'rs' | 'momentum' | 'risk' | 'volume'

type Props = {
  chipType: ChipType
  state: string | null
  scalar: string | null
  className?: string
}

export function StateValuePair({ chipType, state, scalar, className = '' }: Props) {
  const chip =
    chipType === 'rs'       ? <RSStateChip value={state} /> :
    chipType === 'momentum' ? <MomentumChip value={state} /> :
    chipType === 'volume'   ? <VolumeChip value={state} /> :
                              <RiskChip value={state} />

  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      {chip}
      <span className="font-mono text-[10px] text-ink-tertiary tabular-nums">
        {scalar ?? '—'}
      </span>
    </span>
  )
}
