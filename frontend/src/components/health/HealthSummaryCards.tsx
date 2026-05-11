// frontend/src/components/health/HealthSummaryCards.tsx
import type { ValidatorRun } from '@/lib/queries/health'

const VALIDATORS = ['M3', 'M4', 'M5'] as const

function ValidatorCard({ validator, run }: { validator: string; run: ValidatorRun | undefined }) {
  if (!run) {
    return (
      <div className="border border-paper-rule rounded p-4">
        <div className="font-sans text-[10px] font-semibold tracking-[0.2em] text-ink-3 uppercase mb-2">
          {validator}
        </div>
        <div className="font-mono text-[11px] text-ink-3">No data</div>
      </div>
    )
  }

  const pass = run.status === 'PASS'
  const pct =
    run.total_checks > 0
      ? Math.round(((run.total_checks - run.failures) / run.total_checks) * 100)
      : 100

  return (
    <div
      className={`border rounded p-4 ${
        pass ? 'border-signal-pos-rule bg-signal-pos-soft' : 'border-signal-neg-rule bg-signal-neg-soft'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="font-sans text-[10px] font-semibold tracking-[0.2em] text-ink-3 uppercase">
          Validator {validator}
        </span>
        <span
          className={`inline-flex items-center gap-1 font-mono text-[10px] font-semibold uppercase tracking-wider ${
            pass ? 'text-signal-pos-strong' : 'text-signal-neg-strong'
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${pass ? 'bg-signal-pos' : 'bg-signal-neg'}`}
          />
          {run.status}
        </span>
      </div>
      <div className="font-mono text-2xl font-medium tabular-nums text-ink-primary">
        {pct}%
      </div>
      <div className="font-sans text-[11px] text-ink-3 mt-1 tabular-nums">
        {run.total_checks - run.failures}/{run.total_checks} checks passed
        {run.failures > 0 && (
          <span className="text-signal-neg-strong ml-1">· {run.failures} failed</span>
        )}
      </div>
    </div>
  )
}

export function HealthSummaryCards({
  validators,
  staleTables,
  recentFailures,
  anomalyCount,
}: {
  validators: ValidatorRun[]
  staleTables: number
  recentFailures: number
  anomalyCount: number
}) {
  const validatorMap = Object.fromEntries(validators.map((v) => [v.validator, v]))

  return (
    <div className="px-6 py-5 border-b border-paper-rule">
      <h2 className="font-sans text-xs font-medium text-ink-3 uppercase tracking-[0.22em] mb-4">
        System scorecard
      </h2>

      {/* Validator row */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        {VALIDATORS.map((v) => (
          <ValidatorCard key={v} validator={v} run={validatorMap[v]} />
        ))}
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-3 gap-3">
        <div
          className={`border rounded p-4 ${
            anomalyCount === 0
              ? 'border-signal-pos-rule bg-signal-pos-soft'
              : 'border-signal-neg-rule bg-signal-neg-soft'
          }`}
        >
          <div className="font-sans text-[10px] font-semibold tracking-[0.2em] text-ink-3 uppercase mb-2">
            Anomalies (today)
          </div>
          <div
            className={`font-mono text-2xl font-medium tabular-nums ${
              anomalyCount === 0 ? 'text-signal-pos-strong' : 'text-signal-neg-strong'
            }`}
          >
            {anomalyCount}
          </div>
          <div className="font-sans text-[11px] text-ink-3 mt-1">
            {anomalyCount === 0 ? 'No anomalies flagged' : 'flagged by health check'}
          </div>
        </div>

        <div
          className={`border rounded p-4 ${
            staleTables === 0
              ? 'border-signal-pos-rule bg-signal-pos-soft'
              : 'border-signal-neg-rule bg-signal-neg-soft'
          }`}
        >
          <div className="font-sans text-[10px] font-semibold tracking-[0.2em] text-ink-3 uppercase mb-2">
            Stale tables
          </div>
          <div
            className={`font-mono text-2xl font-medium tabular-nums ${
              staleTables === 0 ? 'text-signal-pos-strong' : 'text-signal-neg-strong'
            }`}
          >
            {staleTables}
          </div>
          <div className="font-sans text-[11px] text-ink-3 mt-1">
            {staleTables === 0 ? 'All tables fresh' : 'tables lagging >2 days'}
          </div>
        </div>

        <div
          className={`border rounded p-4 ${
            recentFailures === 0
              ? 'border-signal-pos-rule bg-signal-pos-soft'
              : 'border-signal-warn-rule bg-signal-warn-soft'
          }`}
        >
          <div className="font-sans text-[10px] font-semibold tracking-[0.2em] text-ink-3 uppercase mb-2">
            Pipeline failures (last 30)
          </div>
          <div
            className={`font-mono text-2xl font-medium tabular-nums ${
              recentFailures === 0 ? 'text-signal-pos-strong' : 'text-signal-warn-strong'
            }`}
          >
            {recentFailures}
          </div>
          <div className="font-sans text-[11px] text-ink-3 mt-1">
            {recentFailures === 0 ? 'No recent failures' : 'failed runs in log'}
          </div>
        </div>
      </div>
    </div>
  )
}
