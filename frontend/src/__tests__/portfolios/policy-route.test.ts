// Tests for src/app/api/policy/route.ts
// Covers: body validation, policy validation blocking writes, happy path persists,
// house-default vs portfolio-override routing, null change = revert-to-inherit.
//
// Mock strategy mirrors propose-route.test.ts exactly:
//   vi.mock('@/lib/db') with a tagged-template vi.fn()

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

// ---------------------------------------------------------------------------
// Mock the DB tagged-template function
// ---------------------------------------------------------------------------

vi.mock('@/lib/db', () => {
  const fn = vi.fn()
  const tag = (...args: unknown[]) => fn(...args)
  tag._mockFn = fn
  return { default: tag }
})

import { POST } from '@/app/api/policy/route'
import { NextRequest } from 'next/server'
import sqlDefault from '@/lib/db'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockSql = (sqlDefault as any)._mockFn as ReturnType<typeof vi.fn>

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRequest(body: unknown): NextRequest {
  return new NextRequest('http://localhost/api/policy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// Minimal house-default DB row — all fields non-null except trailing_stop_pct
const HOUSE_ROW = {
  cash_floor_pct: '5',
  respect_regime_cap: true,
  max_per_stock_pct: '5',
  max_per_sector_pct: '15',
  max_small_cap_pct: '30',
  min_holdings: '10',
  max_positions: '30',
  buy_states: ['Emerging', 'Stage2'],
  min_within_state_rank: '0.60',
  min_rs_rank: '0.70',
  hard_stop_pct: '8',
  state_exit_trim: 'Stage3',
  state_exit_full: 'Stage4',
  trailing_stop_pct: null,
  instrument_universe: 'direct_equity',
  benchmark: 'NIFTY500',
  rebalance_cadence: 'weekly',
}

// ---------------------------------------------------------------------------
// Helper: set up mock SQL calls for the read path.
//
// The route performs (in order):
//   1. SELECT house row              → call #1
//   2. SELECT portfolio override row → call #2 (only if portfolioId set)
//   3. UPDATE / UPSERT               → call #3
//   4. SELECT house row (re-read)    → call #4
//   5. SELECT portfolio override (re-read) → call #5 (only if portfolioId set)
// ---------------------------------------------------------------------------

function setupHouseDefaultMocks(afterUpdateHouseRow = HOUSE_ROW): void {
  mockSql
    .mockResolvedValueOnce([HOUSE_ROW])   // #1 read house
    .mockResolvedValueOnce([])            // #3 UPDATE house
    .mockResolvedValueOnce([afterUpdateHouseRow]) // #4 re-read house
}

function setupPortfolioMocks(
  existingOverrideRow: Record<string, unknown> | null = null,
): void {
  mockSql
    .mockResolvedValueOnce([HOUSE_ROW])                                         // #1 read house
    .mockResolvedValueOnce(existingOverrideRow ? [existingOverrideRow] : [])    // #2 read portfolio override
    .mockResolvedValueOnce([])                                                  // #3 UPSERT
    .mockResolvedValueOnce([HOUSE_ROW])                                         // #4 re-read house
    .mockResolvedValueOnce(existingOverrideRow ? [existingOverrideRow] : [])    // #5 re-read portfolio override
}

beforeEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Input validation
// ---------------------------------------------------------------------------

describe('POST /api/policy — input validation', () => {
  it('returns 400 for non-JSON body', async () => {
    const req = new NextRequest('http://localhost/api/policy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: 'not-json',
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('bad_request')
  })

  it('returns 400 when changes is missing', async () => {
    const req = makeRequest({ portfolioId: null })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('validation_error')
  })

  it('returns 400 when changes is not an object', async () => {
    const req = makeRequest({ portfolioId: null, changes: 'bad' })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('validation_error')
  })

  it('returns 400 when portfolioId is not string or null', async () => {
    const req = makeRequest({ portfolioId: 42, changes: {} })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('validation_error')
  })

  it('returns 400 when changes contains an unknown field key', async () => {
    const req = makeRequest({ portfolioId: null, changes: { unknown_field: '10' } })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('validation_error')
  })
})

// ---------------------------------------------------------------------------
// Policy validation blocks writes
// ---------------------------------------------------------------------------

describe('POST /api/policy — policy validation blocks writes', () => {
  it('returns 400 (error envelope) and writes nothing when changes make min_holdings > max_positions', async () => {
    // current: min_holdings=10, max_positions=30
    // change: min_holdings → 50 (which makes 50 > 30 → Rule 1 violation)
    mockSql
      .mockResolvedValueOnce([HOUSE_ROW])  // read house
      // No further calls — write must NOT happen

    const req = makeRequest({
      portfolioId: null,
      changes: { min_holdings: '50' },
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('policy_violation')
    expect(body.message).toMatch(/min_holdings/)
    // Only 1 SQL call (the read); the UPDATE must NOT have been called
    expect(mockSql).toHaveBeenCalledTimes(1)
  })

  it('returns 400 when changes make max_per_stock_pct exceed max_per_sector_pct', async () => {
    // current: max_per_stock=5, max_per_sector=15
    // change: max_per_stock → 20 → violation (20 > 15)
    mockSql.mockResolvedValueOnce([HOUSE_ROW])

    const req = makeRequest({
      portfolioId: null,
      changes: { max_per_stock_pct: '20' },
    })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('policy_violation')
    expect(mockSql).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// Happy path — house default
// ---------------------------------------------------------------------------

describe('POST /api/policy — house default happy path', () => {
  it('writes and returns {data: <effective policy>} for a valid change to the house default', async () => {
    const updatedHouseRow = { ...HOUSE_ROW, rebalance_cadence: 'monthly' }
    mockSql
      .mockResolvedValueOnce([HOUSE_ROW])          // #1 read house
      .mockResolvedValueOnce([])                   // #2 UPDATE house
      .mockResolvedValueOnce([updatedHouseRow])    // #3 re-read house

    const req = makeRequest({
      portfolioId: null,
      changes: { rebalance_cadence: 'monthly' },
    })
    const res = await POST(req)
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.data).toBeDefined()
    // 3 SQL calls: read house, UPDATE, re-read house
    expect(mockSql).toHaveBeenCalledTimes(3)
  })

  it('returns 500 when DB throws during UPDATE', async () => {
    mockSql
      .mockResolvedValueOnce([HOUSE_ROW])
      .mockRejectedValueOnce(new Error('DB connection lost'))

    const req = makeRequest({
      portfolioId: null,
      changes: { rebalance_cadence: 'monthly' },
    })
    const res = await POST(req)
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error_code).toBe('db_error')
  })
})

// ---------------------------------------------------------------------------
// Happy path — portfolio override (existing row)
// ---------------------------------------------------------------------------

describe('POST /api/policy — portfolio override, existing row', () => {
  const PORTFOLIO_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
  const OVERRIDE_ROW = {
    ...HOUSE_ROW,
    max_per_stock_pct: '4',  // already overridden
    // all others null → inherited
    cash_floor_pct: null, respect_regime_cap: null,
    max_per_sector_pct: null, max_small_cap_pct: null,
    min_holdings: null, max_positions: null,
    buy_states: null, min_within_state_rank: null, min_rs_rank: null,
    hard_stop_pct: null, state_exit_trim: null, state_exit_full: null,
    trailing_stop_pct: null, instrument_universe: null, benchmark: null,
    rebalance_cadence: null,
  }

  it('updates and returns {data} for a valid change', async () => {
    const updatedOverrideRow = { ...OVERRIDE_ROW, max_per_stock_pct: '3' }
    mockSql
      .mockResolvedValueOnce([HOUSE_ROW])          // #1 read house
      .mockResolvedValueOnce([OVERRIDE_ROW])       // #2 read override
      .mockResolvedValueOnce([])                   // #3 UPDATE
      .mockResolvedValueOnce([HOUSE_ROW])          // #4 re-read house
      .mockResolvedValueOnce([updatedOverrideRow]) // #5 re-read override

    const req = makeRequest({
      portfolioId: PORTFOLIO_ID,
      changes: { max_per_stock_pct: '3' },
    })
    const res = await POST(req)
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.data).toBeDefined()
    expect(mockSql).toHaveBeenCalledTimes(5)
  })
})

// ---------------------------------------------------------------------------
// Happy path — portfolio override, no existing row (INSERT path)
// ---------------------------------------------------------------------------

describe('POST /api/policy — portfolio override, no existing row', () => {
  const PORTFOLIO_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

  it('inserts a new override row and returns {data}', async () => {
    const newOverrideRow = {
      ...HOUSE_ROW,
      cash_floor_pct: null, respect_regime_cap: null,
      max_per_stock_pct: null, max_per_sector_pct: null, max_small_cap_pct: null,
      min_holdings: null, max_positions: null,
      buy_states: null, min_within_state_rank: null, min_rs_rank: null,
      hard_stop_pct: null, state_exit_trim: null, state_exit_full: null,
      trailing_stop_pct: null, instrument_universe: null, benchmark: null,
      rebalance_cadence: 'monthly',
    }
    mockSql
      .mockResolvedValueOnce([HOUSE_ROW])       // #1 read house
      .mockResolvedValueOnce([])                // #2 read override → none
      .mockResolvedValueOnce([])                // #3 INSERT
      .mockResolvedValueOnce([HOUSE_ROW])       // #4 re-read house
      .mockResolvedValueOnce([newOverrideRow])  // #5 re-read override

    const req = makeRequest({
      portfolioId: PORTFOLIO_ID,
      changes: { rebalance_cadence: 'monthly' },
    })
    const res = await POST(req)
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.data).toBeDefined()
    expect(mockSql).toHaveBeenCalledTimes(5)
  })
})

// ---------------------------------------------------------------------------
// Revert-to-inherit: null change value → sets column to NULL in DB
// ---------------------------------------------------------------------------

describe('POST /api/policy — null change reverts to inherited', () => {
  const PORTFOLIO_ID = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
  const OVERRIDE_ROW = {
    ...HOUSE_ROW,
    rebalance_cadence: 'daily', // currently overriding
    cash_floor_pct: null, respect_regime_cap: null,
    max_per_stock_pct: null, max_per_sector_pct: null, max_small_cap_pct: null,
    min_holdings: null, max_positions: null,
    buy_states: null, min_within_state_rank: null, min_rs_rank: null,
    hard_stop_pct: null, state_exit_trim: null, state_exit_full: null,
    trailing_stop_pct: null, instrument_universe: null, benchmark: null,
  }

  it('succeeds when change value is null (revert to inherit)', async () => {
    // null → clear column (inherit from house default)
    // After revert, override row no longer has rebalance_cadence set
    const revertedOverrideRow = { ...OVERRIDE_ROW, rebalance_cadence: null }
    mockSql
      .mockResolvedValueOnce([HOUSE_ROW])            // #1 read house
      .mockResolvedValueOnce([OVERRIDE_ROW])         // #2 read override
      .mockResolvedValueOnce([])                     // #3 UPDATE (set NULL)
      .mockResolvedValueOnce([HOUSE_ROW])            // #4 re-read house
      .mockResolvedValueOnce([revertedOverrideRow])  // #5 re-read override

    const req = makeRequest({
      portfolioId: PORTFOLIO_ID,
      changes: { rebalance_cadence: null },
    })
    const res = await POST(req)
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.data).toBeDefined()
  })

  it('no DB write when changes is empty (nothing changed)', async () => {
    // Empty changes → nothing to write; still return current effective policy
    mockSql
      .mockResolvedValueOnce([HOUSE_ROW])   // read house
      .mockResolvedValueOnce([OVERRIDE_ROW]) // read override

    const req = makeRequest({
      portfolioId: PORTFOLIO_ID,
      changes: {},
    })
    const res = await POST(req)
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.data).toBeDefined()
    // Only 2 calls (reads), no write or second reads
    expect(mockSql).toHaveBeenCalledTimes(2)
  })
})

// ---------------------------------------------------------------------------
// 500 when no house-default row exists
// ---------------------------------------------------------------------------

describe('POST /api/policy — DB edge cases', () => {
  it('returns 500 when house-default row is missing', async () => {
    mockSql.mockResolvedValueOnce([]) // empty → no house row

    const req = makeRequest({ portfolioId: null, changes: { rebalance_cadence: 'daily' } })
    const res = await POST(req)
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error_code).toBe('db_error')
  })
})
