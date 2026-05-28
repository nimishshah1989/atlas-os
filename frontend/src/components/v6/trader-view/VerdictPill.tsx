// Trader-view verdict pill — single large decision label per spec §4.
// Vocabulary: CONTEXT.md §"Cell state vocabulary" (BUY/ACCUMULATE/WATCH/HOLD/AVOID/SELL/WAIT).

export type Verdict =
  | 'BUY' | 'ACCUMULATE'
  | 'WATCH' | 'HOLD'
  | 'AVOID' | 'SELL'
  | 'WAIT'

const COLORS: Record<Verdict, string> = {
  BUY:        'bg-signal-pos text-paper',
  ACCUMULATE: 'bg-signal-pos text-paper',
  WATCH:      'bg-ink-tertiary text-paper',
  HOLD:       'bg-ink-tertiary text-paper',
  AVOID:      'bg-signal-neg text-paper',
  SELL:       'bg-signal-neg text-paper',
  WAIT:       'bg-signal-warn text-paper',
}

// Optional conviction-tier modifier — T1 vibrant, T5 faded.
// Composite-derived BUYs with low conviction render with reduced opacity
// to surface the confidence axis orthogonally to the verdict axis.
function tierOpacity(tier: string | null | undefined): string {
  if (!tier) return ''
  const t = tier.toUpperCase()
  if (t === 'T1') return ''
  if (t === 'T2') return 'opacity-90'
  if (t === 'T3') return 'opacity-75'
  if (t === 'T4') return 'opacity-60'
  if (t === 'T5') return 'opacity-45'
  return ''
}

export function VerdictPill({
  verdict,
  convictionTier,
}: {
  verdict: Verdict | string | null
  convictionTier?: string | null
}) {
  if (!verdict || !(verdict in COLORS)) {
    return (
      <span className="inline-block font-serif text-[34px] font-medium px-[22px] py-[6px] leading-[1.1] rounded-sm bg-paper-soft text-ink-tertiary border border-paper-rule">
        —
      </span>
    )
  }
  const v = verdict as Verdict
  return (
    <span
      className={`inline-block font-serif text-[34px] font-medium px-[22px] py-[6px] leading-[1.1] rounded-sm ${COLORS[v]} ${tierOpacity(convictionTier)}`}
      data-testid="verdict-pill"
      data-verdict={v}
      data-conviction-tier={convictionTier ?? ''}
    >
      {v}
    </span>
  )
}
