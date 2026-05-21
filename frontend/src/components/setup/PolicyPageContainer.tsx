'use client'
// src/components/setup/PolicyPageContainer.tsx
// Thin client wrapper that owns the router-push on portfolio selector change.
// Keeps the policy page shell as a pure RSC (no 'use client' needed there).

import { useRouter } from 'next/navigation'
import { PolicyPageClient } from '@/components/setup/PolicyPageClient'
import type { EffectivePolicy } from '@/components/portfolio/PolicyPanel'
import type { PortfolioListRow } from '@/lib/queries/portfolios'

type Props = {
  policy: EffectivePolicy
  portfolioId: string | null
  portfolios: PortfolioListRow[]
}

export function PolicyPageContainer({ policy, portfolioId, portfolios }: Props) {
  const router = useRouter()

  function handlePortfolioChange(id: string | null) {
    const url = id ? `/setup/policy?portfolio=${id}` : '/setup/policy'
    router.push(url)
  }

  return (
    <PolicyPageClient
      policy={policy}
      portfolioId={portfolioId}
      portfolios={portfolios}
      onPortfolioChange={handlePortfolioChange}
    />
  )
}
