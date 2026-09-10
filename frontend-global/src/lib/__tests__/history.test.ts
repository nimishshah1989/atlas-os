// The two history readings, tested on CONSTRUCTED series.
//
// WHAT THESE NUMBERS ARE, SAID PLAINLY. Every close below is the test's own, chosen to make an
// ordering or an edge case unambiguous. None of them is a market close and none is claimed to be:
// this container cannot reach the price spine, and a number I could not read is a number I must
// not label with a source (rule #0 cuts both ways — it forbids inventing data, and it forbids
// dressing invented data in a provenance).
//
// That is the right fixture for what is under test. `calendarYears` and `underwater` are ALGEBRA
// over a series — which two sessions a year is measured between, what happens when the benchmark
// is missing on one of them, whether a rising series reports zero drawdown or none. An ordering is
// proved by orderings. The BOARD's figures come from the same functions over
// `atlas_global.ohlcv_daily.close_tr`, which is where every number a reader sees originates.
//
// Round numbers on purpose: 100 → 90 is a ten percent fall exactly, and a test whose expected
// value needs a calculator hides its own arithmetic error.
import { describe, expect, it } from 'vitest'
import { calendarYears, underwater, type ClosePoint } from '@/lib/history'

// One session per year — the last of each — on real US trading dates, with the test's own closes:
// up a tenth, down a fifth, up a quarter. Enough shape to tell a base from an end and a peak from
// a trough.
const YEAR_ENDS: ClosePoint[] = [
  { date: '2021-12-31', close_tr: '100' },
  { date: '2022-12-30', close_tr: '80' },
  { date: '2023-12-29', close_tr: '100' },
  { date: '2024-12-31', close_tr: '125' },
]

describe('calendar years', () => {
  const rows = calendarYears(YEAR_ENDS, YEAR_ENDS)

  it('measures each year from the PREVIOUS year’s last close, not the current year’s first', () => {
    const y2022 = rows.find((r) => r.year === '2022')!
    expect(y2022.from).toBe('2021-12-31')
    expect(y2022.to).toBe('2022-12-30')
    // 80 / 100 − 1. Had it started from the 2022 sessions instead, the year's opening fall would
    // be missing from the figure entirely.
    expect(y2022.fund).toBeCloseTo(-0.2, 10)
  })

  it('returns newest year first, because that is the one being read', () => {
    expect(rows.map((r) => r.year)).toEqual(['2024', '2023', '2022'])
  })

  it('flags the earliest year PARTIAL — its base is the first session on the spine, not a 31 December', () => {
    // 2021 has no previous year-end here, and its own only session IS the base, so it is dropped
    // rather than reported as a zero year. Give it two sessions and it appears, flagged.
    const withStart = [{ date: '2021-01-04', close_tr: '90' }, ...YEAR_ENDS]
    const r = calendarYears(withStart, withStart)
    const y2021 = r.find((x) => x.year === '2021')!
    expect(y2021.partial).toBe(true)
    expect(y2021.from).toBe('2021-01-04')
    expect(r.filter((x) => x.partial)).toHaveLength(1)
  })

  it('compares the index over the FUND’S OWN two sessions, so excess is zero against itself', () => {
    for (const r of rows) expect(r.excess).toBeCloseTo(0, 10)
  })

  it('leaves excess NULL where the index has no close on one of those two sessions', () => {
    // A fund that traded on a session SPY has no row for — the test's own construction.
    const fund: ClosePoint[] = [
      { date: '2023-12-29', close_tr: '100' },
      { date: '2024-12-31', close_tr: '125' },
    ]
    const [row] = calendarYears(fund, [{ date: '2023-12-29', close_tr: '100' }])
    expect(row.fund).toBeCloseTo(0.25, 10)
    expect(row.spy).toBeNull()
    expect(row.excess).toBeNull()
  })

  it('has nothing to say about a series of one session', () => {
    expect(calendarYears([YEAR_ENDS[0]], YEAR_ENDS)).toEqual([])
    expect(calendarYears([], [])).toEqual([])
  })
})

describe('the underwater curve', () => {
  it('names the deepest point over the whole spine', () => {
    const { worst } = underwater(YEAR_ENDS)
    // Against the peak of 100 set in 2021, the 2022 close of 80 is the low of these four.
    expect(worst!.date).toBe('2022-12-30')
    expect(worst!.dd).toBeCloseTo(-0.2, 10)
  })

  it('is zero at a new high, and says which peak today is measured against', () => {
    const { curve, current } = underwater(YEAR_ENDS)
    expect(curve[curve.length - 1].dd).toBeCloseTo(0, 10)
    expect(current!.peak).toBe('2024-12-31')
  })

  it('reports a series that only ever rose as never under water — 0 is the true answer, not "no data"', () => {
    const rising: ClosePoint[] = [
      { date: '2023-01-03', close_tr: '10' },
      { date: '2023-06-01', close_tr: '11' },
      { date: '2023-12-29', close_tr: '12' },
    ]
    const { worst, curve } = underwater(rising)
    expect(worst!.dd).toBe(0)
    expect(curve.every((p) => p.dd === 0)).toBe(true)
  })

  it('skips a session with no close rather than treating it as a fall to zero', () => {
    const gapped: ClosePoint[] = [
      { date: '2023-01-03', close_tr: '100' },
      { date: '2023-01-04', close_tr: null },
      { date: '2023-01-05', close_tr: '90' },
    ]
    const { curve, worst } = underwater(gapped)
    expect(curve.map((c) => c.date)).toEqual(['2023-01-03', '2023-01-05'])
    expect(worst!.dd).toBeCloseTo(-0.1, 10)
  })

  it('has nothing to draw from nothing', () => {
    expect(underwater([])).toEqual({ curve: [], worst: null, current: null })
  })
})
