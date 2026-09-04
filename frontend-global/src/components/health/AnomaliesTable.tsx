// src/components/health/AnomaliesTable.tsx — metrics the health snapshot flagged on its latest date.
import { formatIsoDate, formatNum } from '@/lib/format'
import type { AnomalySnapshot } from '@/lib/queries/health'

const SEVERITY: Record<string, string> = { critical: 'text-neg', warn: 'text-warn', info: 'text-ink-2' }

export function AnomaliesTable({ snapshot }: { snapshot: AnomalySnapshot }) {
  const { data_date, rows } = snapshot
  return (
    <div className="panel overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            <th>Table</th>
            <th>Metric</th>
            <th className="r">Today</th>
            <th className="r">Prior day</th>
            <th className="r">Change</th>
            <th className="r">z</th>
            <th>Severity</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={`${a.table_name}:${a.metric_name}`}>
              <td className="text-ink">{a.table_name}</td>
              <td>{a.metric_name}</td>
              <td className="num r">{formatNum(a.value_today, 2)}</td>
              <td className="num r">{formatNum(a.value_prior_day, 2)}</td>
              <td className="num r">{a.pct_change_dod == null ? '—' : `${formatNum(a.pct_change_dod, 1)}%`}</td>
              <td className="num r">{formatNum(a.z_score, 2)}</td>
              <td className={SEVERITY[a.severity ?? ''] ?? 'text-ink-3'}>{a.severity ?? '—'}</td>
              <td className="max-w-[40ch] text-ink-2">{a.notes ?? ''}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={8} className="text-ink-3">
                {data_date
                  ? `Nothing flagged on the ${formatIsoDate(data_date)} snapshot.`
                  : 'No health snapshot yet. write_health_snapshot adds one row per tracked metric at the end of the nightly run.'}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
