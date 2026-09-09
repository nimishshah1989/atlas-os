// src/lib/series.ts — the chart window, the rebasing and the return calculator, on a REAL dated
// series with REAL gaps.
//
// RULE #0, AND THE SAME BARGAIN basketMetrics.test.ts STRUCK. This container cannot reach a US
// price feed (Alpaca needs a key that must never be in the repo; Stooq is CAPTCHA-gated, which is
// why plan.md calls its bulk files a manual download), so there is no bar fixture to assert on and
// none is invented. What this file uses instead is the one real dated observation series the
// repository holds verbatim: FRED's DTB3, the 3-month Treasury bill yield
// (tests/fixtures/global/macro/DTB3.csv, 2016-01-04 → 2026-09-02).
//
// A YIELD IS NOT A PRICE, and no assertion below pretends otherwise: nothing here claims an
// instrument returned anything. What is asserted is the machinery — WHICH observation a date
// resolves to, what happens at a gap, that the window is the last N entries, that rebasing puts
// both series at 100 on the same day, and that a missing value comes back null rather than zero.
// That machinery cannot tell a yield from a close, and DTB3 brings the one property a made-up
// series would not: real holes on every US market holiday, which is exactly what
// `sessionAtOrBefore` exists for.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_RANGE,
  emaStack,
  lastSessions,
  periodReturn,
  RANGES,
  rebase,
  sessionAtOrBefore,
  type Bar,
} from '@/lib/series'

const CSV = resolve(__dirname, '../../../../tests/fixtures/global/macro/DTB3.csv')

/** The real observations, oldest first, as bars. Both bases carry the SAME observation: the file
 *  has one series, and putting a different one in the other column would be the invention this
 *  file exists not to make. The one place the two must differ is tested with an explicit null. */
function observations(): Bar[] {
  return readFileSync(CSV, 'utf8')
    .trim()
    .split('\n')
    .slice(1)
    .map((line) => line.split(','))
    .filter(([, v]) => v !== '' && v !== undefined && Number(v) > 0)
    .map(([date, v]) => ({ date, close_adj: v, close_tr: v }))
}

const ROWS = observations()

describe('the fixture is the real file', () => {
  it('is a long ascending run of dated observations', () => {
    expect(ROWS.length).toBeGreaterThan(2000)
    expect(ROWS[0].date < ROWS[ROWS.length - 1].date).toBe(true)
    expect(ROWS.every((r, i) => i === 0 || ROWS[i - 1].date < r.date)).toBe(true)
  })
})

describe('sessionAtOrBefore lands on a real observation, never between two', () => {
  it('finds the exact day when there is one', () => {
    const mid = ROWS[Math.floor(ROWS.length / 2)]
    expect(sessionAtOrBefore(ROWS, mid.date)?.date).toBe(mid.date)
  })

  it('falls BACK across a real gap rather than forward or through it', () => {
    // Find a genuine hole in the file: consecutive observations more than one day apart. The
    // day inside it must resolve to the day BEFORE — resolving forward would answer a question
    // with data that did not exist when it was asked.
    const i = ROWS.findIndex((r, k) => k > 0 && Date.parse(r.date) - Date.parse(ROWS[k - 1].date) > 86400000 * 1.5)
    expect(i).toBeGreaterThan(0)
    const before = ROWS[i - 1]
    const inside = new Date(Date.parse(before.date) + 86400000).toISOString().slice(0, 10)
    expect(inside < ROWS[i].date).toBe(true) // the day really is inside the hole
    expect(sessionAtOrBefore(ROWS, inside)?.date).toBe(before.date)
  })

  it('has nothing to return before the series begins', () => {
    expect(sessionAtOrBefore(ROWS, '1999-01-01')).toBeNull()
  })

  it('returns the last observation for any date after the series ends', () => {
    expect(sessionAtOrBefore(ROWS, '2099-01-01')?.date).toBe(ROWS[ROWS.length - 1].date)
  })
})

describe('the chart window is the last N entries', () => {
  it('takes exactly N, ending at the newest', () => {
    const w = lastSessions(ROWS, 126)
    expect(w).toHaveLength(126)
    expect(w[w.length - 1].date).toBe(ROWS[ROWS.length - 1].date)
  })

  it('gives the whole series when it is shorter than the window, rather than padding it', () => {
    // A fund listed last March has a real one-year chart; it is simply shorter than a year, and
    // padding it to 252 points would draw history it never had.
    const short = ROWS.slice(0, 20)
    expect(lastSessions(short, 252)).toHaveLength(20)
    expect(lastSessions(ROWS, Number.POSITIVE_INFINITY)).toHaveLength(ROWS.length)
  })

  it('offers ranges in ascending order with a default that exists', () => {
    const sessions = RANGES.map((r) => r.sessions)
    expect(sessions).toEqual([...sessions].sort((a, b) => a - b))
    expect(RANGES.some((r) => r.key === DEFAULT_RANGE)).toBe(true)
  })
})

describe('rebase indexes to 100 at the window, and drops what it cannot index', () => {
  it('starts at 100 and keeps the shape', () => {
    const w = lastSessions(ROWS, 60)
    const r = rebase(w.map((p) => ({ date: p.date, value: p.close_tr })))
    expect(r).toHaveLength(60)
    expect(r[0].value).toBe(100)
    // The ratio of any two rebased points is the ratio of the two observations — the shape is not
    // altered by indexing, which is the only reason the picture is comparable at all.
    const k = 40
    expect(r[k].value / r[0].value).toBeCloseTo(Number(w[k].close_tr) / Number(w[0].close_tr), 12)
  })

  it('skips leading nulls instead of carrying them at 100', () => {
    const w = lastSessions(ROWS, 10).map((p) => ({ date: p.date, value: p.close_tr }))
    const withHole = [{ date: '2016-01-01', value: null }, ...w]
    const r = rebase(withHole)
    expect(r).toHaveLength(10)
    expect(r[0].date).toBe(w[0].date) // the null day is absent, not drawn flat at 100
  })

  it('has nothing to draw from an empty window', () => {
    expect(rebase([])).toEqual([])
  })
})

describe('periodReturn answers on the sessions that exist, or not at all', () => {
  const bench = ROWS.map((r) => ({ date: r.date, close_tr: r.close_tr }))

  it('reports WHICH two observations it used, not the dates asked for', () => {
    const from = ROWS[100].date
    const to = ROWS[400].date
    // A Sunday-shaped ask: a day inside a real gap resolves back, and the answer says so.
    const asked = new Date(Date.parse(to) + 86400000).toISOString().slice(0, 10)
    const a = periodReturn(ROWS, bench, from, asked)
    expect(a).not.toBeNull()
    expect(a?.from).toBe(from)
    expect([to, asked]).toContain(a?.to)
    expect(a?.to).toBe(sessionAtOrBefore(ROWS, asked)?.date)
  })

  it('computes growth between the two observations it named', () => {
    const a = periodReturn(ROWS, bench, ROWS[100].date, ROWS[400].date)
    const expected = Number(ROWS[400].close_tr) / Number(ROWS[100].close_tr) - 1
    expect(a?.total).toBeCloseTo(expected, 12)
    expect(a?.price).toBeCloseTo(expected, 12)
  })

  it('states the benchmark comparison in the RELATIVE form, not as a subtraction', () => {
    // ADR-0002. Over long windows (1+r)/(1+b)−1 and r−b are materially different numbers, and the
    // RS columns are the first form; the calculator must not quietly be the second.
    const a = periodReturn(ROWS, bench, ROWS[100].date, ROWS[900].date)
    expect(a?.relative).toBeCloseTo((1 + (a?.total ?? 0)) / (1 + (a?.benchmark ?? 0)) - 1, 12)
    // Against ITSELF the relative result is exactly zero, whatever the absolute return was.
    expect(a?.relative).toBeCloseTo(0, 12)
    expect(Math.abs(a?.total ?? 0)).toBeGreaterThan(0.01) // and the absolute return was not zero
  })

  it('is null — never zero — when the window has no two observations in it', () => {
    expect(periodReturn(ROWS, bench, '1999-01-01', '1999-06-01')).toBeNull()
    expect(periodReturn(ROWS, bench, ROWS[10].date, ROWS[10].date)).toBeNull()
    expect(periodReturn(ROWS, bench, ROWS[400].date, ROWS[100].date)).toBeNull() // backwards
    expect(periodReturn([], bench, ROWS[10].date, ROWS[400].date)).toBeNull()
  })

  it('answers on total return even where the price basis is missing, and says nothing extra', () => {
    // The real asymmetry on the board: close_tr present, close_adj not. `total` must survive and
    // `price` must be null, rather than the whole answer collapsing or price silently echoing it.
    const stripped: Bar[] = ROWS.map((r) => ({ ...r, close_adj: null }))
    const a = periodReturn(stripped, bench, ROWS[100].date, ROWS[400].date)
    expect(a?.total).not.toBeNull()
    expect(a?.price).toBeNull()
  })

  it('has no benchmark comparison when the benchmark does not cover the window', () => {
    const a = periodReturn(ROWS, [], ROWS[100].date, ROWS[400].date)
    expect(a?.total).not.toBeNull()
    expect(a?.benchmark).toBeNull()
    expect(a?.relative).toBeNull()
  })
})

describe('emaStack names the shape, and refuses to name one it cannot see', () => {
  it('reads three real observations in each order', () => {
    // Three observations from the file, used as three numbers: the function compares magnitudes.
    const [lo, mid, hi] = [ROWS[0].close_tr, ROWS[1].close_tr, ROWS[2].close_tr]
      .map(Number)
      .sort((a, b) => a - b)
      .map(String)
    expect(emaStack(hi, mid, lo)?.tone).toBe('pos')
    expect(emaStack(lo, mid, hi)?.tone).toBe('neg')
    expect(emaStack(mid, hi, lo)?.tone).toBe('neutral')
  })

  it('is null when any average is missing — a young fund is not in a downtrend', () => {
    expect(emaStack('10', '9', null)).toBeNull()
    expect(emaStack(null, null, null)).toBeNull()
  })
})
