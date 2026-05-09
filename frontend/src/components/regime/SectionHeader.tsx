import type { ReactNode } from 'react'
import { SignalGauge } from './SignalGauge'

type Props = {
  icon: ReactNode
  title: string
  description: string
  bullishCount: number
  totalCount: number
}

export function SectionHeader({ icon, title, description, bullishCount, totalCount }: Props) {
  return (
    <div className="border-t border-paper-rule px-6 pt-6 pb-4">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2.5">
          <span className="text-ink-secondary">{icon}</span>
          <h2 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            {title}
          </h2>
        </div>
        <SignalGauge bullish={bullishCount} total={totalCount} size="sm" />
      </div>
      <p className="font-sans text-xs text-ink-secondary leading-relaxed">
        {description}
      </p>
    </div>
  )
}
