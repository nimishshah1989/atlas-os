// src/lib/history.ts — what ten years of one instrument's own closes say, as two readings a fund
// manager acts on: how it did each calendar year AGAINST THE INDEX, and how far below its own
// peak it has ever been.
//
// The FM: "the kind of data we have, there is so much historical context we can give. We can build
// really rich instrument pages" — and, on how: "having more visual elements like line charts",
// "using baseline to compare stuff everywhere".
//
// NO NEW QUERY. Both readings are computed from the SAME `close_tr` series the price chart already
// draws, and the benchmark from the SAME SPY series already fetched over the same dates. A second
// query would be a second opinion about one instrument's history, and the day it disagreed with
// the chart above it, both would be worthless.
//
// WHY ARITHMETIC IS ALLOWED HERE. Rule #2 keeps FLOATS AWAY FROM MONEY: a price, a fee, an AUM
// never passes through a double. A RETURN is a ratio of two real closes, not a money amount, and
// the board already computes one this way in ReturnCalculator — which sets the precedent this
// follows, including its rule that the two sessions used are NAMED rather than implied.
//
// TOTAL RETURN, NOT PRICE. Every figure here is on `close_tr` — splits and dividends — because a
// fund that pays out four percent a year and a fund that does not are not comparable on price, and
// a dividend-heavy year read off `close_adj` would show as a year of underperformance that never
// happened.

/** One session of a series, as the queries hand it over: NUMERIC as text. */
export type ClosePoint = { date: string; close_tr: string | null }

const num = (v: string | null | undefined): number | null => {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? n : null
}

const yearOf = (iso: string) => iso.slice(0, 4)

/** The last session of each calendar year in a series, plus the very first session of all — the
 *  anchors every year's return is measured between. */
function anchors(points: readonly ClosePoint[]): Map<string, ClosePoint> {
  const last = new Map<string, ClosePoint>()
  for (const p of points) if (num(p.close_tr) != null) last.set(yearOf(p.date), p)
  return last
}

export type YearRow = {
  year: string
  /** Total return over the year, as a fraction. Null where a close is missing at either end. */
  fund: number | null
  /** SPY over the SAME two sessions — never over the calendar year, which would compare a fund's
   *  268 sessions against an index's 251 and call the difference skill. */
  spy: number | null
  /** fund − spy, in points. Null unless both sides are measured. */
  excess: number | null
  /** True for the first year in the window, whose base is the earliest session on the spine rather
   *  than the previous 31 December — a part-year, and the row says so instead of pretending. */
  partial: boolean
  /** The two sessions the figure was measured between, so the number is checkable. */
  from: string
  to: string
}

/** Calendar-year total return, the fund beside the index, on the fund's own sessions.
 *
 *  THE BASE IS THE PREVIOUS YEAR'S LAST CLOSE, not the current year's first. Starting inside the
 *  year silently discards the first session's move, which for a fund that gaps on 2 January is the
 *  part of the year that mattered. The earliest year has no previous close, so it is measured from
 *  the first session on the spine and flagged `partial`. */
export function calendarYears(
  points: readonly ClosePoint[],
  benchmark: readonly ClosePoint[],
): YearRow[] {
  const usable = points.filter((p) => num(p.close_tr) != null)
  if (usable.length < 2) return []
  const spyBy = new Map(benchmark.filter((b) => num(b.close_tr) != null).map((b) => [b.date, b]))
  const ends = anchors(usable)
  const years = [...ends.keys()].sort()

  const rows: YearRow[] = []
  for (let i = 0; i < years.length; i++) {
    const y = years[i]
    const end = ends.get(y)!
    const prev = i === 0 ? usable[0] : ends.get(years[i - 1])!
    // The earliest year's base IS its own first session, so a one-session year has nothing to
    // measure and is dropped rather than reported as zero.
    if (prev.date === end.date) continue
    const a = num(prev.close_tr)!
    const b = num(end.close_tr)!
    const fund = b / a - 1
    const sa = num(spyBy.get(prev.date)?.close_tr ?? null)
    const sb = num(spyBy.get(end.date)?.close_tr ?? null)
    const spy = sa != null && sb != null ? sb / sa - 1 : null
    rows.push({
      year: y,
      fund,
      spy,
      excess: spy == null ? null : fund - spy,
      partial: i === 0,
      from: prev.date,
      to: end.date,
    })
  }
  return rows.reverse()
}

export type Underwater = {
  /** One point per session: how far below the running peak, as a NEGATIVE fraction (0 at a high). */
  curve: { date: string; dd: number }[]
  /** The deepest point, and the session it happened on. Null when the series is too short. */
  worst: { date: string; dd: number } | null
  /** The peak the instrument is measured against TODAY, and how far below it the last close sits. */
  current: { peak: string; dd: number } | null
}

/** The underwater curve: how far below its own running high the instrument has been, every day.
 *
 *  This is the risk reading a volatility number cannot give. Two funds at 18 percent annualised
 *  volatility are not the same fund if one of them spent 2022 forty percent under water; the curve
 *  shows the shape of the pain and how long it lasted, which is what an FM is actually asked about
 *  by the person holding it. The producer stores `mdd_12m` — one number over one window — and this
 *  is the same measure over the whole spine, from the same column. */
export function underwater(points: readonly ClosePoint[]): Underwater {
  let peak = 0
  let peakDate = ''
  const curve: { date: string; dd: number }[] = []
  let worst: { date: string; dd: number } | null = null
  for (const p of points) {
    const c = num(p.close_tr)
    if (c == null) continue
    if (c >= peak) {
      peak = c
      peakDate = p.date
    }
    const dd = peak > 0 ? c / peak - 1 : 0
    curve.push({ date: p.date, dd })
    if (worst == null || dd < worst.dd) worst = { date: p.date, dd }
  }
  if (curve.length === 0) return { curve: [], worst: null, current: null }
  return {
    curve,
    // A series that only ever rose has no drawdown to report, and 0 is the true answer there.
    worst,
    current: { peak: peakDate, dd: curve[curve.length - 1].dd },
  }
}
