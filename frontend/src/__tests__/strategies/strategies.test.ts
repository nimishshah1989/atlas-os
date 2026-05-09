// Tests for src/lib/queries/strategies.ts
// Mocks postgres.js to verify query shape + return typing.

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock server-only so Vitest (jsdom) doesn't error
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({
  default: vi.fn(),
}))

import sql from '@/lib/db'
import { getAllStrategies, getStrategyById, getStrategyConfig } from '@/lib/queries/strategies'

const MOCK_STRATEGY = {
  id: 'aaaa-bbbb',
  name: 'Momentum Alpha',
  tier: 'Aggressive',
  archetype: 'momentum_blend',
  variant: 'v1',
  config: { state_filter: ['Leader', 'Strong'], max_positions: 20 },
  is_active: true,
  is_fm_authored: false,
  created_by: null,
  created_at: new Date('2026-01-01'),
  updated_at: new Date('2026-04-01'),
  paper_active: false,
  latest_sharpe: '1.32',
  latest_alpha_vs_nifty500: '0.1230',
  latest_backtest_at: new Date('2026-04-10'),
}

// Cast through unknown to avoid PendingQuery deep-type-instantiation TS error
function mockSqlReturn(data: unknown): void {
  ;(sql as unknown as { mockReturnValue: (v: unknown) => void }).mockReturnValue(
    Promise.resolve(data),
  )
}

describe('getAllStrategies', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns array of StrategyRow', async () => {
    mockSqlReturn([MOCK_STRATEGY])

    const result = await getAllStrategies()
    expect(result).toHaveLength(1)
    expect(result[0].name).toBe('Momentum Alpha')
    expect(result[0].tier).toBe('Aggressive')
    expect(result[0].is_fm_authored).toBe(false)
  })

  it('returns empty array when no strategies match', async () => {
    mockSqlReturn([])

    const result = await getAllStrategies({ tier: 'Passive' })
    expect(result).toHaveLength(0)
  })

  it('preserves NUMERIC as string (latest_sharpe)', async () => {
    mockSqlReturn([MOCK_STRATEGY])

    const result = await getAllStrategies()
    // NUMERIC comes back as string from postgres.js; test confirms we don't parse it
    expect(typeof result[0].latest_sharpe).toBe('string')
    expect(result[0].latest_sharpe).toBe('1.32')
  })

  it('paper_active is a boolean', async () => {
    mockSqlReturn([{ ...MOCK_STRATEGY, paper_active: true }])

    const result = await getAllStrategies()
    expect(result[0].paper_active).toBe(true)
  })
})

describe('getStrategyById', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when no rows', async () => {
    mockSqlReturn([])

    const result = await getStrategyById('nonexistent-id')
    expect(result).toBeNull()
  })

  it('returns first row when found', async () => {
    mockSqlReturn([MOCK_STRATEGY])

    const result = await getStrategyById('aaaa-bbbb')
    expect(result).not.toBeNull()
    expect(result?.id).toBe('aaaa-bbbb')
    expect(result?.config).toEqual({ state_filter: ['Leader', 'Strong'], max_positions: 20 })
  })
})

describe('getStrategyConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when strategy not found', async () => {
    mockSqlReturn([])

    const result = await getStrategyConfig('missing')
    expect(result).toBeNull()
  })

  it('returns id and config when found', async () => {
    mockSqlReturn([{ id: 'aaaa', config: { state_filter: ['Leader'] } }])

    const result = await getStrategyConfig('aaaa')
    expect(result?.id).toBe('aaaa')
    expect(result?.config.state_filter).toEqual(['Leader'])
  })
})
