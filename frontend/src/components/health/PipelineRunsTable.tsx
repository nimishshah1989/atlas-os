// frontend/src/components/health/PipelineRunsTable.tsx
import type { PipelineRun } from '@/lib/queries/health'

const STATUS_DOT: Record<PipelineRun['status'], string> = {
  success: 'bg-signal-pos',
  failed: 'bg-signal-neg',
  running: 'bg-signal-info',
}

function formatStarted(d: Date): string {
  return new Date(d).toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  })
}

function formatDuration(s: number | null): string {
  if (s == null) return '—'
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}m ${r}s`
}

function formatRows(n: number | null): string {
  if (n == null) return '—'
  return n.toLocaleString('en-IN')
}

export function PipelineRunsTable({
  runs,
  title,
}: {
  runs: PipelineRun[]
  title?: string
}) {
  return (
    <div className="px-6 py-5 border-b border-paper-rule">
      <h2 className="font-sans text-xs font-medium text-ink-3 uppercase tracking-[0.22em] mb-3">
        {title ?? `Pipeline runs · last ${runs.length}`}
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left font-sans text-[10px] font-semibold tracking-[0.18em] uppercase text-ink-3 border-b border-ink-rule">
              <th className="py-2 pr-4">Script</th>
              <th className="py-2 pr-4">Phase</th>
              <th className="py-2 pr-4">Started (IST)</th>
              <th className="py-2 pr-4 text-right">Duration</th>
              <th className="py-2 pr-4 text-right">Rows</th>
              <th className="py-2 pl-4">Status</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr
                key={r.run_id}
                className="border-b border-paper-rule hover:bg-paper-soft"
              >
                <td className="py-2 pr-4 font-sans text-[13px]">{r.script_name}</td>
                <td className="py-2 pr-4 font-sans text-[12px] text-ink-3">
                  {r.phase ?? '—'}
                </td>
                <td className="py-2 pr-4 font-mono text-[12px] tabular-nums">
                  {formatStarted(r.started_at)}
                </td>
                <td className="py-2 pr-4 font-mono text-[12px] tabular-nums text-right">
                  {formatDuration(r.duration_seconds)}
                </td>
                <td className="py-2 pr-4 font-mono text-[12px] tabular-nums text-right">
                  {formatRows(r.rows_written)}
                </td>
                <td className="py-2 pl-4">
                  <span className="inline-flex items-center gap-2 font-sans text-[11px]">
                    <span
                      className={`w-2 h-2 rounded-full ${STATUS_DOT[r.status]}`}
                    />
                    {r.status}
                  </span>
                </td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={6} className="py-3 font-sans text-sm text-ink-3">
                  No pipeline runs recorded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
