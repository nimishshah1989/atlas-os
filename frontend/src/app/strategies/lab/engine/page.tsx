export const dynamic = 'force-dynamic'

import { getLatestInsights, getGenePoolHealth, getLeaderboard } from '@/lib/queries/strategy_lab'
import { EngineRoom } from '@/components/trading/EngineRoom'

export default async function EngineRoomPage() {
  const [insights, health, leaderboard] = await Promise.all([getLatestInsights(), getGenePoolHealth(), getLeaderboard()])
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Strategy Lab</p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Engine Room</h1>
      </header>
      <EngineRoom insights={insights} health={health} leaderboard={leaderboard} />
    </main>
  )
}
