export const dynamic = 'force-dynamic'

import { getLeaderboard, getLatestInsights, getGenePoolHealth } from '@/lib/queries/strategy_lab'
import { MorningBrief } from '@/components/trading/MorningBrief'

type SearchParams = { configurator?: string }

export default async function StrategyLabPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams
  const showConfigurator = params.configurator === '1'
  const [leaderboard, insights, health] = await Promise.all([
    getLeaderboard(), getLatestInsights(), getGenePoolHealth(),
  ])
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
      <MorningBrief leaderboard={leaderboard} insights={insights} health={health} showConfigurator={showConfigurator} />
    </main>
  )
}
