// frontend/src/app/portfolios/[id]/analytics/page.tsx
//
// TV-06: Portfolio analytics RSC shell.
// Fetches analytics data server-side and passes to PortfolioAnalyticsClient.
// No synthetic data — returns null when no analytics exist (empty state handled by client).

export const dynamic = 'force-dynamic'

import { getPortfolioAnalytics } from '@/lib/queries/v6/portfolio_analytics'
import { PortfolioAnalyticsClient } from '@/components/v6/PortfolioAnalyticsClient'
import { getStaticPortfolioById, getRuleBasedPortfolioById } from '@/lib/queries/portfolios'

type Props = { params: Promise<{ id: string }> }

export default async function PortfolioAnalyticsPage({ params }: Props) {
  const { id } = await params

  const [analytics, staticPortfolio, ruleBasedPortfolio] = await Promise.all([
    getPortfolioAnalytics(id),
    getStaticPortfolioById(id),
    getRuleBasedPortfolioById(id),
  ])

  // Use the real portfolio name if available; fall back to ID prefix.
  const portfolio = staticPortfolio ?? ruleBasedPortfolio
  const portfolioName = portfolio?.name ?? `Portfolio ${id.slice(0, 8)}`

  return (
    <PortfolioAnalyticsClient
      portfolioId={id}
      portfolioName={portfolioName}
      analytics={analytics}
    />
  )
}
