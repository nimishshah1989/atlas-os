// src/app/portfolios/new/page.tsx — build a basket. The form is components/portfolios/BasketBuilder;
// the action is ./actions.ts; the thresholds it validates against are read here so the copy can
// name them before anything is typed.
import { NoDatabase } from '@/components/health/NoDatabase'
import { BasketBuilder, type BuilderLimits } from '@/components/portfolios/BasketBuilder'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { fracToMicro, microToPct, seedRows } from '@/lib/basketDraft'
import { dbAvailable } from '@/lib/db'
import { getBasketLimits, latestSession } from '@/lib/queries/baskets'
import { attempt } from '@/lib/result'

export const metadata = { title: 'New basket' }

const QUERY_BUDGET_MS = 12_000

// `?symbols=URA,NLR,URNM&name=Nuclear+%26+Uranium` — the way in from a theme or a market page.
// The seed only fills the form; every symbol, every weight and the Σ=1 rule are checked again by
// the action against instrument_master and the FM's thresholds, so a hand-edited URL can open a
// form the action then refuses, and never write a basket nobody validated.
type Params = { searchParams: Promise<{ symbols?: string; name?: string; kind?: string }> }

export default async function NewBasketPage({ searchParams }: Params) {
  await requireUser()
  const { symbols, name, kind } = await searchParams
  const seed = seedRows(symbols)
  if (!dbAvailable) return <NoDatabase title="New basket" />
  const [limits, session] = await Promise.all([
    attempt(getBasketLimits(), { label: 'basket thresholds', timeoutMs: QUERY_BUDGET_MS }),
    attempt(latestSession(), { label: 'latest session', timeoutMs: QUERY_BUDGET_MS }),
  ])
  let builder: BuilderLimits | null = null
  if (limits.ok) {
    const cap = fracToMicro(limits.value.maxPositionFrac)
    builder = {
      defaultCapital: limits.value.defaultCapitalUsd.split('.')[0],
      capPct: microToPct(cap),
      floorPct: microToPct(fracToMicro(limits.value.minWeightFrac)),
      minRows: Math.max(1, Math.ceil(1_000_000 / cap)),
    }
  }
  return (
    <div className="page">
      <PageHeader
        title="New basket"
        lead={
          seed.length
            ? `${seed.length} names, equal-weighted to start. Change any weight; the total must reach 100%.`
            : 'A name, a kind, capital, and the names with their weights. Saved as version 1; booked at the last session close by the next mark.'
        }
      />
      {builder ? (
        <BasketBuilder
          limits={builder}
          session={session.ok ? session.value : null}
          seed={seed.length ? seed : undefined}
          seedName={name?.slice(0, 80)}
          seedKind={kind === 'stock' ? 'stock' : kind === 'etf' ? 'etf' : undefined}
        />
      ) : (
        <QueryFailed error={limits.ok ? 'thresholds unavailable' : limits.error} />
      )}
    </div>
  )
}
