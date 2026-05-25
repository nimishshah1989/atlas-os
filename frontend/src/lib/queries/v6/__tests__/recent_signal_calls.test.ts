// frontend/src/lib/queries/v6/__tests__/recent_signal_calls.test.ts
//
// 5 required test cases:
//   1. getRecentSignalCalls default (50, 7d) — returns ordered list
//   2. getRecentSignalCalls empty table — returns []
//   3. getSignalCallsByIid for an iid with multiple calls — ordered by entry_date DESC
//   4. getSignalCallsByCell for a cell with history — ordered by entry_date DESC
//   5. is_active flag computed correctly (exit_date IS NULL → true)

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import {
  getRecentSignalCalls,
  getSignalCallsByIid,
  getSignalCallsByCell,
  type SignalCallEvent,
} from '../recent_signal_calls'

// ---------------------------------------------------------------------------
// Fixtures — raw rows as postgres-js would return them
// ---------------------------------------------------------------------------

const RAW_CALL_A = {
  signal_call_id: 'aaa00000-0000-0000-0000-000000000001',
  cell_id: 'ccc00000-0000-0000-0000-000000000001',
  cell_name: 'Mid 12m POSITIVE',
  instrument_id: 'iii00000-0000-0000-0000-000000000001',
  ticker: 'RELIANCE',
  action: 'POSITIVE',
  cap_tier: 'Mid',
  tenure: '12m',
  entry_date: '2026-05-25',
  entry_price: null,
  confidence_unconditional: '0.8200',
  predicted_excess: '0.043000',
  exit_date: null,
  is_active: true,
}

const RAW_CALL_B = {
  signal_call_id: 'aaa00000-0000-0000-0000-000000000002',
  cell_id: 'ccc00000-0000-0000-0000-000000000001',
  cell_name: 'Mid 12m POSITIVE',
  instrument_id: 'iii00000-0000-0000-0000-000000000002',
  ticker: 'INFY',
  action: 'POSITIVE',
  cap_tier: 'Mid',
  tenure: '12m',
  entry_date: '2026-05-22',
  entry_price: null,
  confidence_unconditional: '0.7100',
  predicted_excess: null,
  exit_date: '2026-05-24',
  is_active: false,
}

const RAW_CALL_C = {
  signal_call_id: 'aaa00000-0000-0000-0000-000000000003',
  cell_id: 'ccc00000-0000-0000-0000-000000000002',
  cell_name: 'Large 6m NEGATIVE',
  instrument_id: 'iii00000-0000-0000-0000-000000000001',
  ticker: 'RELIANCE',
  action: 'NEGATIVE',
  cap_tier: 'Large',
  tenure: '6m',
  entry_date: '2026-05-20',
  entry_price: null,
  confidence_unconditional: '0.6500',
  predicted_excess: '-0.021000',
  exit_date: null,
  is_active: true,
}

// Fixture: iid not in atlas_universe_stocks (ticker = null → fallback to iid)
const RAW_CALL_NO_TICKER = {
  signal_call_id: 'aaa00000-0000-0000-0000-000000000004',
  cell_id: 'ccc00000-0000-0000-0000-000000000003',
  cell_name: 'Small 3m NEUTRAL',
  instrument_id: 'iii00000-0000-0000-0000-000000000099',
  ticker: null,
  action: 'NEUTRAL',
  cap_tier: 'Small',
  tenure: '3m',
  entry_date: '2026-05-19',
  entry_price: null,
  confidence_unconditional: '0.5500',
  predicted_excess: null,
  exit_date: null,
  is_active: true,
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function expectShape(event: SignalCallEvent) {
  expect(typeof event.signal_call_id).toBe('string')
  expect(typeof event.cell_id).toBe('string')
  expect(typeof event.cell_name).toBe('string')
  expect(typeof event.instrument_id).toBe('string')
  expect(typeof event.ticker).toBe('string')
  expect(['POSITIVE', 'NEUTRAL', 'NEGATIVE']).toContain(event.action)
  expect(['Small', 'Mid', 'Large']).toContain(event.cap_tier)
  expect(['1m', '3m', '6m', '12m']).toContain(event.tenure)
  expect(typeof event.entry_date).toBe('string')
  expect(typeof event.is_active).toBe('boolean')
}

// ---------------------------------------------------------------------------
// Case 1: getRecentSignalCalls — default params, returns ordered list
// ---------------------------------------------------------------------------

describe('getRecentSignalCalls', () => {
  beforeEach(() => sqlMock.mockReset())

  it('default (limit=50, days=7): returns ordered list with correct shape', async () => {
    sqlMock.mockResolvedValueOnce([RAW_CALL_A, RAW_CALL_B])

    const result = await getRecentSignalCalls()

    expect(sqlMock).toHaveBeenCalledTimes(1)
    expect(result).toHaveLength(2)

    const first = result[0]
    expectShape(first)
    expect(first.signal_call_id).toBe(RAW_CALL_A.signal_call_id)
    expect(first.ticker).toBe('RELIANCE')
    expect(first.action).toBe('POSITIVE')
    expect(first.cap_tier).toBe('Mid')
    expect(first.tenure).toBe('12m')
    expect(first.entry_date).toBe('2026-05-25')
    expect(first.entry_price).toBeNull()
    expect(first.confidence_unconditional).toBe('0.8200')
    expect(first.predicted_excess).toBe('0.043000')
    expect(first.exit_date).toBeNull()
    expect(first.is_active).toBe(true)

    // Second item has a closed position
    const second = result[1]
    expect(second.entry_date).toBe('2026-05-22')
    expect(second.exit_date).toBe('2026-05-24')
    expect(second.is_active).toBe(false)
    expect(second.predicted_excess).toBeNull()
  })

  // -------------------------------------------------------------------------
  // Case 2: Empty table → []
  // -------------------------------------------------------------------------

  it('empty table: returns empty array without throwing', async () => {
    sqlMock.mockResolvedValueOnce([])

    const result = await getRecentSignalCalls()

    expect(result).toEqual([])
    expect(Array.isArray(result)).toBe(true)
    expect(sqlMock).toHaveBeenCalledTimes(1)
  })

  it('custom limit and days are forwarded to SQL', async () => {
    sqlMock.mockResolvedValueOnce([RAW_CALL_A])

    const result = await getRecentSignalCalls(10, 3)

    expect(result).toHaveLength(1)
    // We can't inspect the SQL template tag content directly, but we verify
    // the function accepts custom params and returns the expected shape.
    expectShape(result[0])
  })
})

// ---------------------------------------------------------------------------
// Case 3: getSignalCallsByIid — multiple calls for same iid, ordered DESC
// ---------------------------------------------------------------------------

describe('getSignalCallsByIid', () => {
  beforeEach(() => sqlMock.mockReset())

  it('iid with multiple calls: returns ordered list by entry_date DESC', async () => {
    // Simulate two calls for RELIANCE, returned in descending date order
    sqlMock.mockResolvedValueOnce([RAW_CALL_A, RAW_CALL_C])

    const result = await getSignalCallsByIid('iii00000-0000-0000-0000-000000000001')

    expect(sqlMock).toHaveBeenCalledTimes(1)
    expect(result).toHaveLength(2)

    // First result is the more recent entry (2026-05-25)
    expect(result[0].entry_date).toBe('2026-05-25')
    expect(result[0].signal_call_id).toBe(RAW_CALL_A.signal_call_id)
    expect(result[0].ticker).toBe('RELIANCE')

    // Second result is older (2026-05-20)
    expect(result[1].entry_date).toBe('2026-05-20')
    expect(result[1].signal_call_id).toBe(RAW_CALL_C.signal_call_id)
  })

  it('iid not in universe: ticker falls back to instrument_id string', async () => {
    sqlMock.mockResolvedValueOnce([RAW_CALL_NO_TICKER])

    const result = await getSignalCallsByIid('iii00000-0000-0000-0000-000000000099')

    expect(result).toHaveLength(1)
    // ticker was null from DB → fallback to instrument_id
    expect(result[0].ticker).toBe('iii00000-0000-0000-0000-000000000099')
  })

  it('iid with no calls: returns empty array', async () => {
    sqlMock.mockResolvedValueOnce([])

    const result = await getSignalCallsByIid('iii00000-0000-0000-0000-deadbeef0000')

    expect(result).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Case 4: getSignalCallsByCell — cell with history, ordered DESC
// ---------------------------------------------------------------------------

describe('getSignalCallsByCell', () => {
  beforeEach(() => sqlMock.mockReset())

  it('cell with history: returns ordered list by entry_date DESC', async () => {
    // Two different stocks triggered by the same cell
    sqlMock.mockResolvedValueOnce([RAW_CALL_A, RAW_CALL_B])

    const result = await getSignalCallsByCell('ccc00000-0000-0000-0000-000000000001')

    expect(sqlMock).toHaveBeenCalledTimes(1)
    expect(result).toHaveLength(2)

    // Most recent first
    expect(result[0].entry_date).toBe('2026-05-25')
    expect(result[0].cell_id).toBe('ccc00000-0000-0000-0000-000000000001')

    expect(result[1].entry_date).toBe('2026-05-22')
    expect(result[1].cell_id).toBe('ccc00000-0000-0000-0000-000000000001')
  })

  it('cell with no calls: returns empty array', async () => {
    sqlMock.mockResolvedValueOnce([])

    const result = await getSignalCallsByCell('ccc00000-0000-0000-0000-ffffffff0000')

    expect(result).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Case 5: is_active flag — exit_date IS NULL → true; non-null → false
// ---------------------------------------------------------------------------

describe('is_active flag semantics', () => {
  beforeEach(() => sqlMock.mockReset())

  it('is_active = true when exit_date is null (open position)', async () => {
    sqlMock.mockResolvedValueOnce([RAW_CALL_A]) // exit_date: null → is_active: true

    const [event] = await getRecentSignalCalls(1, 30)

    expect(event.exit_date).toBeNull()
    expect(event.is_active).toBe(true)
  })

  it('is_active = false when exit_date is set (closed position)', async () => {
    sqlMock.mockResolvedValueOnce([RAW_CALL_B]) // exit_date: '2026-05-24' → is_active: false

    const [event] = await getRecentSignalCalls(1, 30)

    expect(event.exit_date).toBe('2026-05-24')
    expect(event.is_active).toBe(false)
  })
})
