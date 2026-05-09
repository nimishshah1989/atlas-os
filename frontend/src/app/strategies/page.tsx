// src/app/strategies/page.tsx
// RSC — systematic strategies dashboard.
// Shell ≤250 LOC; logic lives in StrategiesView client island.
import { getAllStrategies } from '@/lib/queries/strategies'
import { StrategiesView } from './StrategiesView'

type SearchParams = {
  tier?: string
  archetype?: string
  paper?: string
}

export default async function StrategiesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const params = await searchParams

  const filter = {
    tier: params.tier ?? undefined,
    archetype: params.archetype ?? undefined,
    paperActive: params.paper === 'true' ? true : params.paper === 'false' ? false : undefined,
  }

  const strategies = await getAllStrategies(
    filter.tier || filter.archetype || filter.paperActive !== undefined ? filter : undefined,
  )

  // KPI band aggregates
  const avgSharpe =
    strategies.length > 0
      ? strategies
          .filter((s) => s.latest_sharpe != null)
          .reduce((sum, s) => sum + parseFloat(s.latest_sharpe!), 0) /
          (strategies.filter((s) => s.latest_sharpe != null).length || 1)
      : null

  const paperActiveCount = strategies.filter((s) => s.paper_active).length

  const tierCounts = strategies.reduce<Record<string, number>>((acc, s) => {
    acc[s.tier] = (acc[s.tier] ?? 0) + 1
    return acc
  }, {})

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <h1 className="font-serif text-2xl text-ink-primary">Systematic Strategies</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          {strategies.length} strategies · {paperActiveCount} paper-active
        </p>
      </header>

      {/* KPI band */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Avg Sharpe</p>
          <p className="font-mono text-lg font-semibold text-ink-primary mt-1">
            {avgSharpe != null ? avgSharpe.toFixed(2) : '—'}
          </p>
        </div>
        {(['Aggressive', 'Moderate', 'Passive'] as const).map((tier) => (
          <div key={tier} className="bg-paper border border-paper-rule rounded-[2px] p-3">
            <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">{tier}</p>
            <p className="font-mono text-lg font-semibold text-ink-primary mt-1">
              {tierCounts[tier] ?? 0}
            </p>
          </div>
        ))}
      </div>

      <StrategiesView
        strategies={strategies}
        initialTier={params.tier}
        initialArchetype={params.archetype}
        initialPaperActive={params.paper}
      />
    </main>
  )
}
