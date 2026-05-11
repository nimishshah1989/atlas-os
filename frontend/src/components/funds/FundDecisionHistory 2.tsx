import type { FundDecisionRow } from '@/lib/queries/funds'

function formatDecisionDate(d: Date): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const date = new Date(d)
  return `${String(date.getDate()).padStart(2, '0')}-${months[date.getMonth()]}-${date.getFullYear()}`
}

export function FundDecisionHistory({ decisions }: { decisions: FundDecisionRow[] }) {
  if (decisions.length === 0) {
    return <p className="font-sans text-sm text-ink-secondary">No decision history available</p>
  }

  return (
    <div className="overflow-x-auto border border-paper-rule rounded-sm">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule bg-paper">
            {['DATE', 'RECOMMENDATION', 'ENTRY', 'EXIT', 'REDUCE', 'WEEKS'].map(h => (
              <th
                key={h}
                className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-left whitespace-nowrap"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {decisions.map((row, i) => (
            <tr
              key={i}
              className={`border-b border-paper-rule/40 ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
            >
              <td className="px-3 py-2 font-mono text-xs text-ink-secondary whitespace-nowrap">
                {formatDecisionDate(row.date)}
              </td>
              <td className="px-3 py-2 font-sans text-xs text-ink-primary">
                {row.recommendation ?? '—'}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-ink-secondary text-center">
                {row.entry_trigger ? '●' : ''}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-ink-secondary text-center">
                {row.exit_trigger ? '●' : ''}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-ink-secondary text-center">
                {row.reduce_trigger ? '●' : ''}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-ink-secondary text-right">
                {row.weeks_in_current_state ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
