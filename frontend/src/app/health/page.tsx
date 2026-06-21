// frontend/src/app/health/page.tsx
// M12 — Backend Data Health Observability dashboard.

import {
  getFreshness,
  getHeaderStatus,
  getJipFreshness,
  getLatestAnomalies,
  getLatestRunPerScript,
  getRecentRuns,
  getValidatorHistory,
  getValidatorLatest,
} from '@/lib/queries/health'
import { HealthHeader } from '@/components/health/HealthHeader'
import { HealthSummaryCards } from '@/components/health/HealthSummaryCards'
import { PipelineRunsTable } from '@/components/health/PipelineRunsTable'
import { FreshnessTable } from '@/components/health/FreshnessTable'
import { JipSyncPanel } from '@/components/health/JipSyncPanel'
import { AnomaliesPanel } from '@/components/health/AnomaliesPanel'
import { ValidatorScorecard } from '@/components/health/ValidatorScorecard'
import { KnownGapsPanel } from '@/components/health/KnownGapsPanel'

export const dynamic = 'force-dynamic'
export const revalidate = 0

const DEFAULT_STATUS = { level: 'yellow' as const, message: 'Status unavailable — DB query failed', last_health_check: null }

export default async function HealthPage() {
  const [status, latestRuns, allRuns, freshness, jipFreshness, anomalies, validators, validatorLatest] =
    await Promise.all([
      getHeaderStatus().catch(() => DEFAULT_STATUS),
      getLatestRunPerScript().catch(() => []),
      getRecentRuns(30).catch(() => []),
      getFreshness().catch(() => []),
      getJipFreshness().catch(() => []),
      getLatestAnomalies().catch(() => []),
      getValidatorHistory(30).catch(() => []),
      getValidatorLatest().catch(() => []),
    ])

  const staleTables = freshness.filter((t) => t.lag_days != null && t.lag_days > 2).length
  const recentFailures = allRuns.filter((r) => r.status === 'failed').length

  return (
    <div>
      <HealthHeader status={status} />
      <HealthSummaryCards
        validators={validatorLatest}
        staleTables={staleTables}
        recentFailures={recentFailures}
        anomalyCount={anomalies.length}
      />
      <PipelineRunsTable runs={latestRuns} title="Pipeline · latest run per script" />
      <FreshnessTable rows={freshness} />
      <JipSyncPanel rows={jipFreshness} />
      <AnomaliesPanel anomalies={anomalies} />
      <ValidatorScorecard runs={validators} />
      <KnownGapsPanel />
    </div>
  )
}
