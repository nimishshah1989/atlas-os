// Hex values mirror globals.css CSS custom properties exactly.
// Recharts and D3 both need hex strings, not Tailwind class names.

export const CHART_COLORS = {
  // RS states (7-level)
  rsLeader:        '#2F6B43',   // --color-signal-pos
  rsStrong:        '#1D9E75',   // --color-teal
  rsEmerging:      '#25394A',   // --color-accent
  rsConsolidating: '#B8860B',   // --color-signal-warn
  rsAverage:       '#8C8278',   // --color-ink-tertiary
  rsWeak:          '#B0492C',   // --color-signal-neg
  rsLaggard:       '#B0492C',   // --color-signal-neg

  // Momentum states
  momAccelerating:  '#2F6B43',
  momImproving:     '#1D9E75',
  momFlat:          '#8C8278',
  momDeteriorating: '#B8860B',
  momCollapsing:    '#B0492C',

  // Regime states
  riskOn:         '#2F6B43',
  constructive:   '#1D9E75',
  cautious:       '#B8860B',
  riskOff:        '#B0492C',

  // Neutral / structural
  grid:        '#C2B8A8',   // --color-paper-rule
  inkTertiary: '#8C8278',   // --color-ink-tertiary
  paper:       '#F8F4EC',   // --color-paper
} as const

/** Map RS state string → chart hex color. Falls back to inkTertiary. */
export function rsStateColor(rsState: string | null): string {
  switch (rsState) {
    case 'Leader':        return CHART_COLORS.rsLeader
    case 'Strong':        return CHART_COLORS.rsStrong
    case 'Emerging':      return CHART_COLORS.rsEmerging
    case 'Consolidating': return CHART_COLORS.rsConsolidating
    case 'Average':       return CHART_COLORS.rsAverage
    case 'Weak':          return CHART_COLORS.rsWeak
    case 'Laggard':       return CHART_COLORS.rsLaggard
    default:              return CHART_COLORS.inkTertiary
  }
}

/** Map RS + Momentum → bubble chart fill color. Strong fading → warn; others follow RS. */
export function bubbleColor(rsState: string | null, momState: string | null): string {
  if (rsState === 'Leader') return CHART_COLORS.rsLeader
  if (rsState === 'Strong' && (momState === 'Deteriorating' || momState === 'Collapsing'))
    return CHART_COLORS.rsConsolidating
  if (rsState === 'Strong')        return CHART_COLORS.rsStrong
  if (rsState === 'Emerging')      return CHART_COLORS.rsEmerging
  if (rsState === 'Consolidating') return CHART_COLORS.rsConsolidating
  if (rsState === 'Average')       return CHART_COLORS.rsAverage
  return CHART_COLORS.rsWeak
}
