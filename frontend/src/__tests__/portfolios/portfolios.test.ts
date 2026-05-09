// Tests for src/lib/queries/portfolios.ts
// Covers: getAllPortfolios union shape + type tagging, getStaticPortfolioById,
//         getRuleBasedPortfolioById, getBacktestsForPortfolio routing.

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Hoisted mocks — no top-level variable references inside vi.mock factories
vi.mock('server-only', () => ({}))
vi.mock('@/lib/db', () => ({ default: vi.fn() }))

import sql from '@/lib/db'
import {
  getAllPortfolios,
  getStaticPortfolioById,
  getRuleBasedPortfolioById,
  getBacktestsForPortfolio,
} from '@/lib/queries/portfolios'

// Helper: control what sql returns next call
function mockSqlReturn(data: unknown): void {
  ;(sql as unknown as { mockReturnValue: (v: unknown) => void }).mockReturnValue(
    Promise.resolve(data),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getAllPortfolios', () => {
  it('returns empty array when no portfolios exist', async () => {
    mockSqlReturn([])
    const result = await getAllPortfolios()
    expect(result).toEqual([])
  })

  it('passes through rows from sql with static type tag', async () => {
    const mockRows = [
      {
        id: 'uuid-1',
        name: 'Banking Leaders',
        type: 'static',
        instrument_count: 5,
        latest_sharpe: '1.42',
        paper_trading_active: false,
        created_at: new Date('2026-05-01'),
      },
      {
        id: 'uuid-2',
        name: 'FM Strategy Alpha',
        type: 'rule-based',
        instrument_count: null,
        latest_sharpe: '0.98',
        paper_trading_active: false,
        created_at: new Date('2026-05-02'),
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getAllPortfolios()
    expect(result).toHaveLength(2)
    expect(result[0].type).toBe('static')
    expect(result[1].type).toBe('rule-based')
  })

  it('handles rows with null sharpe gracefully', async () => {
    const mockRows = [
      {
        id: 'uuid-3',
        name: 'New Portfolio',
        type: 'static',
        instrument_count: 3,
        latest_sharpe: null,
        paper_trading_active: false,
        created_at: new Date('2026-05-01'),
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getAllPortfolios()
    expect(result[0].latest_sharpe).toBeNull()
  })

  it('preserves NUMERIC as string (latest_sharpe)', async () => {
    const mockRows = [
      {
        id: 'uuid-4',
        name: 'Portfolio X',
        type: 'static',
        instrument_count: 1,
        latest_sharpe: '1.5000',
        paper_trading_active: true,
        created_at: new Date('2026-05-01'),
      },
    ]
    mockSqlReturn(mockRows)
    const result = await getAllPortfolios()
    expect(typeof result[0].latest_sharpe).toBe('string')
  })
})

describe('getStaticPortfolioById', () => {
  it('returns null when no row found', async () => {
    mockSqlReturn([])
    const result = await getStaticPortfolioById('nonexistent-id')
    expect(result).toBeNull()
  })

  it('returns first row when found', async () => {
    const row = {
      id: 'static-uuid',
      name: 'My Static Portfolio',
      instruments: [{ instrument_id: 'abc', instrument_type: 'stock', weight_pct: 100 }],
      backtest_id: null,
      paper_trading_active: false,
      created_at: new Date('2026-05-01'),
      updated_at: new Date('2026-05-01'),
      latest_sharpe: '1.2',
      latest_max_drawdown: '-0.15',
      latest_alpha_vs_nifty500: '0.05',
    }
    mockSqlReturn([row])
    const result = await getStaticPortfolioById('static-uuid')
    expect(result).not.toBeNull()
    expect(result!.name).toBe('My Static Portfolio')
    expect(result!.instruments).toHaveLength(1)
    expect(result!.instruments[0].instrument_type).toBe('stock')
  })
})

describe('getRuleBasedPortfolioById', () => {
  it('returns null when not found', async () => {
    mockSqlReturn([])
    const result = await getRuleBasedPortfolioById('bad-id')
    expect(result).toBeNull()
  })

  it('returns detail row for rule-based portfolio', async () => {
    const row = {
      id: 'rb-uuid',
      name: 'FM Alpha Rules',
      config: { rs_state_filter: ['Leader', 'Strong'] },
      is_active: true,
      created_by: 'fund-manager',
      created_at: new Date('2026-05-01'),
      updated_at: new Date('2026-05-01'),
      latest_sharpe: '0.87',
      latest_max_drawdown: '-0.12',
      latest_alpha_vs_nifty500: '0.03',
      latest_backtest_id: 'bt-uuid',
    }
    mockSqlReturn([row])
    const result = await getRuleBasedPortfolioById('rb-uuid')
    expect(result).not.toBeNull()
    expect(result!.config).toHaveProperty('rs_state_filter')
    expect((result!.config.rs_state_filter as string[])).toContain('Leader')
  })
})

describe('getBacktestsForPortfolio', () => {
  it('returns backtests for static portfolio (custom_portfolio_id path)', async () => {
    const btRows = [
      {
        id: 'bt-1',
        backtest_type: 'full',
        start_date: new Date('2021-01-01'),
        end_date: new Date('2025-12-31'),
        sharpe_ratio: '1.5',
        max_drawdown: '-0.18',
        total_return: '0.82',
        alpha_vs_nifty500: '0.07',
        alpha_vs_naive_atlas: '0.03',
        walk_forward_oos_sharpe: '1.1',
        regime_breakdown: null,
        created_at: new Date('2026-05-01'),
      },
    ]
    mockSqlReturn(btRows)
    const result = await getBacktestsForPortfolio('static-id', 'static')
    expect(result).toHaveLength(1)
    expect(result[0].sharpe_ratio).toBe('1.5')
  })

  it('returns backtests for rule-based portfolio (strategy_id path)', async () => {
    const btRows = [
      {
        id: 'bt-2',
        backtest_type: 'full',
        start_date: new Date('2021-01-01'),
        end_date: new Date('2025-12-31'),
        sharpe_ratio: '0.92',
        max_drawdown: '-0.22',
        total_return: '0.55',
        alpha_vs_nifty500: '0.02',
        alpha_vs_naive_atlas: null,
        walk_forward_oos_sharpe: null,
        regime_breakdown: null,
        created_at: new Date('2026-05-02'),
      },
    ]
    mockSqlReturn(btRows)
    const result = await getBacktestsForPortfolio('rb-id', 'rule-based')
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('bt-2')
  })

  it('returns empty array if no backtests exist', async () => {
    mockSqlReturn([])
    const result = await getBacktestsForPortfolio('any-id', 'static')
    expect(result).toEqual([])
  })
})
