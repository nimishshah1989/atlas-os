// frontend/src/components/v6/stock-detail/ChartCommentary.ts
export interface CommentaryInput {
  state: string | null
  dwellDays: number | null
  stateSinceDate: string | null
  ema20Ratio: number | null
  volRatio63: number | null
  extension: number | null
  high52w: number | null
  price: number | null
}

export function generateChartCommentary(input: CommentaryInput): string {
  const parts: string[] = []

  if (input.state && input.dwellDays !== null) {
    const stateLabel = input.state.replace('stage_', 'Stage ').replace('_', ' ').toUpperCase()
    const freshness = input.dwellDays <= 20 ? 'Recently entered' : input.dwellDays <= 60 ? 'Confirmed in' : 'Established in'
    parts.push(`${freshness} ${stateLabel} ${input.dwellDays} days ago.`)
  }

  if (input.ema20Ratio !== null) {
    const extPct = Math.round((input.ema20Ratio - 1) * 1000) / 10
    if (extPct >= 0 && extPct <= 3) {
      parts.push('Trading close to EMA 20 — not extended.')
    } else if (extPct > 8) {
      parts.push(`Running ${extPct.toFixed(1)}% above EMA 20 — extended, watch for a pullback to base.`)
    } else if (extPct > 0) {
      parts.push(`${extPct.toFixed(1)}% above EMA 20 — not overextended.`)
    } else {
      parts.push(`Holding below EMA 20 — needs to reclaim.`)
    }
  }

  if (input.volRatio63 !== null) {
    if (input.volRatio63 > 1.3) {
      parts.push('Volume expanding — institutional participation confirming the move.')
    } else if (input.volRatio63 < 0.8) {
      parts.push('Volume fading — watch for re-acceleration before adding.')
    } else {
      parts.push('Volume steady — no distribution signal.')
    }
  }

  return parts.join(' ') || 'Insufficient data for commentary.'
}
