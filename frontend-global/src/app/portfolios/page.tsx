// src/app/portfolios/page.tsx — the baskets, as cards. Logic lives in components/portfolios.
import Link from 'next/link'
import { NoDatabase } from '@/components/health/NoDatabase'
import { BasketCards } from '@/components/portfolios/BasketCards'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import { listBaskets } from '@/lib/queries/baskets'
import { attempt } from '@/lib/result'

export const metadata = { title: 'Portfolios' }

const QUERY_BUDGET_MS = 12_000

export default async function PortfoliosPage() {
  await requireUser()
  if (!dbAvailable) return <NoDatabase title="Portfolios" />
  const list = await attempt(listBaskets(), { label: 'baskets', timeoutMs: QUERY_BUDGET_MS })
  return (
    <div className="page">
      <PageHeader
        title="Portfolios"
        lead="Baskets built on this board, each a paper book of fractional shares booked at a real session close and marked nightly on total return."
        aside={
          <Link href="/portfolios/new" className="btn btn-primary text-body">
            New basket
          </Link>
        }
      />
      {list.ok ? <BasketCards baskets={list.value} /> : <QueryFailed error={list.error} />}
      <p className="mt-6 max-w-[80ch] text-meta text-ink-3">
        A basket is booked once, at the latest SPY session&rsquo;s close, with each name sized to its target weight of
        capital; its NAV is replayed from that day on close_tr every night. Since-inception is NAV over capital; vs SPY
        is the relative form (1+r)/(1+r<sub>SPY</sub>) − 1 over the same span. Nothing here is rebalanced.
      </p>
    </div>
  )
}
