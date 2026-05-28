// Trader-view return-line — expected return + conviction tier badge.

import { fmtSignedPct } from '@/lib/format-number'

interface ReturnLineProps {
  predictedExcess: number | null
  tenure: string | null
  convictionTier: string | null
  convictionScore: number | null
  verdictSource: 'signal_call' | 'composite_score' | 'no_data' | string | null
}

export function ReturnLine({ predictedExcess, tenure, convictionTier, convictionScore, verdictSource }: ReturnLineProps) {
  const numClass = predictedExcess == null
    ? 'text-ink-tertiary'
    : predictedExcess >= 0 ? 'text-signal-pos' : 'text-signal-neg'

  const tenureLabel = tenure ? tenure.toUpperCase() : '—'

  // Different copy based on whether the prediction is high-confidence (signal_call)
  // or low-confidence (composite_score fallback)
  const leadLabel = verdictSource === 'signal_call' ? 'Expected' : verdictSource === 'composite_score' ? 'Composite-lean' : 'No prediction'

  return (
    <div className="font-mono text-[15px] text-ink-secondary flex items-center gap-3 flex-wrap">
      <span>
        {leadLabel}{' '}
        {predictedExcess != null ? (
          <>
            <span className={`font-semibold ${numClass}`}>{fmtSignedPct(predictedExcess)}</span>
            {' '}over {tenureLabel}
          </>
        ) : convictionScore != null ? (
          <>
            <span className="font-semibold text-ink-secondary">{convictionScore.toFixed(2)}</span>
            {' '}composite score
          </>
        ) : (
          <span className="text-ink-tertiary">—</span>
        )}
      </span>
      {convictionTier && (
        <span className="text-[10px] font-bold tracking-wider px-2 py-0.5 bg-accent/10 text-accent rounded-sm">
          {convictionTier} conviction
        </span>
      )}
    </div>
  )
}
