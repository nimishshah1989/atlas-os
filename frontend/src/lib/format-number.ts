// Format a numeric string from postgres NUMERIC(18,6) for display.
// Rule: trim trailing zeros after the decimal, but always show at least 2 places.
//   "0.200000" -> "0.20"
//   "0.005000" -> "0.005"   (preserves precision for small values)
//   "8.000000" -> "8.00"
//   "20.000000" -> "20.00"
// Returns the input verbatim if it's not a parseable number.

export function formatThreshold(raw: string | null | undefined): string {
  if (raw == null) return '—'
  const n = Number(raw)
  if (!Number.isFinite(n)) return raw
  // Strip trailing zeros first ("0.200000" -> "0.2"), then pad to 2 decimals if shorter.
  const trimmed = raw.includes('.') ? raw.replace(/\.?0+$/, '') : raw
  const dotAt = trimmed.indexOf('.')
  if (dotAt === -1) return `${trimmed}.00`
  const decimals = trimmed.length - dotAt - 1
  if (decimals >= 2) return trimmed
  return trimmed + '0'.repeat(2 - decimals)
}

/**
 * Format a policy percentage field for display.
 * Trims trailing zeros and shows at most 1 decimal place.
 *   "5.0000" -> "5%"
 *   "15.0000" -> "15%"
 *   "8.5000" -> "8.5%"
 *   null -> "—"
 */
export function formatPct(raw: string | number | null | undefined): string {
  if (raw == null) return '—'
  const n = typeof raw === 'number' ? raw : Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  // At most 1 decimal place, trim trailing zero.
  const s = n.toFixed(1).replace(/\.0$/, '')
  return `${s}%`
}

/**
 * Format a rank field (0–1 quantile) for display.
 * Always shows exactly 2 decimal places.
 *   "0.600000" -> "0.60"
 *   "0.700000" -> "0.70"
 *   null -> "—"
 */
export function formatRank(raw: string | number | null | undefined): string {
  if (raw == null) return '—'
  const n = typeof raw === 'number' ? raw : Number(raw)
  if (!Number.isFinite(n)) return String(raw)
  return n.toFixed(2)
}

/**
 * Sign-aware percent formatter. Input is a decimal fraction (e.g. 0.052 = 5.2%).
 * Returns "+5.2%", "-3.1%", or "—" for null/undefined.
 * Use this wherever a financial excess or return needs an explicit sign.
 */
export function fmtSignedPct(v: number | null | undefined, decimals = 1): string {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(decimals)}%`
}
