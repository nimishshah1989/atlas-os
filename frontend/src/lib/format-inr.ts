// Format a number as Indian Rupee per ~/.claude/rules/frontend-viz.md.
// Uses en-IN locale which produces lakh/crore grouping (₹1,23,45,678).
// 2 decimal places for display; returns "—" for null/undefined/NaN.

export function formatINR(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/**
 * Format an INR amount without the currency symbol (for inputs).
 * "1000000" -> "10,00,000"
 */
export function formatINRPlain(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return ''
  return value.toLocaleString('en-IN')
}
