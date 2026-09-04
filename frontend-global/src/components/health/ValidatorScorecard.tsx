// src/components/health/ValidatorScorecard.tsx — latest result per validator plus its pass rate
// over the window (port of India's scorecard, minus the sparkline until there is history).
import { formatNum, formatShortDateTime } from '@/lib/format'
import type { ValidatorRun } from '@/lib/queries/health'

export function ValidatorScorecard({
  latest,
  history,
  windowDays,
}: {
  latest: ValidatorRun[]
  history: ValidatorRun[]
  windowDays: number
}) {
  const passRate = (validator: string): string => {
    const runs = history.filter((r) => r.validator === validator)
    if (runs.length === 0) return '—'
    const passes = runs.filter((r) => r.status === 'PASS').length
    return `${formatNum((passes / runs.length) * 100, 1)}% of ${runs.length}`
  }

  return (
    <div className="panel overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>
            <th>Validator</th>
            <th className="r">Checks passed</th>
            <th>Latest</th>
            <th className="r">Pass rate, {windowDays} days</th>
            <th>Ran (ET)</th>
          </tr>
        </thead>
        <tbody>
          {latest.map((v) => (
            <tr key={v.validator}>
              <td className="text-ink">{v.validator}</td>
              <td className="num r">
                {formatNum(v.total_checks - v.failures)} of {formatNum(v.total_checks)}
              </td>
              <td className={v.status === 'PASS' ? 'text-pos' : 'text-neg'}>{v.status}</td>
              <td className="num r">{passRate(v.validator)}</td>
              <td className="num whitespace-nowrap">{formatShortDateTime(v.ran_at)}</td>
            </tr>
          ))}
          {latest.length === 0 && (
            <tr>
              <td colSpan={5} className="text-ink-3">
                No validator results yet. validate_global writes one row per check group when the nightly run reaches
                its gates.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
