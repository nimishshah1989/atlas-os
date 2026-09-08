// src/components/health/FreshnessTable.tsx — the snapshot's lag per tracked table, in SPY sessions
// (blank while ohlcv_daily holds no SPY bar — the row's note says so). Tolerance and tier come from
// freshness_guard's registries through the writer; nothing here adds a threshold.
import { formatNum, formatShortDateTime } from '@/lib/format'
import type { FreshnessRow, FreshnessSnapshot } from '@/lib/queries/health'

/** fresh (green) · stale (red when it withholds publish, amber when warn-only) · no lag (grey/tier). */
function describeLag(r: Pick<FreshnessRow, 'value_today' | 'is_anomaly' | 'severity' | 'notes'>) {
  const noLag = r.value_today == null ? (r.notes?.startsWith('EMPTY') ? 'empty' : 'no SPY calendar') : null
  if (r.is_anomaly) {
    const critical = r.severity === 'critical'
    return {
      label: noLag ?? (critical ? 'stale, withholds publish' : 'stale'),
      dot: critical ? 'bg-neg' : 'bg-warn',
      text: critical ? 'text-neg' : 'text-warn',
    }
  }
  if (noLag) return { label: noLag, dot: 'bg-ink-3', text: 'text-ink-3' }
  return { label: 'fresh', dot: 'bg-pos', text: 'text-pos' }
}

export function FreshnessTable({ snapshot }: { snapshot: FreshnessSnapshot }) {
  const { rows } = snapshot
  return (
    <div className="panel overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            <th>Table</th>
            <th className="r">Lag (sessions)</th>
            <th>State</th>
            <th>Note</th>
            <th>Computed (ET)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const s = describeLag(r)
            return (
              <tr key={r.table_name} data-freshness-row={r.table_name}>
                <td className="text-ink">{r.table_name}</td>
                <td className="num r">{formatNum(r.value_today)}</td>
                <td className={s.text}>
                  <span className="inline-flex items-center gap-2">
                    <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${s.dot}`} />
                    {s.label}
                  </span>
                </td>
                <td className="max-w-[56ch] text-ink-2">{r.notes ?? ''}</td>
                <td className="num whitespace-nowrap">{formatShortDateTime(r.computed_at)}</td>
              </tr>
            )
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={5} className="text-ink-3">
                No freshness rows yet. write_health_snapshot writes one per tracked table at the end of every
                orchestrator run.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
