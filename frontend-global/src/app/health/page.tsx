// src/app/health/page.tsx — the operator surface. Reachable without a session; reads only the
// three ops tables in atlas_global. With no database it says so instead of pretending.
import { AnomaliesTable } from '@/components/health/AnomaliesTable'
import { HealthStatus } from '@/components/health/HealthStatus'
import { NoDatabase } from '@/components/health/NoDatabase'
import { PipelineRunsTable } from '@/components/health/PipelineRunsTable'
import { ValidatorScorecard } from '@/components/health/ValidatorScorecard'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed, Section } from '@/components/ui/Section'
import { dbAvailable } from '@/lib/db'
import {
  getLatestAnomalies,
  getLatestRunPerScript,
  getPipelineRuns,
  getValidatorHistory,
  getValidatorLatest,
} from '@/lib/queries/health'
import { attempt } from '@/lib/result'

export const dynamic = 'force-dynamic'
export const revalidate = 0
export const metadata = { title: 'Health' }

const RECENT_RUNS = 30
const VALIDATOR_WINDOW_DAYS = 30

export default async function HealthPage() {
  if (!dbAvailable) return <NoDatabase />

  const [latest, recent, validators, history, anomalies] = await Promise.all([
    attempt(getLatestRunPerScript()),
    attempt(getPipelineRuns(RECENT_RUNS)),
    attempt(getValidatorLatest()),
    attempt(getValidatorHistory(VALIDATOR_WINDOW_DAYS)),
    attempt(getLatestAnomalies()),
  ])

  return (
    <div className="page">
      <PageHeader
        title="Health"
        lead="What the nightly pipeline did, whether its gates passed, and which metrics the snapshot flagged."
      />

      <HealthStatus latest={latest} recent={recent} validators={validators} anomalies={anomalies} />

      <Section title="Latest run per script">
        {latest.ok ? (
          <PipelineRunsTable
            runs={latest.value}
            empty="No pipeline runs recorded yet. atlas_global_daily.sh writes one row per step when it first runs."
          />
        ) : (
          <QueryFailed error={latest.error} />
        )}
      </Section>

      <Section title="Recent runs" note={`newest ${RECENT_RUNS}`}>
        {recent.ok ? (
          <PipelineRunsTable runs={recent.value} empty="No pipeline runs recorded yet." />
        ) : (
          <QueryFailed error={recent.error} />
        )}
      </Section>

      <Section title="Validators">
        {validators.ok && history.ok ? (
          <ValidatorScorecard latest={validators.value} history={history.value} windowDays={VALIDATOR_WINDOW_DAYS} />
        ) : (
          <QueryFailed error={validators.ok ? (history.ok ? '' : history.error) : validators.error} />
        )}
      </Section>

      <Section title="Flagged metrics" note="from the latest health snapshot">
        {anomalies.ok ? <AnomaliesTable snapshot={anomalies.value} /> : <QueryFailed error={anomalies.error} />}
      </Section>
    </div>
  )
}
