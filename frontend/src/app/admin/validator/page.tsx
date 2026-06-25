// Phase C — Validator Admin Page
// Shows nightly frontend accuracy scan results: route health matrix, aggregated findings, trend.
export const dynamic = 'force-dynamic'

import {
  getRecentValidatorRuns,
  getLatestFrontendFindingGroups,
  getLatestRouteSummary,
  getValidatorTrend,
} from '@/lib/queries/validator'
import { ValidatorDashboard } from '@/components/admin/ValidatorDashboard'

export default async function ValidatorAdminPage() {
  const [runs, groups, routeSummary, trend] = await Promise.all([
    getRecentValidatorRuns(20),
    getLatestFrontendFindingGroups(),
    getLatestRouteSummary(),
    getValidatorTrend(7),
  ])

  return (
    <main className="min-h-screen bg-surface-panel px-8 py-6 max-w-6xl mx-auto">
      <ValidatorDashboard
        runs={runs}
        groups={groups}
        routeSummary={routeSummary}
        trend={trend}
      />
    </main>
  )
}
