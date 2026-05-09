// frontend/src/app/health/page.tsx
// M12 — Backend Data Health Observability dashboard.

import {
  getFreshness,
  getHeaderStatus,
  getLatestAnomalies,
  getRecentRuns,
  getValidatorHistory,
} from '@/lib/queries/health'
import { HealthHeader } from '@/components/health/HealthHeader'
import { PipelineRunsTable } from '@/components/health/PipelineRunsTable'
import { FreshnessTable } from '@/components/health/FreshnessTable'
import { AnomaliesPanel } from '@/components/health/AnomaliesPanel'
import { ValidatorScorecard } from '@/components/health/ValidatorScorecard'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export default async function HealthPage() {
  const [status, runs, freshness, anomalies, validators] = await Promise.all([
    getHeaderStatus(),
    getRecentRuns(30),
    getFreshness(),
    getLatestAnomalies(),
    getValidatorHistory(30),
  ])

  return (
    <div>
      <HealthHeader status={status} />
      <PipelineRunsTable runs={runs} />
      <FreshnessTable rows={freshness} />
      <AnomaliesPanel anomalies={anomalies} />
      <ValidatorScorecard runs={validators} />
    </div>
  )
}
