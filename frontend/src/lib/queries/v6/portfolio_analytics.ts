// frontend/src/lib/queries/v6/portfolio_analytics.ts
//
// TV-06: Fetch portfolio analytics (Sharpe, Sortino, Calmar, Beta, Alpha,
// MaxDD, TWR) plus daily returns series for the cumulative returns chart.
//
// Returns null on 404 (portfolio has no analytics yet) or network failure.

import 'server-only'
import { callInternalApi } from '@/lib/internal-api'

export interface DailyReturn {
  date: string
  portfolio_return: number
  nifty50_return: number
}

export interface PortfolioAnalytics {
  sharpe: number | null
  sortino: number | null
  calmar: number | null
  beta: number | null
  alpha: number | null
  max_drawdown: number | null
  twr: number
  annualised_return: number
  observation_days: number
  risk_free_rate_used: number
  daily_returns: DailyReturn[]
}

export async function getPortfolioAnalytics(
  portfolioId: string,
): Promise<PortfolioAnalytics | null> {
  const res = await callInternalApi<PortfolioAnalytics>(
    `/v1/portfolios/${portfolioId}/analytics`,
  )
  if (!res.ok) return null
  // Guard against API responses missing daily_returns
  const data = res.data
  return { ...data, daily_returns: data.daily_returns ?? [] }
}
