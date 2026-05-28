// frontend/src/components/v6/india-pulse/helpers.ts
//
// Pure formatting helpers specific to the India Pulse page.
// No side effects, fully testable.

/** Format a decimal fraction as percentage with explicit +/- sign. */
export function fmtPct(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  const abs = Math.abs(pct).toFixed(decimals)
  if (pct < 0) return `−${abs}%`
  return `+${abs}%`
}

/** Format a plain number (not a fraction) as percentage with sign. */
export function fmtPctRaw(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const abs = Math.abs(v).toFixed(decimals)
  if (v < 0) return `−${abs}%`
  return `+${abs}%`
}

/** Format a Z-score with sign. */
export function fmtZ(v: number | null, decimals = 2): string {
  if (v == null) return '—'
  const abs = Math.abs(v).toFixed(decimals)
  if (v < 0) return `−${abs}`
  return `+${abs}`
}

/** Format a decimal fraction as percentage without sign (absolute). */
export function fmtPctAbs(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(decimals)}%`
}

/** Format a number with fixed decimals, null-safe. */
export function fmtNum(v: number | null, decimals = 2): string {
  if (v == null) return '—'
  return v.toFixed(decimals)
}

/** Format a large integer (e.g. crore flows). */
export function fmtInt(v: number | null): string {
  if (v == null) return '—'
  return Math.round(v).toLocaleString('en-IN')
}

/** Format a crore value with sign and ₹ cr suffix. */
export function fmtCrore(v: number | null): string {
  if (v == null) return '—'
  const abs = Math.abs(v)
  const formatted = abs >= 10000
    ? `₹${(abs / 100).toFixed(0)} cr`
    : `₹${Math.round(abs).toLocaleString('en-IN')} cr`
  return v < 0 ? `−${formatted}` : `+${formatted}`
}

/** Determine color class for a numeric value (positive=green, negative=red, null=tertiary). */
export function colorClass(v: number | null, warnThreshold?: number): string {
  if (v == null) return 'text-ink-tertiary'
  if (warnThreshold != null && Math.abs(v) < warnThreshold) return 'text-signal-warn'
  if (v > 0) return 'text-signal-pos'
  if (v < 0) return 'text-signal-neg'
  return 'text-ink-secondary'
}

/** Return left-border class for index cards based on return direction. */
export function indexBorderClass(ret_1d: number | null): string {
  if (ret_1d == null) return 'border-l-ink-tertiary'
  if (ret_1d > 0.005) return 'border-l-signal-pos'
  if (ret_1d < -0.005) return 'border-l-signal-neg'
  return 'border-l-signal-warn'
}

/** Map sector rs_1w value to heatmap color class. Thresholds: ±3% (strong), ±1.5% (mid), ±0.3% (flat). */
export function sectorColorClass(rs1w: number | null): string {
  if (rs1w == null) return 'bg-paper border border-paper-rule'
  const pct = rs1w * 100
  if (pct >= 3.0) return 'bg-[rgba(47,107,67,0.55)]'
  if (pct >= 1.5) return 'bg-[rgba(47,107,67,0.30)]'
  if (pct > 0.3) return 'bg-[rgba(47,107,67,0.15)]'
  if (pct >= -0.3) return 'bg-paper border border-paper-rule'
  if (pct >= -1.5) return 'bg-[rgba(176,73,44,0.15)]'
  if (pct >= -3.0) return 'bg-[rgba(176,73,44,0.30)]'
  return 'bg-[rgba(176,73,44,0.55)]'
}

/** Text color for sector cell (dark cells need white text). */
export function sectorTextColor(rs1w: number | null): string {
  if (rs1w == null) return 'text-ink-secondary'
  const pct = rs1w * 100
  if (pct >= 3.0 || pct <= -3.0) return 'text-paper'
  return 'text-ink-secondary'
}

/** Format a date string to DD-MMM-YYYY. */
export function fmtDateDMY(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const day = String(d.getDate()).padStart(2, '0')
  const mon = d.toLocaleString('en-US', { month: 'short' })
  const yr = d.getFullYear()
  return `${day}-${mon}-${yr}`
}
