// fundCategoryCurve — every number on /funds/compare is computed here.
//
// Pure by design: takes arrays of { d, v }, returns arrays and numbers. No DB, no React,
// no clock. The SQL module hands it real rows; the components hand it to the formatter.
// Keeping the arithmetic in one testable place is the whole point — the composite is a
// chain-linked index and getting the compounding subtly wrong is invisible on a chart.

/** One point on a series: ISO date, and a value (a rebased index level, or a percentage). */
export type CurvePoint = { d: string; v: number }

/** A return over a span. `pct` is a percentage (-1.58 means -1.58%), not a fraction. */
export type SpanReturn = { pct: number; annualised: boolean; days: number }

/** The seven trailing periods the returns table renders. */
export const PERIODS = [
  { key: '1m', label: '1M', months: 1 },
  { key: '3m', label: '3M', months: 3 },
  { key: '6m', label: '6M', months: 6 },
  { key: '1y', label: '1Y', months: 12 },
  { key: '2y', label: '2Y', months: 24 },
  { key: '3y', label: '3Y', months: 36 },
  { key: '5y', label: '5Y', months: 60 },
] as const

const MS_PER_DAY = 24 * 3600 * 1000

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / MS_PER_DAY)
}

/** Rebase a series so its first point is exactly 100. Empty in, empty out. */
export function rebase(pts: CurvePoint[]): CurvePoint[] {
  const base = pts[0]?.v
  if (base == null || base <= 0) return []
  return pts.map((p) => ({ d: p.d, v: (100 * p.v) / base }))
}

/**
 * Return between the first and last point. Absolute at a year or less; CAGR above it,
 * on actual day count — annualising a six-month number would overstate it.
 */
export function spanReturn(pts: CurvePoint[]): SpanReturn | null {
  const a = pts[0]
  const b = pts.at(-1)
  if (a == null || b == null || a === b || a.v <= 0) return null
  const days = daysBetween(a.d, b.d)
  if (days <= 0) return null
  const growth = b.v / a.v
  const annualised = days > 365
  const pct = annualised ? growth ** (365.25 / days) - 1 : growth - 1
  return { pct: pct * 100, annualised, days }
}

/** Subtract whole calendar months, clamping to the shorter month (31 Mar - 1m = 28/29 Feb). */
export function minusMonths(iso: string, months: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const targetMonth = m - months
  const yy = y + Math.floor((targetMonth - 1) / 12)
  const mm = ((((targetMonth - 1) % 12) + 12) % 12) + 1
  const lastDay = new Date(Date.UTC(yy, mm, 0)).getUTCDate()
  const dd = Math.min(d, lastDay)
  return `${yy}-${String(mm).padStart(2, '0')}-${String(dd).padStart(2, '0')}`
}

/**
 * Trailing return over N calendar months, anchored on the last observation on or before
 * (last date - N months). Returns null — never 0 — when the series does not reach back
 * that far; a missing period must read "—", not "flat".
 */
export function trailingReturn(pts: CurvePoint[], months: number): SpanReturn | null {
  const last = pts.at(-1)
  if (last == null) return null
  const anchor = minusMonths(last.d, months)
  let startIdx = -1
  for (let i = 0; i < pts.length; i++) {
    if (pts[i].d <= anchor) startIdx = i
    else break
  }
  if (startIdx < 0) return null
  return spanReturn([pts[startIdx], last])
}

/**
 * Rolling return through time: for each date, the return since the last observation on or
 * before (date - N years). Windows are calendar-anchored, so a 1Y window means a year, not
 * "250 rows back" — trading-day counts drift and a row-count window silently stops being a
 * year once a series has gaps. Where the anchor lands between observations the window errs
 * long, never short: a shorter-than-requested window would understate the return.
 * Values are percentages.
 */
export function rollingReturns(pts: CurvePoint[], years: number): CurvePoint[] {
  const out: CurvePoint[] = []
  let start = 0
  for (const p of pts) {
    const anchor = minusMonths(p.d, years * 12)
    while (start + 1 < pts.length && pts[start + 1].d <= anchor) start++
    const from = pts[start]
    if (from.d > anchor || from.v <= 0 || from === p) continue
    out.push({ d: p.d, v: (p.v / from.v - 1) * 100 })
  }
  return out
}

export type RollingStats = {
  n: number
  min: number
  p25: number
  median: number
  p75: number
  max: number
  /** % of dates where the composite beat the benchmark, or null with no benchmark. */
  beatRate: number | null
}

/** Linear-interpolated percentile over a sorted array. */
function percentile(sorted: number[], p: number): number {
  const k = (sorted.length - 1) * p
  const lo = Math.floor(k)
  const hi = Math.min(lo + 1, sorted.length - 1)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (k - lo)
}

/** Distribution of a rolling series, plus how often it beat a benchmark on matching dates. */
export function rollingStats(comp: CurvePoint[], bench: CurvePoint[]): RollingStats | null {
  if (comp.length === 0) return null
  const sorted = comp.map((p) => p.v).sort((a, b) => a - b)
  const byDate = new Map(bench.map((p) => [p.d, p.v]))
  const paired = comp.filter((p) => byDate.has(p.d))
  return {
    n: comp.length,
    min: sorted[0],
    p25: percentile(sorted, 0.25),
    median: percentile(sorted, 0.5),
    p75: percentile(sorted, 0.75),
    max: sorted[sorted.length - 1],
    beatRate: paired.length === 0
      ? null
      : (100 * paired.filter((p) => p.v > byDate.get(p.d)!).length) / paired.length,
  }
}

export type ThinCoverage = {
  /** Dates where fewer than half the category's peak contributor count reported. */
  days: number
  worst: { d: string; n: number } | null
  peak: number
}

/**
 * Dates where the composite rested on far fewer funds than the category actually holds.
 * Mostly Saturdays and holidays, where a handful of schemes still stamp a NAV — the average
 * that day is over those few, not over the category, and it compounds into the curve like
 * any other day. Worth naming on the page; the chart's coverage strip alone squashes these
 * into a spike the eye reads as noise.
 *
 * Peak is tracked as a running maximum, so a category that grew from 40 funds to 70 is not
 * retroactively judged thin for its early years.
 */
export function thinCoverage(counts: { d: string; n: number }[]): ThinCoverage {
  let peak = 0
  let days = 0
  let worst: { d: string; n: number } | null = null
  for (const c of counts) {
    if (c.n === 0) continue // the anchor row has no contributors by construction
    peak = Math.max(peak, c.n)
    if (c.n < peak / 2) {
      days++
      if (worst == null || c.n < worst.n) worst = { d: c.d, n: c.n }
    }
  }
  return { days, worst, peak }
}
