import { Activity, BarChart2, Zap, Users } from 'lucide-react'
import { Sparkline } from '@/components/ui/Sparkline'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { TOOLTIPS, type TooltipKey } from '@/lib/tooltips'
import { SignalGauge } from './SignalGauge'

export type IndicatorRow = {
  key: string
  label: string
  tooltipKey: TooltipKey
  current: number | null
  isBullish: boolean | null
  history: (number | null)[]
  format: (v: number) => string
  refLine?: number
}

type Props = {
  title: string
  indicators: IndicatorRow[]
  bullishCount: number
  totalCount: number
}

function SignalDot({ isBullish }: { isBullish: boolean | null }) {
  if (isBullish === null)
    return <span className="inline-block w-1.5 h-1.5 rounded-full bg-paper-rule flex-shrink-0 mt-px" />
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 mt-px ${
        isBullish ? 'bg-signal-pos' : 'bg-signal-neg'
      }`}
    />
  )
}

function CategoryIcon({ title }: { title: string }) {
  const cls = 'w-3.5 h-3.5 text-ink-tertiary flex-shrink-0'
  if (title === 'Trend')         return <Activity className={cls} strokeWidth={1.75} />
  if (title === 'Breadth')       return <BarChart2 className={cls} strokeWidth={1.75} />
  if (title === 'Momentum')      return <Zap className={cls} strokeWidth={1.75} />
  return <Users className={cls} strokeWidth={1.75} />
}

export function BreadthCategory({ title, indicators, bullishCount, totalCount }: Props) {
  return (
    <div className="px-5 py-4">
      {/* Category header: icon + name + gauge */}
      <div className="flex items-center gap-1.5 mb-3">
        <CategoryIcon title={title} />
        <span className="font-sans text-[11px] font-semibold text-ink-secondary uppercase tracking-wider">
          {title}
        </span>
        <div className="ml-auto">
          <SignalGauge bullish={bullishCount} total={totalCount} size="sm" />
        </div>
      </div>

      {/* Indicator rows — compact */}
      <div className="space-y-1.5">
        {indicators.map((ind) => (
          <div key={ind.key} className="flex items-center gap-1.5">
            <SignalDot isBullish={ind.isBullish} />
            <span className="font-sans text-[11px] text-ink-secondary flex-1 min-w-0 truncate leading-tight">
              {ind.label}
              <InfoTooltip content={TOOLTIPS[ind.tooltipKey]} />
            </span>
            <span className="font-mono text-[11px] tabular-nums text-ink-primary flex-shrink-0 w-12 text-right">
              {ind.current !== null ? ind.format(ind.current) : '–'}
            </span>
            <Sparkline
              data={ind.history}
              width={52}
              height={16}
              color={
                ind.isBullish
                  ? 'var(--color-signal-pos)'
                  : ind.isBullish === false
                  ? 'var(--color-signal-neg)'
                  : 'var(--color-ink-tertiary)'
              }
              refLine={ind.refLine}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
