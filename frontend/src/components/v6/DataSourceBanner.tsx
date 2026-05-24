// frontend/src/components/v6/DataSourceBanner.tsx
//
// Thin strip surfacing "Live API" vs "Demo data" + the data-as-of timestamp.
// Sits below the page title row. Never larger than 28px tall.

import { formatIST } from '@/lib/format-date'

type Props = {
  source: 'live' | 'demo'
  asOf: string
  hint?: string
}

export function DataSourceBanner({ source, asOf, hint }: Props) {
  const isLive = source === 'live'
  const label = isLive ? 'Live API' : 'Demo data — backend endpoint not yet wired'
  const dot = isLive ? 'bg-signal-pos' : 'bg-signal-warn'
  const text = isLive ? 'text-ink-secondary' : 'text-ink-secondary'
  return (
    <div className="px-6 py-1.5 border-b border-paper-rule/60 flex items-center gap-3 bg-paper">
      <span className="inline-flex items-center gap-1.5 font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
        <span className={text}>{label}</span>
      </span>
      <span className="font-sans text-[10px] text-ink-tertiary">
        Data as of {formatIST(asOf)}
      </span>
      {hint && (
        <span className="font-sans text-[10px] text-ink-tertiary ml-auto">
          {hint}
        </span>
      )}
    </div>
  )
}
