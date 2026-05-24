// frontend/src/lib/format-cell.ts
// Formatters for cell-rule metrics — see atlas-v6-design-language.md §5.4.
// Always return a dash for null/NaN. Mono-friendly: callers wrap in font-mono.

export function formatIC(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  // 3 decimals, no sign. IC is a magnitude statistic; direction lives elsewhere.
  return value.toFixed(3)
}

export function formatICSigned(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(3)}`
}

export function formatQ(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(3)
}

export function formatFricAdj(value: number | null | undefined): string {
  // value is already a fraction (e.g. 0.148 = +14.8%); render annualized %.
  if (value == null || !Number.isFinite(value)) return '—'
  const pct = value * 100
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}

export function formatGatePass(passed: number | null | undefined, total: number | null | undefined): string {
  if (passed == null || total == null) return '—'
  return `${passed} / ${total}`
}

/** IC color tier — driven from design-language §1.3 (icHigh/Mid/Low/Neg). */
export function icTier(
  ic: number | null | undefined
): 'high' | 'mid' | 'low' | 'neg' | 'empty' {
  if (ic == null || !Number.isFinite(ic)) return 'empty'
  if (ic >= 0.05) return 'high'
  if (ic >= 0.02) return 'mid'
  if (ic >= 0) return 'low'
  return 'neg'
}

/** Tailwind class bundle for an IC tier — background, border, text. */
export function icTierClasses(tier: ReturnType<typeof icTier>): string {
  switch (tier) {
    case 'high':
      return 'bg-signal-pos/15 border-signal-pos/40 text-signal-pos'
    case 'mid':
      return 'bg-teal/10 border-teal/30 text-teal'
    case 'low':
      return 'bg-signal-warn/10 border-signal-warn/30 text-signal-warn'
    case 'neg':
      return 'bg-signal-neg/10 border-signal-neg/30 text-signal-neg'
    case 'empty':
    default:
      return 'bg-paper-rule/20 border-paper-rule text-ink-tertiary'
  }
}

/** Verdict color for a conviction-tape segment. */
export function verdictClasses(
  direction: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL'
): { bg: string; text: string; border: string } {
  switch (direction) {
    case 'POSITIVE':
      return { bg: 'bg-signal-pos', text: 'text-paper', border: 'border-signal-pos' }
    case 'NEGATIVE':
      return { bg: 'bg-signal-neg', text: 'text-paper', border: 'border-signal-neg' }
    case 'NEUTRAL':
    default:
      return { bg: 'bg-ink-tertiary/30', text: 'text-ink-secondary', border: 'border-paper-rule' }
  }
}

export function buildCellId(
  tier: 'Large' | 'Mid' | 'Small',
  tenure: '1m' | '3m' | '6m' | '12m',
  direction: 'POSITIVE' | 'NEGATIVE'
): string {
  return `${tier}-${tenure}-${direction}`
}

export function parseCellId(
  cellId: string
): { tier: 'Large' | 'Mid' | 'Small'; tenure: '1m' | '3m' | '6m' | '12m'; direction: 'POSITIVE' | 'NEGATIVE' } | null {
  const parts = cellId.split('-')
  if (parts.length !== 3) return null
  const [tier, tenure, direction] = parts
  if (!['Large', 'Mid', 'Small'].includes(tier)) return null
  if (!['1m', '3m', '6m', '12m'].includes(tenure)) return null
  if (!['POSITIVE', 'NEGATIVE'].includes(direction)) return null
  return {
    tier: tier as 'Large' | 'Mid' | 'Small',
    tenure: tenure as '1m' | '3m' | '6m' | '12m',
    direction: direction as 'POSITIVE' | 'NEGATIVE',
  }
}
