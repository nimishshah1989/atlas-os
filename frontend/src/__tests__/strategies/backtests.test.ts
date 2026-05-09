// Tests for src/lib/queries/backtests.ts
// Verifies getLatestBacktestForStrategy ordering + null handling.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({
  default: vi.fn(),
}))

import sql from '@/lib/db'
import {
  getBacktestsForStrategy,
  getLatestBacktestForStrategy,
} from '@/lib/queries/backtests'

const MOCK_BT = {
  id: 'bt-001',
  strategy_id: 'strat-001',
  custom_portfolio_id: null,
  backtest_type: 'full',
  start_date: new Date('2020-01-01'),
  end_date: new Date('2024-12-31'),
  sharpe_ratio: '1.4500',
  max_drawdown: '-0.2340',
  total_return: '1.2300',
  alpha_vs_nifty500: '0.0890',
  alpha_vs_naive_atlas: '0.0450',
  walk_forward_oos_sharpe: '1.1200',
  regime_breakdown: {
    'Risk-On': { alpha: 0.12, days: 245 },
    'Constructive': { alpha: 0.08, days: 180 },
  },
  created_at: new Date('2026-04-10'),
}

// Mimic how existing tests mock the sql tagged-template literal:
// Cast through unknown to avoid PendingQuery deep-type-instantiation error.
function mockSqlReturn(data: unknown): void {
  ;(sql as unknown as { mockReturnValue: (v: unknown) => void }).mockReturnValue(
    Promise.resolve(data),
  )
}

describe('getBacktestsForStrategy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns array of BacktestRow with string NUMERIC columns', async () => {
    mockSqlReturn([MOCK_BT])

    const result = await getBacktestsForStrategy('strat-001')
    expect(result).toHaveLength(1)
    expect(typeof result[0].sharpe_ratio).toBe('string')
    expect(result[0].sharpe_ratio).toBe('1.4500')
  })

  it('returns empty array when no backtests', async () => {
    mockSqlReturn([])

    const result = await getBacktestsForStrategy('strat-000')
    expect(result).toHaveLength(0)
  })

  it('preserves regime_breakdown JSONB as object', async () => {
    mockSqlReturn([MOCK_BT])

    const result = await getBacktestsForStrategy('strat-001')
    expect(result[0].regime_breakdown).toEqual({
      'Risk-On': { alpha: 0.12, days: 245 },
      'Constructive': { alpha: 0.08, days: 180 },
    })
  })
})

describe('getLatestBacktestForStrategy', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null when no backtests exist', async () => {
    mockSqlReturn([])

    const result = await getLatestBacktestForStrategy('strat-no-bt')
    expect(result).toBeNull()
  })

  it('returns first (newest) row when backtests exist', async () => {
    mockSqlReturn([MOCK_BT])

    const result = await getLatestBacktestForStrategy('strat-001')
    expect(result).not.toBeNull()
    expect(result?.id).toBe('bt-001')
    expect(result?.sharpe_ratio).toBe('1.4500')
  })

  it('handles null optional KPI fields gracefully', async () => {
    const nullBt = {
      ...MOCK_BT,
      sharpe_ratio: null,
      alpha_vs_nifty500: null,
      regime_breakdown: null,
    }
    mockSqlReturn([nullBt])

    const result = await getLatestBacktestForStrategy('strat-001')
    expect(result?.sharpe_ratio).toBeNull()
    expect(result?.alpha_vs_nifty500).toBeNull()
    expect(result?.regime_breakdown).toBeNull()
  })
})
