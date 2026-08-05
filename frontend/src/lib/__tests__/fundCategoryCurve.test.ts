import { describe, it, expect } from 'vitest'
import {
  fetchStart, growthReturn, minusMonths, PERIODS, rebase, rollingReturns, rollingStats,
  coverage,
  spanReturn,
  trailingReturn,
  type CurvePoint,
} from '../fundCategoryCurve'

// REAL composite output for "India Fund Sector - Energy" over 2026-03-30 → 2026-04-07,
// produced by the chain-link SQL in lib/queries/fund_category_curve.ts against
// atlas_foundation on 2026-08-05. NO synthetic inputs (rule #0).
// This window is chosen because it exercises the NAV gaps the composite has to survive:
//   • 2026-03-31 — SBI Energy (F00001JAQ0) has no 03-30 NAV, so no return that day
//   • 2026-04-01 — only ICICI and Kotak report; Baroda and SBI skip to 04-02, and their
//     two-day moves land whole on 04-02 rather than being counted twice
const ENERGY: CurvePoint[] = [
  { d: '2026-03-30', v: 100.000000 },
  { d: '2026-03-31', v: 99.994732 },
  { d: '2026-04-01', v: 100.779574 },
  { d: '2026-04-02', v: 101.390296 },
  { d: '2026-04-06', v: 101.442800 },
  { d: '2026-04-07', v: 101.718849 },
]

describe('rebase', () => {
  it('sets the first point to exactly 100 and scales the rest proportionally', () => {
    const raw: CurvePoint[] = [
      { d: '2026-03-30', v: 45538.65 }, // real NIFTY FMCG close 2026-03-30
      { d: '2026-04-30', v: 51072.10 }, // real NIFTY FMCG close 2026-04-30
      { d: '2026-07-31', v: 49642.05 }, // real NIFTY FMCG close 2026-07-31
    ]
    const out = rebase(raw)
    expect(out[0]).toEqual({ d: '2026-03-30', v: 100 })
    expect(out[1].v).toBeCloseTo(112.151107, 4) // 100 * 51072.10 / 45538.65
    expect(out[2].v).toBeCloseTo(109.010807, 4) // 100 * 49642.05 / 45538.65
  })

  it('leaves a series already anchored at 100 unchanged', () => {
    const out = rebase(ENERGY)
    expect(out.map((p) => p.d)).toEqual(ENERGY.map((p) => p.d))
    // Element-wise, not toEqual: 100 * 99.994732 / 100 need not be bit-identical.
    out.forEach((p, i) => expect(p.v).toBeCloseTo(ENERGY[i].v, 9))
  })

  it('returns an empty array for an empty series', () => {
    expect(rebase([])).toEqual([])
  })

  it('returns an empty array when the first value is zero or negative', () => {
    expect(rebase([{ d: '2026-01-01', v: 0 }, { d: '2026-01-02', v: 5 }])).toEqual([])
  })
})

// REAL month-end NAVs for ICICI Pru FMCG Gr (mstar F0GBR06S3I), 2023-06-30 → 2026-07-31,
// pulled from atlas_foundation.de_mf_nav_daily on 2026-08-04. NO synthetic inputs (rule #0).
// This fund IS the whole "India Fund Sector - FMCG" category (1 of 1 with NAV), so its
// rebased NAV series is by definition that category's composite — which is exactly what
// the single-fund identity test in the integration suite asserts. The window is a real
// losing stretch (-4.8% over three years), so it exercises negative returns and CAGR.
const FMCG: CurvePoint[] = [
  { d: '2023-06-30', v: 438.57 }, { d: '2023-07-31', v: 449.35 }, { d: '2023-08-31', v: 440.41 },
  { d: '2023-09-29', v: 442.95 }, { d: '2023-10-31', v: 438.29 }, { d: '2023-11-30', v: 450.01 },
  { d: '2023-12-29', v: 472.96 }, { d: '2024-01-31', v: 456.96 }, { d: '2024-02-29', v: 449.04 },
  { d: '2024-03-31', v: 452.09 }, { d: '2024-04-30', v: 454.98 }, { d: '2024-05-31', v: 459.65 },
  { d: '2024-06-28', v: 481.94 }, { d: '2024-07-31', v: 520.97 }, { d: '2024-08-30', v: 531.92 },
  { d: '2024-09-30', v: 548.94 }, { d: '2024-10-31', v: 500.94 }, { d: '2024-11-29', v: 488.55 },
  { d: '2024-12-31', v: 476.21 }, { d: '2025-01-31', v: 480.25 }, { d: '2025-02-28', v: 437.20 },
  { d: '2025-03-31', v: 454.31 }, { d: '2025-04-30', v: 475.89 }, { d: '2025-05-30', v: 476.58 },
  { d: '2025-06-30', v: 477.95 }, { d: '2025-07-31', v: 480.09 }, { d: '2025-08-29', v: 484.34 },
  { d: '2025-09-30', v: 472.46 }, { d: '2025-10-31', v: 482.81 }, { d: '2025-11-28', v: 475.52 },
  { d: '2025-12-31', v: 471.16 }, { d: '2026-01-30', v: 437.43 }, { d: '2026-02-27', v: 439.49 },
  { d: '2026-03-31', v: 389.87 }, { d: '2026-04-30', v: 429.93 }, { d: '2026-05-29', v: 416.72 },
  { d: '2026-06-30', v: 413.55 }, { d: '2026-07-31', v: 417.52 },
]

describe('spanReturn', () => {
  it('annualises a span longer than a year on actual day count', () => {
    const r = spanReturn(FMCG)!
    expect(r.days).toBe(1127)          // 2023-06-30 → 2026-07-31
    expect(r.annualised).toBe(true)
    expect(r.pct).toBeCloseTo(-1.581500, 4)  // (417.52/438.57)^(365.25/1127) - 1
  })

  it('returns absolute return for a span of a year or less', () => {
    const r = spanReturn(FMCG.slice(-13))! // 2025-07-31 → 2026-07-31, 365 days
    expect(r.days).toBe(365)
    expect(r.annualised).toBe(false)
    expect(r.pct).toBeCloseTo(-13.032973, 4) // 417.52/480.09 - 1
  })

  it('returns null for a series with fewer than two points', () => {
    expect(spanReturn([])).toBeNull()
    expect(spanReturn([{ d: '2026-07-31', v: 417.52 }])).toBeNull()
  })
})

describe('trailingReturn', () => {
  // Each expectation below is the real answer for this real series. The anchor is the last
  // date minus N calendar months; the start point is the last observation on or before it.
  it.each([
    [1,  31,   false, 0.959981],
    [3,  92,   false, -2.886516],
    [6,  182,  false, -4.551585],   // anchor 2026-01-31 falls on a non-NAV day -> uses 2026-01-30
    [12, 365,  false, -13.032973],
    [24, 730,  true,  -10.484269],
    [36, 1096, true,  -2.418699],
  ])('%i-month trailing return spans %i days, annualised=%s', (months, days, ann, pct) => {
    const r = trailingReturn(FMCG, months)!
    expect(r.days).toBe(days)
    expect(r.annualised).toBe(ann)
    expect(r.pct).toBeCloseTo(pct, 4)
  })

  it('returns null when the series is shorter than the requested period', () => {
    // 60 months back from 2026-07-31 is 2021-07-31; the series starts 2023-06-30.
    expect(trailingReturn(FMCG, 60)).toBeNull()
  })

  it('never reports 0 for a period it cannot cover', () => {
    const r = trailingReturn(FMCG, 60)
    expect(r).toBeNull()
    expect(r).not.toEqual({ pct: 0, annualised: false, days: 0 })
  })
})

describe('PERIODS', () => {
  it('lists the seven trailing periods the returns table renders', () => {
    expect(PERIODS.map((p) => p.key)).toEqual(['1m', '3m', '6m', '1y', '2y', '3y', '5y'])
    expect(PERIODS.map((p) => p.months)).toEqual([1, 3, 6, 12, 24, 36, 60])
  })
})

describe('rollingReturns', () => {
  it('produces one window per date that has an observation a full year earlier', () => {
    const roll = rollingReturns(FMCG, 1)
    // 38 month-ends; the first 13 have no point a calendar year back, leaving 25 windows.
    expect(roll).toHaveLength(25)
    expect(roll[0].d).toBe('2024-07-31')
    expect(roll[0].v).toBeCloseTo(15.938578, 4)  // 520.97/449.35 - 1, vs 2023-07-31
    expect(roll.at(-1)!.d).toBe('2026-07-31')
    expect(roll.at(-1)!.v).toBeCloseTo(-13.032973, 4) // 417.52/480.09 - 1, vs 2025-07-31
  })

  it('agrees with trailingReturn on the final window', () => {
    expect(rollingReturns(FMCG, 1).at(-1)!.v).toBeCloseTo(trailingReturn(FMCG, 12)!.pct, 6)
  })

  it('returns an empty array when the series is shorter than the window', () => {
    expect(rollingReturns(FMCG.slice(-6), 1)).toEqual([])
  })

  it('anchors on calendar months, never shortening the window', () => {
    // 2025-02-28 minus 12 months is 2024-02-28, but the only nearby observation is
    // 2024-02-29, which is *after* the anchor. Falling back to 2024-01-31 gives a 13-month
    // window rather than an 11-month one. Erring long is deliberate: a window shorter than
    // the one requested would understate the return and quietly mislabel it.
    const w = rollingReturns(FMCG, 1).find((p) => p.d === '2025-02-28')!
    expect(w.v).toBeCloseTo(-4.324230, 4) // 437.20/456.96 - 1, vs 2024-01-31
  })
})

describe('rollingStats', () => {
  it('summarises the distribution of a real rolling-1Y series', () => {
    const s = rollingStats(rollingReturns(FMCG, 1), [])!
    expect(s.n).toBe(25)
    expect(s.min).toBeCloseTo(-14.184147, 4)
    expect(s.p25).toBeCloseTo(-8.487246, 4)
    expect(s.median).toBeCloseTo(-3.619196, 4)
    expect(s.p75).toBeCloseTo(4.747461, 4)
    expect(s.max).toBeCloseTo(23.928209, 4)
  })

  it('reports beatRate as null when there is no benchmark to compare against', () => {
    expect(rollingStats(rollingReturns(FMCG, 1), [])!.beatRate).toBeNull()
  })

  it('counts the share of dates where the composite beat the benchmark', () => {
    const comp = rollingReturns(FMCG, 1)
    // A series never beats itself; a series one point better beats a weaker one everywhere.
    expect(rollingStats(comp, comp)!.beatRate).toBe(0)
    const worse = comp.map((p) => ({ d: p.d, v: p.v - 1 }))
    expect(rollingStats(comp, worse)!.beatRate).toBe(100)
  })

  it('returns null for an empty series', () => {
    expect(rollingStats([], [])).toBeNull()
  })
})

describe('minusMonths', () => {
  it('subtracts whole calendar months', () => {
    expect(minusMonths('2026-07-31', 1)).toBe('2026-06-30') // June has 30 days
    expect(minusMonths('2026-07-31', 12)).toBe('2025-07-31')
    expect(minusMonths('2026-07-31', 60)).toBe('2021-07-31')
  })

  it('clamps into a shorter target month rather than overflowing', () => {
    expect(minusMonths('2025-03-31', 1)).toBe('2025-02-28')
    expect(minusMonths('2024-03-31', 1)).toBe('2024-02-29') // leap year
  })

  it('rolls back across year boundaries', () => {
    expect(minusMonths('2026-01-30', 3)).toBe('2025-10-30')
    expect(minusMonths('2026-01-30', 13)).toBe('2024-12-30')
  })
})

describe('coverage', () => {
  // REAL per-date ALIVE-fund counts (the composite's divisor), from atlas_foundation
  // on 2026-08-05. NO synthetic inputs (rule #0).

  it('reports the widest the composite ever ran, ignoring the anchor row', () => {
    // "India Fund Sector - Healthcare", 2026-01-29 → 2026-02-05. 2026-01-31 is a Saturday
    // where only 2 of 19 funds publish a NAV — but all 19 are alive and in the divisor, so
    // coverage is flat at 19. Under the old reporter-count divisor this read as a dip to 2.
    const healthcare = [{ n: 0 }, { n: 19 }, { n: 19 }, { n: 19 }, { n: 19 }, { n: 19 }, { n: 19 }]
    expect(coverage(healthcare)).toEqual({ first: 19, peak: 19 })
  })

  it('shows a category taking in a new fund as a range, not a jump', () => {
    // "India Fund Sector - Energy", 2025-04-28 → 2025-05-07: Kotak Energy Opportunities
    // starts reporting on 2025-05-02 and joins the divisor on 2025-05-05.
    expect(coverage([{ n: 0 }, { n: 3 }, { n: 3 }, { n: 3 }, { n: 4 }, { n: 4 }, { n: 4 }]))
      .toEqual({ first: 3, peak: 4 })
  })

  it('reports zeroes for an empty series', () => {
    expect(coverage([])).toEqual({ first: 0, peak: 0 })
  })
})

describe('fetchStart', () => {
  it('reaches back a full rolling window before the displayed period', () => {
    expect(fetchStart('2023-08-03', 3)).toBe('2020-08-03')
    expect(fetchStart('2024-07-31', 1)).toBe('2023-07-31')
  })

  it('gives every displayed date a rolling window, which the display range alone does not', () => {
    // The shipped bug: /funds/compare queried only the displayed period, so a rolling window
    // as long as that period left almost nothing to plot. Real FMCG month-ends, displaying
    // 2024-07-31 onward (25 dates) with a 1-year rolling window.
    const displayFrom = '2024-07-31'
    const displayed = FMCG.filter((p) => p.d >= displayFrom)
    expect(displayed).toHaveLength(25)

    // Querying only what is displayed loses the first year of it.
    expect(rollingReturns(displayed, 1)).toHaveLength(13)

    // Reaching back one window covers every displayed date.
    const extended = FMCG.filter((p) => p.d >= fetchStart(displayFrom, 1))
    const covered = rollingReturns(extended, 1).filter((p) => p.d >= displayFrom)
    expect(covered).toHaveLength(25)
  })

  it('leaves a one-point series where the window equals the whole period', () => {
    // Why the default (3-year period, 3-year window) drew a blank chart: one point is not a line.
    expect(rollingReturns(FMCG, 3).length).toBeLessThanOrEqual(2)
  })
})

describe('growthReturn', () => {
  // The summary table gets growth FACTORS from SQL (exp of summed log-returns) rather than a
  // series, so it needs the same CAGR gate applied to a factor plus a known span.
  it('annualises a multi-year growth factor on actual day count', () => {
    // Real: FMCG composite grew 1.408537x over 2021-08-03 -> 2026-08-03 (1826 days).
    const r = growthReturn(1.408537, 1826)!
    expect(r.annualised).toBe(true)
    expect(r.days).toBe(1826)
    expect(r.pct).toBeCloseTo(7.092172, 4)
  })

  it('annualises a loss correctly', () => {
    // Real: FMCG composite over 3 years (1096 days) shrank to 0.954303x.
    expect(growthReturn(0.954303, 1096)!.pct).toBeCloseTo(-1.546693, 4)
  })

  it('reports a one-year span as an absolute return, not a CAGR', () => {
    const r = growthReturn(0.877336, 365)!
    expect(r.annualised).toBe(false)
    expect(r.pct).toBeCloseTo(-12.2664, 3)
  })

  it('returns null for a period the data does not cover', () => {
    // Sector - Energy has no NAV before 2024-03-04, so its 3Y and 5Y cells must read "—".
    expect(growthReturn(null, 1826)).toBeNull()
  })

  it('returns null for a non-positive or unusable growth factor', () => {
    expect(growthReturn(0, 365)).toBeNull()
    expect(growthReturn(1.5, 0)).toBeNull()
  })
})
