// Tests for src/app/api/portfolio/propose/route.ts
// Covers: input validation, happy path INSERT, error envelopes.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

// ---------------------------------------------------------------------------
// Mock the DB tag-function so tests don't need a real Postgres connection.
// vi.mock is hoisted — factory must not reference top-level variables.
// ---------------------------------------------------------------------------

vi.mock('@/lib/db', () => {
  const fn = vi.fn()
  // Tagged template literal: fn`...` delegates to fn(strings, ...values)
  // We wrap so the exported default behaves both as callable and has .begin
  const tag = (...args: unknown[]) => fn(...args)
  tag._mockFn = fn
  return { default: tag }
})

import { POST } from '@/app/api/portfolio/propose/route'
import { NextRequest } from 'next/server'
import sqlDefault from '@/lib/db'

// Access the underlying vi.fn() that was installed by the factory above.
// The factory exported `tag` which has a `_mockFn` property.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockSql = (sqlDefault as any)._mockFn as ReturnType<typeof vi.fn>

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRequest(body: unknown): NextRequest {
  return new NextRequest('http://localhost/api/portfolio/propose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

const VALID_BODY = {
  portfolio_id: '11111111-1111-1111-1111-111111111111',
  instrument_id: '22222222-2222-2222-2222-222222222222',
  proposed_weight: '5.0',
  rationale: 'stock-cap-bound 5.0%',
}

beforeEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Validation tests
// ---------------------------------------------------------------------------

describe('POST /api/portfolio/propose — validation', () => {
  it('returns 400 when portfolio_id is missing', async () => {
    const req = makeRequest({ ...VALID_BODY, portfolio_id: undefined })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBeDefined()
    expect(body.message).toMatch(/portfolio_id/)
  })

  it('returns 400 when portfolio_id is not a valid UUID', async () => {
    const req = makeRequest({ ...VALID_BODY, portfolio_id: 'not-a-uuid' })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('validation_error')
  })

  it('returns 400 when instrument_id is missing', async () => {
    const req = makeRequest({ ...VALID_BODY, instrument_id: undefined })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.message).toMatch(/instrument_id/)
  })

  it('returns 400 when instrument_id is not a valid UUID', async () => {
    const req = makeRequest({ ...VALID_BODY, instrument_id: 'bad-id' })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('validation_error')
  })

  it('returns 400 when proposed_weight is missing', async () => {
    const req = makeRequest({ ...VALID_BODY, proposed_weight: undefined })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.message).toMatch(/proposed_weight/)
  })

  it('returns 400 when proposed_weight is not a positive number', async () => {
    const req = makeRequest({ ...VALID_BODY, proposed_weight: '-1' })
    const res = await POST(req)
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error_code).toBe('validation_error')
  })

  it('returns 400 when proposed_weight is zero', async () => {
    const req = makeRequest({ ...VALID_BODY, proposed_weight: '0' })
    const res = await POST(req)
    expect(res.status).toBe(400)
  })

  it('returns 400 when proposed_weight is NaN string', async () => {
    const req = makeRequest({ ...VALID_BODY, proposed_weight: 'abc' })
    const res = await POST(req)
    expect(res.status).toBe(400)
  })
})

// ---------------------------------------------------------------------------
// Happy path
// ---------------------------------------------------------------------------

describe('POST /api/portfolio/propose — happy path', () => {
  it('inserts a row and returns {data: {id, status: "pending"}} with status 201', async () => {
    const returnedRow = {
      id: '33333333-3333-3333-3333-333333333333',
      status: 'pending',
    }
    mockSql.mockResolvedValueOnce([returnedRow])

    const req = makeRequest(VALID_BODY)
    const res = await POST(req)

    expect(res.status).toBe(201)
    const body = await res.json()
    expect(body.data).toMatchObject({ id: returnedRow.id, status: 'pending' })
  })

  it('passes rationale as nullable (accepts null rationale)', async () => {
    const returnedRow = { id: 'some-id', status: 'pending' }
    mockSql.mockResolvedValueOnce([returnedRow])

    const req = makeRequest({ ...VALID_BODY, rationale: null })
    const res = await POST(req)
    expect(res.status).toBe(201)
  })

  it('accepts rationale omitted entirely', async () => {
    const returnedRow = { id: 'some-id', status: 'pending' }
    mockSql.mockResolvedValueOnce([returnedRow])

    const { rationale: _omit, ...bodyNoRationale } = VALID_BODY
    const req = makeRequest(bodyNoRationale)
    const res = await POST(req)
    expect(res.status).toBe(201)
  })
})

// ---------------------------------------------------------------------------
// DB error surfacing
// ---------------------------------------------------------------------------

describe('POST /api/portfolio/propose — DB errors', () => {
  it('returns 500 when the DB throws', async () => {
    mockSql.mockRejectedValueOnce(new Error('DB connection refused'))

    const req = makeRequest(VALID_BODY)
    const res = await POST(req)
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error_code).toBeDefined()
  })
})
