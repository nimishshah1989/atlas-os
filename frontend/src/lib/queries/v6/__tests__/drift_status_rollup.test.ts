// frontend/src/lib/queries/v6/__tests__/drift_status_rollup.test.ts
//
// D.12 — 2 test cases for getDriftWarnCount()
//   1. Returns the count from the database when rows exist
//   2. Returns 0 when no cells are in drift_warn (empty result)

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getDriftWarnCount } from '../drift_status_rollup'

describe('getDriftWarnCount', () => {
  beforeEach(() => {
    sqlMock.mockReset()
  })

  it('returns the integer count when cells are in drift_warn', async () => {
    // Postgres COUNT() returns a stringified number via postgres-js
    sqlMock.mockResolvedValueOnce([{ cnt: '3' }])
    const count = await getDriftWarnCount()
    expect(count).toBe(3)
  })

  it('returns 0 when no cells are in drift_warn (COUNT returns "0")', async () => {
    sqlMock.mockResolvedValueOnce([{ cnt: '0' }])
    const count = await getDriftWarnCount()
    expect(count).toBe(0)
  })

  it('returns 0 when query returns an empty array (edge: empty table)', async () => {
    sqlMock.mockResolvedValueOnce([])
    const count = await getDriftWarnCount()
    expect(count).toBe(0)
  })
})
