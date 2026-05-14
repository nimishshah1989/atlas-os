import { notFound } from 'next/navigation'
import {
  getFundDecisionScoreHistory,
  getFundDecisionDetail,
  getFundMaster,
} from '@/lib/queries/funds'
import { FundManagerDecisionsDetail } from '@/components/funds/FundManagerDecisionsDetail'

export const dynamic = 'force-dynamic'

type Props = {
  params: Promise<{ mstar_id: string }>
  searchParams: Promise<{ period?: string }>
}

export default async function FundDecisionsPage({ params, searchParams }: Props) {
  const { mstar_id } = await params
  const { period } = await searchParams

  const [master, scores] = await Promise.all([
    getFundMaster(mstar_id),
    getFundDecisionScoreHistory(mstar_id, 24),
  ])

  if (!master) notFound()

  const selectedPeriod = period ?? scores[0]?.period_date ?? null
  const initialChanges = selectedPeriod ? await getFundDecisionDetail(mstar_id, selectedPeriod) : []

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <div>
        <h1 className="font-serif text-xl text-ink-primary">{master.scheme_name}</h1>
        <p className="font-sans text-sm text-ink-tertiary mt-0.5">
          {master.amc} · {master.category_name} · Manager Decision History
        </p>
      </div>

      {scores.length === 0 ? (
        <p className="font-sans text-sm text-ink-secondary">
          No decision history available for this fund yet.
        </p>
      ) : selectedPeriod ? (
        <FundManagerDecisionsDetail
          scores={scores}
          initialChanges={initialChanges}
          initialPeriod={selectedPeriod}
        />
      ) : null}
    </div>
  )
}
