// Smoke test for getLatestSnapshotDate.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
const sqlMock = vi.fn()
vi.mock('@/lib/db', () => ({
  default: (...args: unknown[]) => sqlMock(...args),
}))

import { getLatestSnapshotDate } from '../snapshot'

describe('getLatestSnapshotDate', () => {
  beforeEach(() => sqlMock.mockReset())

  it('returns the GREATEST snapshot date from the union query', async () => {
    sqlMock.mockResolvedValueOnce([{ d: '2026-05-22' }])
    expect(await getLatestSnapshotDate()).toBe('2026-05-22')
  })

  it('falls back to today when DB returns null', async () => {
    sqlMock.mockResolvedValueOnce([{ d: null }])
    const out = await getLatestSnapshotDate()
    // Should look like an ISO date "YYYY-MM-DD"
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
