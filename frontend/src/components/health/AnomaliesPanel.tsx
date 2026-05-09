// frontend/src/components/health/AnomaliesPanel.tsx
import type { AnomalyRow } from '@/lib/queries/health'

const SEV_STYLE: Record<NonNullable<AnomalyRow['severity']>, string> = {
  critical: 'border-l-signal-neg bg-signal-neg-soft text-signal-neg-strong',
  warn: 'border-l-signal-warn bg-signal-warn-soft text-signal-warn-strong',
  info: 'border-l-signal-info bg-signal-info-soft text-signal-info-strong',
}

const SEV_LABEL: Record<NonNullable<AnomalyRow['severity']>, string> = {
  critical: 'CRITICAL',
  warn: 'WARN',
  info: 'INFO',
}

function formatPct(v: number | null): string {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : '−' // U+2212 minus
  return `${sign}${(Math.abs(v) * 100).toFixed(1)}%`
}

function formatZ(z: number | null): string {
  if (z == null) return '—'
  const sign = z >= 0 ? '+' : '−'
  return `z=${sign}${Math.abs(z).toFixed(2)}`
}

function formatVal(v: number | null): string {
  if (v == null) return '—'
  if (Math.abs(v) >= 1000) return v.toLocaleString('en-IN')
  if (Math.abs(v) < 1 && v !== 0) return v.toFixed(4)
  return v.toFixed(2)
}

export function AnomaliesPanel({ anomalies }: { anomalies: AnomalyRow[] }) {
  return (
    <div className="px-6 py-5 border-b border-paper-rule">
      <h2 className="font-sans text-xs font-medium text-ink-3 uppercase tracking-[0.22em] mb-3">
        Anomalies · today vs yesterday + 14-day average
      </h2>
      {anomalies.length === 0 ? (
        <div className="font-sans text-sm text-signal-pos">
          ✓ No anomalies detected.
        </div>
      ) : (
        <ul className="space-y-2">
          {anomalies.map((a) => {
            const sev = a.severity ?? 'info'
            return (
              <li
                key={`${a.table_name}-${a.metric_name}`}
                className={`border-l-4 px-3 py-2 ${SEV_STYLE[sev]}`}
              >
                <div className="flex items-baseline justify-between gap-4">
                  <div>
                    <span className="font-sans text-[10px] font-semibold tracking-[0.18em] mr-2">
                      {SEV_LABEL[sev]}
                    </span>
                    <span className="font-mono text-[12px]">
                      {a.table_name} · {a.metric_name}
                    </span>
                  </div>
                  <div className="font-mono text-[12px] tabular-nums">
                    {formatVal(a.value_today)}{' '}
                    <span className="text-ink-4">←</span>{' '}
                    {formatVal(a.value_prior_day)}
                    {a.pct_change_dod !== null && (
                      <span className="ml-2">({formatPct(a.pct_change_dod)})</span>
                    )}
                    {a.z_score !== null && (
                      <span className="ml-2 text-ink-3">{formatZ(a.z_score)}</span>
                    )}
                  </div>
                </div>
                {a.notes && (
                  <div className="font-sans text-[11px] text-ink-3 mt-1">{a.notes}</div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
