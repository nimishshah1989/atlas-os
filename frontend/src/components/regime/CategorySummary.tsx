type Props = {
  bullishCount: number
  totalCount: number
  headline: string
  summary: string
}

function getTintClass(bullish: number, total: number): string {
  const r = total > 0 ? bullish / total : 0
  if (r >= 0.65) return 'bg-signal-pos/5 border border-signal-pos/20'
  if (r >= 0.4)  return 'bg-signal-warn/5 border border-signal-warn/20'
  return 'bg-signal-neg/5 border border-signal-neg/20'
}

function getAccentClass(bullish: number, total: number): string {
  const r = total > 0 ? bullish / total : 0
  if (r >= 0.65) return 'text-signal-pos'
  if (r >= 0.4)  return 'text-signal-warn'
  return 'text-signal-neg'
}

export function CategorySummary({ bullishCount, totalCount, headline, summary }: Props) {
  const tintClass   = getTintClass(bullishCount, totalCount)
  const accentClass = getAccentClass(bullishCount, totalCount)
  const pct = totalCount > 0 ? Math.round((bullishCount / totalCount) * 100) : 0

  return (
    <div className="px-6 pb-5">
      <div className={`rounded-sm px-4 py-3 ${tintClass}`}>
        <div className="flex items-baseline gap-3 mb-1">
          <span className={`font-sans text-xs font-bold uppercase tracking-widest ${accentClass}`}>
            {headline}
          </span>
          <span className="font-mono text-[11px] text-ink-tertiary tabular-nums">
            {bullishCount}/{totalCount} signals bullish ({pct}%)
          </span>
        </div>
        <p className="font-sans text-xs text-ink-secondary leading-relaxed">{summary}</p>
      </div>
    </div>
  )
}
