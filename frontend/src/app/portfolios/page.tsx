// src/app/portfolios/page.tsx
// RSC — FM custom portfolios list (Static + Rule-Based).
// Shell ≤250 LOC; logic lives in PortfoliosView client island.
import Link from 'next/link'
import { getAllPortfolios } from '@/lib/queries/portfolios'
import { PortfoliosView } from './PortfoliosView'

export default async function PortfoliosPage() {
  const portfolios = await getAllPortfolios()

  const staticCount = portfolios.filter((p) => p.type === 'static').length
  const ruleBasedCount = portfolios.filter((p) => p.type === 'rule-based').length
  const paperActiveCount = portfolios.filter((p) => p.paper_trading_active).length

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-serif text-2xl text-ink-primary">Custom Portfolios</h1>
          <p className="font-sans text-xs text-ink-tertiary mt-1">
            FM-authored portfolios · {portfolios.length} total
          </p>
        </div>
        <Link
          href="/portfolios/new?type=static"
          className="font-sans text-sm px-4 py-2 bg-accent text-white rounded-[2px] hover:bg-accent/90 transition-colors"
        >
          + New Portfolio
        </Link>
      </header>

      {/* KPI band */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Static</p>
          <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{staticCount}</p>
        </div>
        <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Rule-Based</p>
          <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{ruleBasedCount}</p>
        </div>
        <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Paper Active</p>
          <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{paperActiveCount}</p>
        </div>
      </div>

      <PortfoliosView portfolios={portfolios} />
    </main>
  )
}
