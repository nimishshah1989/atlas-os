/**
 * decimal.ts — Postgres NUMERIC → TypeScript number transport utility.
 *
 * postgres-js returns NUMERIC columns as `string`. Recharts/D3 chart props
 * require `number`. This module is the single conversion boundary — use these
 * helpers instead of bare `Number(x)` on values that may be Decimal strings.
 *
 * Rules:
 *   - null/undefined pass-through (toNumber returns null, not 0)
 *   - Invalid strings throw TypeError (fast-fail, never silent NaN)
 *   - All percentage inputs are decimal fractions (0.183 = 18.3%)
 */

// ---------------------------------------------------------------------------
// Core conversion
// ---------------------------------------------------------------------------

/**
 * Convert a Postgres NUMERIC string to a JavaScript number.
 *
 * - null / undefined → null (safe pass-through for optional columns)
 * - valid numeric string → number
 * - invalid / non-numeric string → throws TypeError (not silent NaN)
 */
// Sentinel strings that the UI uses for "no data". Treat as null instead of
// throwing — chart consumers downstream gracefully skip nulls.
const NULL_SENTINELS = new Set(['—', '-', 'N/A', 'n/a', 'NaN', 'nan', 'null', 'undefined'])

export function toNumber(s: string | null | undefined): number | null {
  if (s == null) return null
  const trimmed = typeof s === 'string' ? s.trim() : s
  if (trimmed === '') return null
  if (typeof trimmed === 'string' && NULL_SENTINELS.has(trimmed)) return null
  const n = Number(trimmed)
  if (!Number.isFinite(n)) {
    throw new TypeError(`toNumber: "${s}" is not a valid number`)
  }
  return n
}

/**
 * Convert a Postgres NUMERIC string to a number, returning `fallback` when
 * the value is null/undefined. Throws on non-numeric strings (same as toNumber).
 *
 * Typical use: chart data props where null means "render nothing" but a
 * component default (e.g., 0) is acceptable as a fallback.
 */
export function toNumberOr(s: string | null | undefined, fallback: number): number {
  const result = toNumber(s)
  return result === null ? fallback : result
}

// ---------------------------------------------------------------------------
// Indian Rupee formatting
// ---------------------------------------------------------------------------

const INR_FORMATTER = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const CRORE = 10_000_000
const LAKH = 100_000

/**
 * Format a Postgres NUMERIC string as Indian Rupee.
 *
 * - null/undefined → "—" (em-dash sentinel)
 * - `compact: true` → short form using lakh/crore (e.g., "₹12.5 Cr", "₹1.25 L")
 * - Default: full format using en-IN grouping (e.g., "₹12,345.67")
 */
export function formatINR(
  s: string | null | undefined,
  opts?: { compact?: boolean },
): string {
  if (s == null) return '—'
  const n = toNumber(s)
  if (n === null) return '—'

  if (opts?.compact) {
    if (Math.abs(n) >= CRORE) {
      const crores = n / CRORE
      return `₹${crores.toFixed(crores % 1 === 0 ? 0 : 2)} Cr`
    }
    if (Math.abs(n) >= LAKH) {
      const lakhs = n / LAKH
      return `₹${lakhs.toFixed(lakhs % 1 === 0 ? 0 : 1)} L`
    }
    // Below lakh: fall through to standard format
  }

  return INR_FORMATTER.format(n)
}

// ---------------------------------------------------------------------------
// Percentage formatting
// ---------------------------------------------------------------------------

/**
 * Format a decimal fraction as a percentage string.
 *
 * Input is a decimal fraction (e.g., 0.183 → "18.3%").
 *
 * - null/undefined → "—"
 * - Positive values are prefixed with "+" by default
 * - Negative values render with "−" (e.g., "-14.6%")
 * - `decimals` controls decimal places (default: 1)
 * - `signed: false` suppresses the "+" prefix on positive values
 */
export function formatPct(
  s: string | null | undefined,
  opts?: { decimals?: number; signed?: boolean },
): string {
  if (s == null) return '—'
  const n = toNumber(s)
  if (n === null) return '—'

  const decimals = opts?.decimals ?? 1
  const signed = opts?.signed ?? true
  const pct = n * 100

  const formatted = Math.abs(pct).toFixed(decimals)
  if (pct < 0) return `-${formatted}%`
  if (pct > 0 && signed) return `+${formatted}%`
  return `${formatted}%`
}

/**
 * Always-signed percentage formatter.
 *
 * Like formatPct but the "+" prefix is always applied (including 0.00%).
 * Input is a decimal fraction (e.g., 0.183 → "+18.30%").
 *
 * - null/undefined → "—"
 * - Zero → "+0.0%" (or "+0.00%" with decimals: 2)
 * - `decimals` defaults to 1
 */
export function signedPct(
  s: string | null | undefined,
  opts?: { decimals?: number },
): string {
  if (s == null) return '—'
  const n = toNumber(s)
  if (n === null) return '—'

  const decimals = opts?.decimals ?? 1
  const pct = n * 100

  const formatted = Math.abs(pct).toFixed(decimals)
  if (pct < 0) return `-${formatted}%`
  return `+${formatted}%`
}
