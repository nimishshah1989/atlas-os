// frontend/src/lib/queries/v6/__tests__/gold_availability.test.ts
//
// Tests for isGoldAvailable().
// 2 cases: Postgres returns true row, Postgres returns false row.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))

// React.cache pass-through: just call the inner function
vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return {
    ...actual,
    cache: (fn: (...args: unknown[]) => unknown) => fn,
  }
})

const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { isGoldAvailable } from '../gold_availability'

describe('isGoldAvailable', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns true when Postgres EXISTS row is true', async () => {
    sqlMock.mockResolvedValueOnce([{ exists: true }])
    const result = await isGoldAvailable()
    expect(result).toBe(true)
  })

  it('returns false when Postgres EXISTS row is false', async () => {
    sqlMock.mockResolvedValueOnce([{ exists: false }])
    const result = await isGoldAvailable()
    expect(result).toBe(false)
  })
})
