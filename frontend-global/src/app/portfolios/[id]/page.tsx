// src/app/portfolios/[id]/page.tsx — one basket. Logic lives in components/portfolios.
import { notFound } from 'next/navigation'
import { NoDatabase } from '@/components/health/NoDatabase'
import { BasketDetailView } from '@/components/portfolios/BasketDetailView'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed } from '@/components/ui/Section'
import { requireUser } from '@/lib/auth'
import { dbAvailable } from '@/lib/db'
import { getBasket } from '@/lib/queries/baskets'
import { attempt } from '@/lib/result'

export const metadata = { title: 'Basket' }

const QUERY_BUDGET_MS = 12_000

export default async function BasketPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  await requireUser()
  if (!dbAvailable) return <NoDatabase title="Portfolios" />
  const d = await attempt(getBasket(id), { label: 'basket', timeoutMs: QUERY_BUDGET_MS })
  if (!d.ok) {
    return (
      <div className="page">
        <PageHeader title="Basket" />
        <QueryFailed error={d.error} />
      </div>
    )
  }
  if (!d.value) notFound()
  return <BasketDetailView d={d.value} />
}
