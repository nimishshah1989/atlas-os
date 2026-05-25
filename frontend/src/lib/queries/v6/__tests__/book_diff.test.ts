// frontend/src/lib/queries/v6/__tests__/book_diff.test.ts
//
// 4 required cases + 3 additional guards for getBookDiff().

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return { ...actual, cache: (fn: (...args: unknown[]) => unknown) => fn }
})

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

const getHeldIidSetMock = vi.fn<() => Promise<Set<string>>>()
vi.mock('../portfolio_holdings', () => ({
  getHeldIidSet: () => getHeldIidSetMock(),
}))

import { getBookDiff } from '../book_diff'
import type { StockFlip } from '../book_diff'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const IID_A = 'aaaa0000-0000-0000-0000-000000000001'
const IID_B = 'bbbb0000-0000-0000-0000-000000000002'
const IID_C = 'cccc0000-0000-0000-0000-000000000003'
const TODAY = '2026-05-26'
const YESTERDAY = '2026-05-23'

function flipRow(
  iid: string,
  ticker: string | null,
  yesterday: string | null,
  today: string | null,
) {
  return { instrument_id: iid, ticker, yesterday_action: yesterday, today_action: today, date_changed: TODAY }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('getBookDiff', () => {
  beforeEach(() => {
    sqlMock.mockReset()
    getHeldIidSetMock.mockReset()
  })

  // Case 1: Some flipped — 2 of 5 held iids changed verdict overnight
  it('returns 2 flipped rows when 2 of 5 held iids changed verdict overnight', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(
      new Set([IID_A, IID_B, IID_C, 'iid-d', 'iid-e']),
    )
    sqlMock
      .mockResolvedValueOnce([{ d: TODAY, d_prev: YESTERDAY }])
      .mockResolvedValueOnce([
        flipRow(IID_A, 'RELIANCE', 'NEUTRAL', 'POSITIVE'),
        flipRow(IID_B, 'TCS', 'POSITIVE', 'NEGATIVE'),
      ])
      .mockResolvedValueOnce([])

    const result = await getBookDiff()

    expect(result.held_iids_flipped).toHaveLength(2)
    expect(result.held_drift_warns).toHaveLength(0)

    const a = result.held_iids_flipped.find((f) => f.instrument_id === IID_A)!
    expect(a.ticker).toBe('RELIANCE')
    expect(a.yesterday_action).toBe('NEUTRAL')
    expect(a.today_action).toBe('POSITIVE')
    expect(a.date_changed).toBe(TODAY)

    const b = result.held_iids_flipped.find((f) => f.instrument_id === IID_B)!
    expect(b.yesterday_action).toBe('POSITIVE')
    expect(b.today_action).toBe('NEGATIVE')

    expect(sqlMock).toHaveBeenCalledTimes(3)
  })

  // Case 2: None flipped — all verdicts unchanged
  it('returns empty arrays when no held iids changed verdict', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(new Set([IID_A, IID_B, IID_C]))
    sqlMock
      .mockResolvedValueOnce([{ d: TODAY, d_prev: YESTERDAY }])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])

    const result = await getBookDiff()

    expect(result.held_iids_flipped).toHaveLength(0)
    expect(result.held_drift_warns).toHaveLength(0)
    expect(Array.isArray(result.held_iids_flipped)).toBe(true)
    expect(Array.isArray(result.held_drift_warns)).toBe(true)
    expect(result.held_iids_flipped).not.toBeNull()
    expect(result.held_drift_warns).not.toBeNull()
    expect(sqlMock).toHaveBeenCalledTimes(3)
  })

  // Case 3: No book — empty set → both arrays [], zero SQL calls
  it('returns both arrays empty with no DB queries when book is empty', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(new Set<string>())

    const result = await getBookDiff()

    expect(result.held_iids_flipped).toEqual([])
    expect(result.held_drift_warns).toEqual([])
    expect(Array.isArray(result.held_iids_flipped)).toBe(true)
    expect(sqlMock).not.toHaveBeenCalled()
  })

  // Case 4: Drift warn join — held iid cell flipped to drift_warn
  it('returns drift-warn row when held iid cell flipped to drift_warn', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(new Set([IID_A, IID_B]))
    sqlMock
      .mockResolvedValueOnce([{ d: TODAY, d_prev: YESTERDAY }])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { instrument_id: IID_A, ticker: 'RELIANCE', today_action: 'POSITIVE', date_changed: TODAY },
      ])

    const result = await getBookDiff()

    expect(result.held_iids_flipped).toHaveLength(0)
    expect(result.held_drift_warns).toHaveLength(1)

    const row = result.held_drift_warns[0]
    expect(row.instrument_id).toBe(IID_A)
    expect(row.ticker).toBe('RELIANCE')
    expect(row.today_action).toBe('POSITIVE')
    expect(row.yesterday_action).toBeNull()
    expect(row.date_changed).toBe(TODAY)
    expect(sqlMock).toHaveBeenCalledTimes(3)
  })

  // Additional: first snapshot → yesterday_action=null on all rows
  it('first snapshot: held iids appear with yesterday_action=null when no D-1 exists', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(new Set([IID_A, IID_B]))
    sqlMock
      .mockResolvedValueOnce([{ d: TODAY, d_prev: null }])
      .mockResolvedValueOnce([
        flipRow(IID_A, 'RELIANCE', null, 'POSITIVE'),
        flipRow(IID_B, 'TCS', null, 'NEUTRAL'),
      ])
      .mockResolvedValueOnce([])

    const result = await getBookDiff()

    expect(result.held_iids_flipped).toHaveLength(2)
    for (const flip of result.held_iids_flipped) {
      expect(flip.yesterday_action).toBeNull()
    }
    expect(sqlMock).toHaveBeenCalledTimes(3)
  })

  // Additional: empty conviction table (d=null) → early return
  it('returns empty diff when atlas_conviction_daily is empty', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(new Set([IID_A]))
    sqlMock.mockResolvedValueOnce([{ d: null, d_prev: null }])

    const result = await getBookDiff()

    expect(result.held_iids_flipped).toEqual([])
    expect(result.held_drift_warns).toEqual([])
    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  // Additional: null ticker falls back to instrument_id
  it('falls back to instrument_id when ticker is null', async () => {
    getHeldIidSetMock.mockResolvedValueOnce(new Set([IID_A]))
    sqlMock
      .mockResolvedValueOnce([{ d: TODAY, d_prev: YESTERDAY }])
      .mockResolvedValueOnce([flipRow(IID_A, null, 'NEUTRAL', 'POSITIVE')])
      .mockResolvedValueOnce([])

    const result = await getBookDiff()

    expect(result.held_iids_flipped[0].ticker).toBe(IID_A)
  })
})

// Type-level checks
describe('StockFlip type contract', () => {
  it('StockFlip accepts 3-state enum values', () => {
    const flip: StockFlip = {
      instrument_id: IID_A,
      ticker: 'RELIANCE',
      yesterday_action: 'NEUTRAL',
      today_action: 'POSITIVE',
      date_changed: TODAY,
    }
    expect(flip.yesterday_action).toBe('NEUTRAL')
  })

  it('StockFlip allows null action fields', () => {
    const flip: StockFlip = {
      instrument_id: IID_A,
      ticker: 'RELIANCE',
      yesterday_action: null,
      today_action: null,
      date_changed: TODAY,
    }
    expect(flip.yesterday_action).toBeNull()
  })
})
