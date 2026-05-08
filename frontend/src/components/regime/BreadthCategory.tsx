// frontend/src/components/regime/BreadthCategory.tsx
import { Sparkline } from '@/components/ui/Sparkline'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { TOOLTIPS, type TooltipKey } from '@/lib/tooltips'

export type IndicatorRow = {
  key: string
  label: string
  tooltipKey: TooltipKey
  current: number | null
  isBullish: boolean | null      // null = neutral/unknown
  history: (number | null)[]
  format: (v: number) => string  // display formatter
  refLine?: number               // horizontal reference line on sparkline
}

type Props = {
  title: string
  indicators: IndicatorRow[]
  bullishCount: number
  totalCount: number
  commentary: string
}

function SignalDot({ isBullish }: { isBullish: boolean | null }) {
  if (isBullish === null) return <span className="inline-block w-2 h-2 rounded-full bg-paper-rule" />
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${isBullish ? 'bg-signal-pos' : 'bg-signal-neg'}`}
    />
  )
}

function ArrowIndicator({ isBullish }: { isBullish: boolean | null }) {
  if (isBullish === null) return <span className="text-ink-tertiary text-xs">→</span>
  return (
    <span className={`text-xs font-mono ${isBullish ? 'text-signal-pos' : 'text-signal-neg'}`}>
      {isBullish ? '↑' : '↓'}
    </span>
  )
}

export function BreadthCategory({ title, indicators, bullishCount, totalCount, commentary }: Props) {
  const convictionPct = Math.round((bullishCount / totalCount) * 100)
  const convictionColor =
    convictionPct >= 70 ? 'text-signal-pos' :
    convictionPct <= 30 ? 'text-signal-neg' :
    'text-signal-warn'

  return (
    <div className="border border-paper-rule rounded-[2px] p-4">
      {/* Category header */}
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-sans text-sm font-medium text-ink-primary">{title}</h3>
        <span className={`font-mono text-xs tabular-nums font-medium ${convictionColor}`}>
          {bullishCount}/{totalCount} bullish
        </span>
      </div>
      <p className="font-sans text-xs text-ink-tertiary mb-4">{commentary}</p>

      {/* Indicator rows */}
      <div className="space-y-2">
        {indicators.map((ind) => (
          <div key={ind.key} className="flex items-center gap-2">
            <SignalDot isBullish={ind.isBullish} />
            <span className="font-sans text-xs text-ink-secondary w-40 truncate flex-shrink-0">
              {ind.label}
              <InfoTooltip content={TOOLTIPS[ind.tooltipKey]} />
            </span>
            <span className="font-mono text-xs tabular-nums text-ink-primary w-16 text-right flex-shrink-0">
              {ind.current !== null ? ind.format(ind.current) : '–'}
            </span>
            <ArrowIndicator isBullish={ind.isBullish} />
            <Sparkline
              data={ind.history}
              width={80}
              height={20}
              color={ind.isBullish ? 'var(--color-signal-pos)' : ind.isBullish === false ? 'var(--color-signal-neg)' : 'var(--color-ink-tertiary)'}
              refLine={ind.refLine}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
