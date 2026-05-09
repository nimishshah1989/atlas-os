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
