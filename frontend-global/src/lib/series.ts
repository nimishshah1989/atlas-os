// src/lib/series.ts — the arithmetic behind the price chart and the return calculator. No React,
// no database. Every function here is the reason a number on the detail page can be checked.
//
// WHAT A RETURN IS COMPUTED ON. `close_tr` — splits AND dividends. A price-only return understates
// a dividend-heavy fund by whole points a year, and the whole product is a comparison between
// funds, so the one that pays more must not read as the one that earned less. The page prints the
// price-only figure BESIDE it, because the difference is the income and a reader is entitled to
// see it separately, not because either is optional.
//
// WHAT A CHART IS DRAWN ON. `close_adj` — splits only. It is what compute_technicals.py runs the
// EMAs on, and an EMA-200 drawn over a different series is two lines pretending to be one.
//
// NOTHING IS INTERPOLATED. A window that has no session on the requested day uses the nearest
// session AT OR BEFORE it and reports which day that was. Inventing a price for a day the market
// was shut is exactly the class of number rule #0 exists to keep off this board.

export type Bar = { date: string; close_adj: string | null; close_tr: string | null }

/** The benchmark only ever needs its total-return close: it is drawn rebased and compared on
 *  total return, never on its own split-adjusted price. */
export type BenchmarkBar = { date: string; close_tr: string | null }

/** Named windows, in SESSIONS. Trading days, not calendar days: a 6-month button that means 126
 *  sessions gives the same amount of history whatever the holidays did. */
export const RANGES = [
  { key: '3m', label: '3M', sessions: 63 },
  { key: '6m', label: '6M', sessions: 126 },
  { key: '1y', label: '1Y', sessions: 252 },
  { key: '3y', label: '3Y', sessions: 756 },
  { key: '5y', label: '5Y', sessions: 1260 },
  { key: '10y', label: '10Y', sessions: 2520 },
  { key: 'max', label: 'Max', sessions: Number.POSITIVE_INFINITY },
] as const

export type RangeKey = (typeof RANGES)[number]['key']

export const DEFAULT_RANGE: RangeKey = '1y'

const n = (s: string | null | undefined): number | null => {
  if (s == null || s === '') return null
  const v = Number(s)
  return Number.isFinite(v) ? v : null
}

/** The last `sessions` entries. Fewer than that and the whole series comes back — a fund listed
 *  last March has a real one-year chart, it is just shorter than a year. */
export function lastSessions<T>(rows: readonly T[], sessions: number): T[] {
  if (!Number.isFinite(sessions) || rows.length <= sessions) return [...rows]
  return rows.slice(rows.length - sessions)
}

/** Both series indexed to 100 at the FIRST session of the window, so two instruments at different
 *  prices can be read against each other. Points before the first usable close are dropped rather
 *  than carried at 100, which would draw a flat line the instrument never had. */
export function rebase(rows: readonly { date: string; value: string | null }[]): { date: string; value: number }[] {
  let base: number | null = null
  const out: { date: string; value: number }[] = []
  for (const r of rows) {
    const v = n(r.value)
    if (v == null || v <= 0) continue
    if (base == null) base = v
    out.push({ date: r.date, value: (v / base) * 100 })
  }
  return out
}

/** The session at or before `date`, by binary search over an ascending series. Null when the
 *  series starts after it — the instrument did not exist, and the caller says so. */
export function sessionAtOrBefore<T extends { date: string }>(rows: readonly T[], date: string): T | null {
  let lo = 0
  let hi = rows.length - 1
  let found: T | null = null
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (rows[mid].date <= date) {
      found = rows[mid]
      lo = mid + 1
    } else hi = mid - 1
  }
  return found
}

export type PeriodReturn = {
  /** The sessions actually used — never the dates asked for, when the market was shut on those. */
  from: string
  to: string
  /** Total return over the window (splits and dividends), as a fraction. */
  total: number | null
  /** The same window on split-adjusted closes — total return minus the income. */
  price: number | null
  /** SPY over the SAME two sessions, for the comparison the board is built on. */
  benchmark: number | null
  /** total − benchmark, in the relative form the RS columns use: (1+r)/(1+b) − 1. */
  relative: number | null
}

const growth = (from: number | null, to: number | null): number | null =>
  from == null || to == null || from <= 0 ? null : to / from - 1

/** What an instrument did between two dates, on the sessions that actually exist. `null` when the
 *  window falls outside the series — never a zero, which would read as "it went nowhere". */
export function periodReturn(
  bars: readonly Bar[],
  benchmark: readonly BenchmarkBar[],
  fromDate: string,
  toDate: string,
): PeriodReturn | null {
  if (bars.length === 0 || fromDate > toDate) return null
  const a = sessionAtOrBefore(bars, fromDate)
  const b = sessionAtOrBefore(bars, toDate)
  if (!a || !b || a.date === b.date) return null

  const total = growth(n(a.close_tr), n(b.close_tr))
  const price = growth(n(a.close_adj), n(b.close_adj))
  // The BENCHMARK is read at the instrument's own two sessions, not at the requested dates: two
  // series compared over different windows is not a comparison.
  const ba = sessionAtOrBefore(benchmark, a.date)
  const bb = sessionAtOrBefore(benchmark, b.date)
  const bench = ba && bb ? growth(n(ba.close_tr), n(bb.close_tr)) : null

  return {
    from: a.date,
    to: b.date,
    total,
    price,
    benchmark: bench,
    // ADR-0002's relative form — the same arithmetic compute_technicals.py writes into rs_*_spy,
    // so the calculator and the RS columns can never disagree about what "beating SPY" means.
    relative: total == null || bench == null ? null : (1 + total) / (1 + bench) - 1,
  }
}

// ── the trend read, in words ────────────────────────────────────────────────

/** What the moving averages say, as one short phrase. The FM's ask is to find strong instruments
 *  fast; "21 > 50 > 200" is the shape every technician reads first, and spelling it saves the
 *  reader from comparing three numbers themselves. Null inputs give null — a young instrument
 *  has no 200-day average and is not therefore in a downtrend. */
export function emaStack(
  ema21: string | null,
  ema50: string | null,
  ema200: string | null,
): { label: string; tone: 'pos' | 'neg' | 'neutral' } | null {
  const a = n(ema21)
  const b = n(ema50)
  const c = n(ema200)
  if (a == null || b == null || c == null) return null
  if (a > b && b > c) return { label: 'Stacked up — 21 over 50 over 200', tone: 'pos' }
  if (a < b && b < c) return { label: 'Stacked down — 21 under 50 under 200', tone: 'neg' }
  return { label: 'Crossed — the averages disagree', tone: 'neutral' }
}
