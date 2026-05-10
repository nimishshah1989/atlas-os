// frontend/src/components/health/JipSyncPanel.tsx
import type { TableFreshness } from '@/lib/queries/health'
import { jipLagThresholdDays } from '@/lib/queries/health'

function formatDate(d: Date | null): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Kolkata',
  })
}

function lagPill(lag: number | null, threshold: number) {
  if (lag == null) {
    return <span className="font-mono text-[11px] text-ink-4 tabular-nums">—</span>
  }
  const overdue = lag > threshold
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono text-[11px] tabular-nums ${
        overdue ? 'text-signal-neg' : 'text-signal-pos'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${overdue ? 'bg-signal-neg' : 'bg-signal-pos'}`} />
      {lag}d
    </span>
  )
}

export function JipSyncPanel({ rows }: { rows: TableFreshness[] }) {
  return (
    <div className="px-6 py-5 border-b border-paper-rule">
      <h2 className="font-sans text-xs font-medium text-ink-3 uppercase tracking-[0.22em] mb-3">
        JIP source sync · public.de_*
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left font-sans text-[10px] font-semibold tracking-[0.18em] uppercase text-ink-3 border-b border-ink-rule">
              <th className="py-2 pr-4">Table</th>
              <th className="py-2 pr-4">Latest</th>
              <th className="py-2 pr-4">Lag</th>
              <th className="py-2 pl-4 text-right">Rows</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.table_name}
                className="border-b border-paper-rule hover:bg-paper-soft"
              >
                <td className="py-2 pr-4 font-mono text-[12px]">{row.table_name}</td>
                <td className="py-2 pr-4 font-mono text-[12px] tabular-nums">
                  {formatDate(row.latest_date)}
                </td>
                <td className="py-2 pr-4">
                  {lagPill(row.lag_days, jipLagThresholdDays(row.table_name))}
                </td>
                <td className="py-2 pl-4 font-mono text-[12px] tabular-nums text-right">
                  {row.row_count.toLocaleString('en-IN')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
