// computeWindowMetrics, ported verbatim from India's portfolioMetrics — on a REAL series.
//
// Rule #0: no invented NAV. The series is FRED's DTB3 (3-month T-bill yield, percent p.a.), the
// one dated observation series this repository holds verbatim (tests/fixtures/global/macro/
// DTB3.csv, 2016-01-04 → 2026-09-02). A yield is not a NAV, and the metrics of "a series that
// walks like DTB3" mean nothing financially — but the FUNCTION does not know that: what is
// asserted is its arithmetic on real dated points (a CAGR that reproduces the endpoints, a
// drawdown found by hand, the 95 percent coverage rule), never a portfolio's performance.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { computeWindowMetrics, maxDrawdown, type SeriesPoint } from '@/lib/basketMetrics'

const CSV = resolve(__dirname, '../../../../tests/fixtures/global/macro/DTB3.csv')

function dtb3(): SeriesPoint[] {
  return readFileSync(CSV, 'utf8')
    .trim()
    .split('\n')
    .slice(1)
    .map((line) => line.split(','))
    .filter(([, v]) => v !== '' && v !== undefined)
    .map(([d, v]) => ({ d, nav: Number(v) }))
    .filter((p) => p.nav > 0) // the zero-rate era is not a level a ratio can start from
}

const DAY = 86400000

describe('computeWindowMetrics on the real DTB3 observations', () => {
  const points = dtb3()

  it('reads the fixture as dated points, oldest first', () => {
    expect(points.length).toBeGreaterThan(2000)
    expect(points[0].d < points[points.length - 1].d).toBe(true)
  })

  it('annualises the last window from its own endpoints', () => {
    const w = computeWindowMetrics(points, 1)
    expect(w.cagr).not.toBeNull()
    // the window is the points within 365.25 days of the end; its CAGR is (last/first)^(365.25/span) − 1
    const endMs = new Date(points[points.length - 1].d).getTime()
    const win = points.filter((p) => endMs - new Date(p.d).getTime() <= 365.25 * DAY)
    const spanDays = (endMs - new Date(win[0].d).getTime()) / DAY
    const expected = Math.pow(win[win.length - 1].nav / win[0].nav, 365.25 / spanDays) - 1
    expect(w.cagr).toBeCloseTo(expected, 12)
  })

  it('finds the worst peak-to-trough fall inside the window, and Calmar from it', () => {
    const w = computeWindowMetrics(points, 5)
    expect(w.maxDd).not.toBeNull()
    expect(w.maxDd!).toBeLessThanOrEqual(0)
    expect(w.maxDd!).toBeGreaterThanOrEqual(-1)
    if (w.maxDd! < 0) expect(w.calmar).toBeCloseTo(w.cagr! / Math.abs(w.maxDd!), 12)
    else expect(w.calmar).toBeNull()
  })

  it('answers null for every cell when the record is shorter than 95 percent of the window', () => {
    const lastYear = points.filter((p) => new Date(points[points.length - 1].d).getTime() - new Date(p.d).getTime() <= 200 * DAY)
    expect(computeWindowMetrics(lastYear, 1)).toEqual({ cagr: null, maxDd: null, calmar: null })
    expect(computeWindowMetrics(points.slice(-1), 1)).toEqual({ cagr: null, maxDd: null, calmar: null })
    expect(computeWindowMetrics([], 3)).toEqual({ cagr: null, maxDd: null, calmar: null })
  })

  it('the since-inception drawdown never exceeds any window drawdown', () => {
    const all = maxDrawdown(points)!
    for (const years of [1, 3, 5]) {
      const w = computeWindowMetrics(points, years)
      if (w.maxDd != null) expect(all).toBeLessThanOrEqual(w.maxDd)
    }
    expect(maxDrawdown(points.slice(0, 1))).toBeNull()
  })
})
