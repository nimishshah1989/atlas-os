// src/app/admin/policies/page.tsx
// RSC — fetches all decision policies + all atlas_thresholds + recent runs, hands to client island.
import { getAllDecisionPolicies } from '@/lib/queries/policies'
import { getAllThresholds, getRecentRuns } from '@/lib/queries/thresholds'
import { PoliciesView } from './PoliciesView'

export default async function PoliciesPage() {
  const [policies, thresholds, recentRuns] = await Promise.all([
    getAllDecisionPolicies(),
    getAllThresholds(),
    getRecentRuns(5),
  ])

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <h1 className="font-serif text-2xl text-ink-primary">Decision Policy Admin</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          {policies.length} policies · {thresholds.length} raw thresholds · M14
        </p>
      </header>
      <PoliciesView policies={policies} thresholds={thresholds} recentRuns={recentRuns} />
    </main>
  )
}
