// src/components/health/PipelineRunsTable.tsx — a runs table (port of India's), times in ET.
import { formatDuration, formatNum, formatShortDateTime } from '@/lib/format'
import type { PipelineRun } from '@/lib/queries/health'

const DOT: Record<PipelineRun['status'], string> = {
  success: 'bg-pos',
  failed: 'bg-neg',
  running: 'bg-accent',
  queued: 'bg-ink-3',
}

export function PipelineRunsTable({ runs, empty }: { runs: PipelineRun[]; empty: string }) {
  return (
    <div className="panel overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            <th>Script</th>
            <th>Phase</th>
            <th>Started (ET)</th>
            <th className="r">Duration</th>
            <th className="r">Rows</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.run_id}>
              <td className="text-ink">{r.script_name}</td>
              <td className="text-ink-3">{r.phase ?? '—'}</td>
              <td className="num whitespace-nowrap">{formatShortDateTime(r.started_at)}</td>
              <td className="num r">{formatDuration(r.duration_seconds)}</td>
              <td className="num r">{formatNum(r.rows_written)}</td>
              <td>
                <span className="inline-flex items-center gap-2">
                  <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${DOT[r.status]}`} />
                  {r.status}
                </span>
                {r.status === 'failed' && r.error_message && (
                  <div className="mt-1 max-w-[48ch] truncate text-meta text-neg" title={r.error_message}>
                    {r.error_message}
                  </div>
                )}
              </td>
            </tr>
          ))}
          {runs.length === 0 && (
            <tr>
              <td colSpan={6} className="text-ink-3">
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
