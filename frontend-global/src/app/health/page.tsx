// src/app/health/page.tsx — the operator surface. Reachable without a session; reads only the
// ops tables in atlas_global (runs, validators, health snapshot, provider calls). With no
// database it says so instead of pretending.
import { AnomaliesTable } from '@/components/health/AnomaliesTable'
import { FreshnessTable } from '@/components/health/FreshnessTable'
import { HealthStatus } from '@/components/health/HealthStatus'
import { NoDatabase } from '@/components/health/NoDatabase'
import { PipelineRunsTable } from '@/components/health/PipelineRunsTable'
import { ProviderCallsTable } from '@/components/health/ProviderCallsTable'
import { ValidatorScorecard } from '@/components/health/ValidatorScorecard'
import { PageHeader } from '@/components/ui/PageHeader'
import { QueryFailed, Section } from '@/components/ui/Section'
import { dbAvailable } from '@/lib/db'
import { formatIsoDate } from '@/lib/format'
import {
  getFreshnessRows,
  getLatestAnomalies,
  getLatestRunPerScript,
  getPipelineRuns,
  getProviderCalls,
  getValidatorHistory,
  getValidatorLatest,
} from '@/lib/queries/health'
import { attempt } from '@/lib/result'

export const dynamic = 'force-dynamic'
export const revalidate = 0
export const metadata = { title: 'Health' }

const RECENT_RUNS = 30
// Per-query settle budget. Twelve seconds is two orders of magnitude above what any of these
// ops-table reads takes when the pooler answers, and short enough that the page — and the
// deploy's 20-second /health probe — returns with the stalled query named rather than nothing.
const QUERY_BUDGET_MS = 12_000
const VALIDATOR_WINDOW_DAYS = 30

export default async function HealthPage() {
  if (!dbAvailable) return <NoDatabase />

  // EVERY QUERY IS NAMED AND BOUNDED (src/lib/result.ts). This page answered 0 bytes for a day
  // while each of these statements ran in under 0.1s one at a time — a hang, not an error, and
  // an unbounded await cannot say which of seven promises never settled. Now each has a budget:
  // a stall renders as "<name> did not answer within 12s" in its own section, and the page
  // still returns. Promise.all is kept deliberately: if the cause is the transaction pooler
  // refusing a slot, WHICH queries time out together is the fingerprint — the last one or two
  // says pool size, all seven says the pool is exhausted, one specific statement says that
  // statement. Sequencing them would hide exactly that.
  const [latest, recent, validators, history, anomalies, freshness, calls] = await Promise.all([
    attempt(getLatestRunPerScript(), { label: 'latest run per script', timeoutMs: QUERY_BUDGET_MS }),
    attempt(getPipelineRuns(RECENT_RUNS), { label: 'recent runs', timeoutMs: QUERY_BUDGET_MS }),
    attempt(getValidatorLatest(), { label: 'validators (latest)', timeoutMs: QUERY_BUDGET_MS }),
    attempt(getValidatorHistory(VALIDATOR_WINDOW_DAYS), { label: 'validators (history)', timeoutMs: QUERY_BUDGET_MS }),
    attempt(getLatestAnomalies(), { label: 'flagged metrics', timeoutMs: QUERY_BUDGET_MS }),
    attempt(getFreshnessRows(), { label: 'freshness rows', timeoutMs: QUERY_BUDGET_MS }),
    attempt(getProviderCalls(), { label: 'provider calls', timeoutMs: QUERY_BUDGET_MS }),
  ])
  const freshnessNote =
    freshness.ok && freshness.value.data_date
      ? `snapshot for EOD ${formatIsoDate(freshness.value.data_date)}, lag in SPY sessions`
      : 'lag in SPY sessions'
  const callsNote =
    calls.ok && calls.value.run_date
      ? `run date ${formatIsoDate(calls.value.run_date)}, ${calls.value.rows.reduce((n, r) => n + r.calls, 0)} calls`
      : undefined

  return (
    <div className="page">
      <PageHeader
        title="Health"
        lead="What the pipeline did, whether its gates passed, how fresh each table is, which metrics the snapshot flagged, and what the run spent of each provider's budget."
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

      <Section title="Freshness" note={freshnessNote}>
        {freshness.ok ? <FreshnessTable snapshot={freshness.value} /> : <QueryFailed error={freshness.error} />}
      </Section>

      <Section title="Flagged metrics" note="from the latest health snapshot">
        {anomalies.ok ? <AnomaliesTable snapshot={anomalies.value} /> : <QueryFailed error={anomalies.error} />}
      </Section>

      <Section title="Provider calls" note={callsNote}>
        {calls.ok ? <ProviderCallsTable snapshot={calls.value} /> : <QueryFailed error={calls.error} />}
      </Section>
    </div>
  )
}
