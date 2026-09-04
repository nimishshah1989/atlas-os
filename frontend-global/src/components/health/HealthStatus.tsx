// src/components/health/HealthStatus.tsx — the headline in words, then four quiet tiles.
import { FreshnessStamp } from '@/components/ui/FreshnessStamp'
import { formatNum } from '@/lib/format'
import type { AnomalySnapshot, PipelineRun, ValidatorRun } from '@/lib/queries/health'
import type { Result } from '@/lib/result'

function headline(recent: Result<PipelineRun[]>): { text: string; tone: string } {
  if (!recent.ok) return { text: 'The database did not answer', tone: 'text-neg' }
  const last = recent.value[0]
  if (!last) return { text: 'No pipeline run yet', tone: 'text-ink-2' }
  switch (last.status) {
    case 'failed':
      return { text: `Last run failed in ${last.script_name}`, tone: 'text-neg' }
    case 'running':
      return { text: `A run is in progress: ${last.script_name}`, tone: 'text-ink' }
    case 'queued':
      return { text: `A run is queued: ${last.script_name}`, tone: 'text-ink' }
    default:
      return { text: 'Last run succeeded', tone: 'text-pos' }
  }
}

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="tile">
      <div className="text-meta text-ink-3">{label}</div>
      <div className="num mt-1 text-section text-ink">{value}</div>
      {detail && <div className="mt-1 text-meta text-ink-2">{detail}</div>}
    </div>
  )
}

export function HealthStatus({
  latest,
  recent,
  validators,
  anomalies,
}: {
  latest: Result<PipelineRun[]>
  recent: Result<PipelineRun[]>
  validators: Result<ValidatorRun[]>
  anomalies: Result<AnomalySnapshot>
}) {
  const h = headline(recent)
  const scripts = latest.ok ? latest.value.length : null
  const recentRuns = recent.ok ? recent.value : []
  const failures = recent.ok ? recentRuns.filter((r) => r.status === 'failed').length : null
  const passing = validators.ok ? validators.value.filter((v) => v.status === 'PASS').length : null
  const flagged = anomalies.ok ? anomalies.value.rows.length : null
  const nOrDash = (n: number | null) => (n == null ? '—' : formatNum(n))

  return (
    <div className="panel px-5 py-4">
      <div className={`font-serif text-section ${h.tone}`}>{h.text}</div>
      <div className="mt-1">
        <FreshnessStamp size="lg" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Scripts with a run" value={nOrDash(scripts)} />
        <Tile
          label={`Failures in the last ${formatNum(recentRuns.length)} runs`}
          value={nOrDash(failures)}
        />
        <Tile
          label="Validators passing"
          value={validators.ok ? `${formatNum(passing)} of ${formatNum(validators.value.length)}` : '—'}
        />
        <Tile
          label="Metrics flagged"
          value={nOrDash(flagged)}
          detail={anomalies.ok && anomalies.value.data_date ? `snapshot ${anomalies.value.data_date}` : undefined}
        />
      </div>
    </div>
  )
}
