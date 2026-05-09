'use server'
// src/app/portfolios/new/actions.ts
// Server Actions for custom portfolio creation.
// Only async-function exports — Next.js 'use server' rule enforced.

import { revalidatePath } from 'next/cache'
import { callInternalApi } from '@/lib/internal-api'

export type InstrumentInput = {
  instrument_id: string
  instrument_type: 'stock' | 'etf' | 'fund'
  weight_pct: number
}

export type CreatePortfolioResult =
  | { ok: true; portfolio_id: string }
  | { ok: false; error: string }

export type PortfolioStatusResult =
  | { ok: true; status: 'pending' | 'completed'; backtest_id?: string }
  | { ok: false; error: string }

/**
 * Create a static portfolio via POST /api/portfolios/custom.
 * Validates: name non-empty, instruments not empty,
 *            weights sum to ~100 (±0.5 tolerance), each weight > 0.
 * On success, revalidates /portfolios list.
 */
export async function createStaticPortfolio(
  name: string,
  instruments: InstrumentInput[],
): Promise<CreatePortfolioResult> {
  // Validate name
  if (!name.trim()) {
    return { ok: false, error: 'Portfolio name is required' }
  }

  // Validate instruments list
  if (instruments.length === 0) {
    return { ok: false, error: 'At least one instrument is required' }
  }

  // Validate each weight > 0
  for (const inst of instruments) {
    if (inst.weight_pct <= 0) {
      return { ok: false, error: `Weight for ${inst.instrument_id} must be greater than 0` }
    }
  }

  // Validate weights sum ~100 (±0.5 tolerance)
  const weightSum = instruments.reduce((acc, i) => acc + i.weight_pct, 0)
  if (Math.abs(weightSum - 100) > 0.5) {
    return {
      ok: false,
      error: `Weights must sum to 100% (currently ${weightSum.toFixed(2)}%)`,
    }
  }

  // Call FastAPI backend
  const result = await callInternalApi<{ portfolio_id: string }>(
    '/api/portfolios/custom',
    {
      method: 'POST',
      body: { name: name.trim(), instruments },
    },
  )

  if (!result.ok) {
    return { ok: false, error: result.message }
  }

  if (!result.data?.portfolio_id) {
    return { ok: false, error: 'Server returned unexpected response shape' }
  }

  revalidatePath('/portfolios')
  return { ok: true, portfolio_id: result.data.portfolio_id }
}

/**
 * Poll the status of a portfolio's backtest.
 * GET /api/portfolios/custom/{id}/status
 * Returns {status: 'pending'|'completed', backtest_id?: string}.
 */
export async function getPortfolioStatusAction(
  portfolioId: string,
): Promise<PortfolioStatusResult> {
  if (!portfolioId) {
    return { ok: false, error: 'Portfolio ID is required' }
  }

  const result = await callInternalApi<{ status: 'pending' | 'completed'; backtest_id?: string }>(
    `/api/portfolios/custom/${portfolioId}/status`,
    { method: 'GET' },
  )

  if (!result.ok) {
    return { ok: false, error: result.message }
  }

  return {
    ok: true,
    status: result.data.status,
    backtest_id: result.data.backtest_id,
  }
}

/**
 * Toggle paper trading on a static portfolio.
 * PATCH /api/portfolios/{id}/paper-trading
 */
export async function togglePaperTradingAction(
  portfolioId: string,
  active: boolean,
): Promise<{ ok: true } | { ok: false; error: string }> {
  if (!portfolioId) {
    return { ok: false, error: 'Portfolio ID is required' }
  }

  const result = await callInternalApi(
    `/api/portfolios/${portfolioId}/paper-trading`,
    { method: 'PATCH', body: { paper_trading_active: active } },
  )

  if (!result.ok) {
    return { ok: false, error: result.message }
  }

  revalidatePath(`/portfolios/${portfolioId}`)
  revalidatePath('/portfolios')
  return { ok: true }
}
