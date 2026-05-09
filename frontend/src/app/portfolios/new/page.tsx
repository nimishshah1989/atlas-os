// src/app/portfolios/new/page.tsx
// RSC — portfolio builder. Tabs: Static | Rule-Based.
// Static tab is fully built. Rule-Based tab is a Phase 4 placeholder.
// Shell ≤250 LOC.
import Link from 'next/link'
import { getStocksForPicker, getETFsForPicker, getMutualFundsForPicker } from '@/lib/queries/instruments'
import { StaticBuilder } from './StaticBuilder'

type SearchParams = {
  type?: string
}

export default async function NewPortfolioPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const params = await searchParams
  const activeType = params.type === 'rule-based' ? 'rule-based' : 'static'

  // Pre-load instrument data for the picker (server-side, limited rows)
  const [stocks, etfs, funds] = await Promise.all([
    getStocksForPicker(),
    getETFsForPicker(),
    getMutualFundsForPicker(),
  ])

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
      <header className="mb-6">
        <div className="flex items-center gap-2 text-xs font-sans text-ink-tertiary mb-3">
          <Link href="/portfolios" className="hover:text-ink-primary transition-colors">
            Portfolios
          </Link>
          <span>/</span>
          <span>New Portfolio</span>
        </div>
        <h1 className="font-serif text-2xl text-ink-primary">New Portfolio</h1>
      </header>

      {/* Tab bar */}
      <div className="flex border-b border-paper-rule mb-8">
        <Link
          href="/portfolios/new?type=static"
          className={`font-sans text-sm px-5 py-2.5 border-b-2 transition-colors ${
            activeType === 'static'
              ? 'border-accent text-accent font-semibold'
              : 'border-transparent text-ink-secondary hover:text-ink-primary'
          }`}
        >
          Static
        </Link>
        <Link
          href="/portfolios/new?type=rule-based"
          className={`font-sans text-sm px-5 py-2.5 border-b-2 transition-colors ${
            activeType === 'rule-based'
              ? 'border-accent text-accent font-semibold'
              : 'border-transparent text-ink-secondary hover:text-ink-primary'
          }`}
        >
          Rule-Based
        </Link>
      </div>

      {/* Tab content */}
      {activeType === 'static' ? (
        <StaticBuilder stocks={stocks} etfs={etfs} funds={funds} />
      ) : (
        <div className="border border-paper-rule rounded-[2px] p-8 text-center">
          <p className="font-sans text-base text-ink-secondary mb-2">
            Rule-Based builder ships in Phase 4.
          </p>
          <p className="font-sans text-sm text-ink-tertiary">
            Define entry/exit rules, regime gates, and market breadth triggers.
            Available in the next phase of M15.
          </p>
        </div>
      )}
    </main>
  )
}
