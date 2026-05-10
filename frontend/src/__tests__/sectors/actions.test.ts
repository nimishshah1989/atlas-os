import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/queries/sector-deep-dive', () => ({
  getTopPicksBySector: vi.fn(),
}))

import { getTopPicksAction } from '@/app/sectors/actions'
import { getTopPicksBySector } from '@/lib/queries/sector-deep-dive'

const mockGetTopPicks = vi.mocked(getTopPicksBySector)

describe('getTopPicksAction', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns top picks for a valid sector', async () => {
    mockGetTopPicks.mockResolvedValue([
      { symbol: 'HDFCBANK', company_name: 'HDFC Bank', rs_pctile_3m: '0.87', rs_state: 'Leader' },
    ])
    const result = await getTopPicksAction('Banking')
    expect(result).toHaveLength(1)
    expect(result[0].symbol).toBe('HDFCBANK')
  })

  it('returns empty array for empty sector name', async () => {
    const result = await getTopPicksAction('')
    expect(result).toEqual([])
    expect(mockGetTopPicks).not.toHaveBeenCalled()
  })

  it('returns empty array when query throws', async () => {
    mockGetTopPicks.mockRejectedValue(new Error('DB connection failed'))
    const result = await getTopPicksAction('Banking')
    expect(result).toEqual([])
  })

  it('returns empty array when sector has no investable stocks', async () => {
    mockGetTopPicks.mockResolvedValue([])
    const result = await getTopPicksAction('Telecom')
    expect(result).toEqual([])
  })
})
