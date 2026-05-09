// Tests for src/app/portfolios/new/actions.ts
// Covers: createStaticPortfolio validation + happy path,
//         getPortfolioStatusAction, togglePaperTradingAction.

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('server-only', () => ({}))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

// Must use inline vi.fn() in the factory — not a top-level variable.
vi.mock('@/lib/internal-api', () => ({
  callInternalApi: vi.fn(),
  triggerRecompute: vi.fn(),
}))

import { revalidatePath } from 'next/cache'
import { callInternalApi } from '@/lib/internal-api'
import {
  createStaticPortfolio,
  getPortfolioStatusAction,
  togglePaperTradingAction,
} from '@/app/portfolios/new/actions'

// Helper for typed mock
const mockApi = callInternalApi as ReturnType<typeof vi.fn>

const VALID_INSTRUMENTS = [
  { instrument_id: 'uuid-hdfc', instrument_type: 'stock' as const, weight_pct: 50 },
  { instrument_id: 'uuid-infosys', instrument_type: 'stock' as const, weight_pct: 50 },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('createStaticPortfolio', () => {
  it('rejects empty name', async () => {
    const result = await createStaticPortfolio('', VALID_INSTRUMENTS)
    expect(result).toEqual({ ok: false, error: 'Portfolio name is required' })
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('rejects whitespace-only name', async () => {
    const result = await createStaticPortfolio('   ', VALID_INSTRUMENTS)
    expect(result).toEqual({ ok: false, error: 'Portfolio name is required' })
  })

  it('rejects empty instruments array', async () => {
    const result = await createStaticPortfolio('My Portfolio', [])
    expect(result).toEqual({ ok: false, error: 'At least one instrument is required' })
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('rejects zero-weight instrument', async () => {
    const instruments = [
      { instrument_id: 'uuid-a', instrument_type: 'stock' as const, weight_pct: 0 },
      { instrument_id: 'uuid-b', instrument_type: 'stock' as const, weight_pct: 100 },
    ]
    const result = await createStaticPortfolio('Test', instruments)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain('must be greater than 0')
  })

  it('rejects weights that do not sum to ~100 (±0.5)', async () => {
    const instruments = [
      { instrument_id: 'uuid-a', instrument_type: 'stock' as const, weight_pct: 30 },
      { instrument_id: 'uuid-b', instrument_type: 'stock' as const, weight_pct: 40 },
    ] // sum = 70, outside ±0.5 of 100
    const result = await createStaticPortfolio('Test', instruments)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toContain('Weights must sum to 100%')
  })

  it('accepts weights within ±0.5 tolerance (33.33+33.33+33.34=100.00)', async () => {
    const instruments = [
      { instrument_id: 'uuid-a', instrument_type: 'stock' as const, weight_pct: 33.33 },
      { instrument_id: 'uuid-b', instrument_type: 'stock' as const, weight_pct: 33.33 },
      { instrument_id: 'uuid-c', instrument_type: 'etf' as const, weight_pct: 33.34 },
    ]
    mockApi.mockResolvedValueOnce({
      ok: true,
      data: { portfolio_id: 'new-portfolio-uuid' },
      status: 201,
    })
    const result = await createStaticPortfolio('Three-Way Split', instruments)
    expect(result).toEqual({ ok: true, portfolio_id: 'new-portfolio-uuid' })
    expect(revalidatePath).toHaveBeenCalledWith('/portfolios')
  })

  it('happy path: valid input calls callInternalApi POST and revalidatePath', async () => {
    mockApi.mockResolvedValueOnce({
      ok: true,
      data: { portfolio_id: 'portfolio-123' },
      status: 201,
    })
    const result = await createStaticPortfolio('Banking Leaders', VALID_INSTRUMENTS)
    expect(result).toEqual({ ok: true, portfolio_id: 'portfolio-123' })
    expect(mockApi).toHaveBeenCalledWith(
      '/api/portfolios/custom',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(revalidatePath).toHaveBeenCalledWith('/portfolios')
  })

  it('surfaces API error without calling revalidatePath', async () => {
    mockApi.mockResolvedValueOnce({
      ok: false,
      error_code: 'validation_error',
      message: 'Instrument uuid-hdfc not in universe',
      status: 422,
    })
    const result = await createStaticPortfolio('Bad Portfolio', VALID_INSTRUMENTS)
    expect(result).toEqual({ ok: false, error: 'Instrument uuid-hdfc not in universe' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it('surfaces network error', async () => {
    mockApi.mockResolvedValueOnce({
      ok: false,
      error_code: 'network_error',
      message: 'fetch failed',
      status: 0,
    })
    const result = await createStaticPortfolio('Network Fail', VALID_INSTRUMENTS)
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toBe('fetch failed')
  })
})

describe('getPortfolioStatusAction', () => {
  it('rejects empty portfolioId', async () => {
    const result = await getPortfolioStatusAction('')
    expect(result).toEqual({ ok: false, error: 'Portfolio ID is required' })
    expect(mockApi).not.toHaveBeenCalled()
  })

  it('returns pending status', async () => {
    mockApi.mockResolvedValueOnce({
      ok: true,
      data: { status: 'pending' },
      status: 200,
    })
    const result = await getPortfolioStatusAction('portfolio-abc')
    expect(result).toEqual({ ok: true, status: 'pending', backtest_id: undefined })
  })

  it('returns completed status with backtest_id', async () => {
    mockApi.mockResolvedValueOnce({
      ok: true,
      data: { status: 'completed', backtest_id: 'bt-xyz' },
      status: 200,
    })
    const result = await getPortfolioStatusAction('portfolio-abc')
    expect(result).toEqual({ ok: true, status: 'completed', backtest_id: 'bt-xyz' })
  })

  it('surfaces API error', async () => {
    mockApi.mockResolvedValueOnce({
      ok: false,
      error_code: 'not_found',
      message: 'Portfolio not found',
      status: 404,
    })
    const result = await getPortfolioStatusAction('bad-id')
    expect(result).toEqual({ ok: false, error: 'Portfolio not found' })
  })
})

describe('togglePaperTradingAction', () => {
  it('rejects empty portfolioId', async () => {
    const result = await togglePaperTradingAction('', true)
    expect(result).toEqual({ ok: false, error: 'Portfolio ID is required' })
  })

  it('happy path: calls PATCH endpoint and revalidates both paths', async () => {
    mockApi.mockResolvedValueOnce({ ok: true, data: {}, status: 200 })
    const result = await togglePaperTradingAction('portfolio-xyz', true)
    expect(result).toEqual({ ok: true })
    expect(mockApi).toHaveBeenCalledWith(
      '/api/portfolios/portfolio-xyz/paper-trading',
      expect.objectContaining({ method: 'PATCH', body: { paper_trading_active: true } }),
    )
    expect(revalidatePath).toHaveBeenCalledWith('/portfolios/portfolio-xyz')
    expect(revalidatePath).toHaveBeenCalledWith('/portfolios')
  })

  it('deactivate path: sends false', async () => {
    mockApi.mockResolvedValueOnce({ ok: true, data: {}, status: 200 })
    await togglePaperTradingAction('portfolio-xyz', false)
    expect(mockApi).toHaveBeenCalledWith(
      '/api/portfolios/portfolio-xyz/paper-trading',
      expect.objectContaining({ body: { paper_trading_active: false } }),
    )
  })

  it('surfaces API error without revalidating', async () => {
    mockApi.mockResolvedValueOnce({
      ok: false,
      error_code: 'api_error',
      message: 'Server error',
      status: 500,
    })
    const result = await togglePaperTradingAction('portfolio-xyz', false)
    expect(result).toEqual({ ok: false, error: 'Server error' })
    expect(revalidatePath).not.toHaveBeenCalled()
  })
})
