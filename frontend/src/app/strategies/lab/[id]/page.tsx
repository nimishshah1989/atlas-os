export const dynamic = 'force-dynamic'
import { getLeaderboard, getGenomePositions, getActivePortfolioConfig } from '@/lib/queries/strategy_lab'
import { StrategyLeaderboard } from '@/components/trading/StrategyLeaderboard'
import { ReplicationGuide } from '@/components/trading/ReplicationGuide'
import { notFound } from 'next/navigation'

type Props = { params: Promise<{ id: string }> }

export default async function StrategyExplorerPage({ params }: Props) {
  const { id } = await params
  const [leaderboard, positions, config] = await Promise.all([
    getLeaderboard(), getGenomePositions(id), getActivePortfolioConfig(),
  ])
  const selected = leaderboard.find((r) => r.genome_id === id)
  if (!selected) notFound()
  return (
    <main className="min-h-screen bg-paper px-6 py-6 max-w-7xl mx-auto">
      <div className="grid grid-cols-3 gap-6">
        <aside className="col-span-1"><StrategyLeaderboard leaderboard={leaderboard} selectedId={id} /></aside>
        <section className="col-span-2"><ReplicationGuide strategy={selected} positions={positions} config={config} /></section>
      </div>
    </main>
  )
}
