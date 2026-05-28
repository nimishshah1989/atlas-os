// frontend/src/lib/queries/v6/portfolio_analytics.ts
//
// TV-06: Fetch portfolio analytics (Sharpe, Sortino, Calmar, Beta, Alpha,
// MaxDD, TWR) plus daily returns series for the cumulative returns chart.
//
// Returns null on 404 (portfolio has no analytics yet) or network failure.
// Revalidates every 5 minutes — analytics are computed nightly, not live.

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
  max_drawdown: number
  twr: number
  annualised_return: number
  observation_days: number
  risk_free_rate_used: number
  daily_returns: DailyReturn[]
}

export async function getPortfolioAnalytics(
  portfolioId: string,
): Promise<PortfolioAnalytics | null> {
  const res = await fetch(`/v1/portfolios/${portfolioId}/analytics`, {
    next: { revalidate: 300 },
  })
  if (!res.ok) return null
  const json = await res.json()
  return (json.data as PortfolioAnalytics) ?? null
}
