// src/app/setup/policy/page.tsx
// Policy editor page — RSC shell ≤250 LOC.
// Fetches house-default or portfolio-specific effective policy server-side.
// Delegates selector + save wiring to PolicyPageClient (client island).
export const dynamic = 'force-dynamic'

import Link from 'next/link'
import { getAllPortfolios } from '@/lib/queries/portfolios'
import { getHouseDefaultPolicy, getEffectivePolicy } from '@/lib/queries/policy'
import { PolicyPageContainer } from '@/components/setup/PolicyPageContainer'

type SearchParams = { portfolio?: string }

export default async function SetupPolicyPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const params = await searchParams
  const portfolioId = params.portfolio ?? null

  const [portfolios, policy] = await Promise.all([
    getAllPortfolios(),
    portfolioId ? getEffectivePolicy(portfolioId) : getHouseDefaultPolicy(),
  ])

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-4xl mx-auto">
      <header className="mb-6">
        <div className="flex items-center gap-2 text-xs font-sans text-ink-tertiary mb-3">
          <Link href="/setup" className="hover:text-ink-primary transition-colors">
            Setup
          </Link>
          <span>/</span>
          <span>Policy</span>
        </div>
        <h1 className="font-serif text-2xl text-ink-primary">Trade Policy</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          House-default rules inherited by all portfolios unless overridden.
        </p>
      </header>

      {policy === null ? (
        <div className="px-4 py-3 rounded-[2px] border border-signal-warn/40 bg-signal-warn/5">
          <p className="font-sans text-sm text-signal-warn">
            No house-default policy found. Run{' '}
            <code className="font-mono text-xs">scripts/seed_house_policy.py</code> to seed
            the default row.
          </p>
        </div>
      ) : (
        <PolicyPageContainer
          policy={policy}
          portfolioId={portfolioId}
          portfolios={portfolios}
        />
      )}
    </main>
  )
}
