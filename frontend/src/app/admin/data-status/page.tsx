// Admin · Data status — freshness RAG for the live product. Real-time (no cache).
export const dynamic = 'force-dynamic'
export const revalidate = 0

import { getFoundationFreshness, getJipFreshness, getRecentRuns, overallRag } from '@/lib/queries/health'
import { DataStatusPanel } from '@/components/admin/DataStatusPanel'

export default async function AdminDataStatusPage() {
  const [foundation, jip, runs] = await Promise.all([
    getFoundationFreshness().catch(() => []),
    getJipFreshness().catch(() => []),
    getRecentRuns(20).catch(() => []),
  ])
  // Overall light = worst of the product tables (the JIP sources feed them, so the product RAG is the headline).
  const overall = overallRag(foundation)
  const asOf = new Date().toISOString().slice(0, 10)
  return <DataStatusPanel foundation={foundation} jip={jip} runs={runs} overall={overall} asOf={asOf} />
}
