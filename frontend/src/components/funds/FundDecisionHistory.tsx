import type { FundDecisionRow } from '@/lib/queries/funds'
import { formatWeeksInState } from '@/lib/fund-formatters'

function formatDecisionDate(d: Date): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const date = new Date(d)
  return `${String(date.getDate()).padStart(2, '0')}-${months[date.getMonth()]}-${date.getFullYear()}`
}

function TriggerDot({ value }: { value: boolean | null }) {
  if (!value) return <span className="text-ink-tertiary/30">●</span>
  return <span className="text-signal-pos">●</span>
}

function GateDot({ value }: { value: boolean | null }) {
  if (value === null) return <span className="font-mono text-[10px] text-ink-tertiary">?</span>
  return (
    <span className={`font-mono text-xs font-semibold ${value ? 'text-signal-pos' : 'text-signal-neg'}`}>
      {value ? '✓' : '✗'}
    </span>
  )
}

const HEADERS = [
  { label: 'DATE', className: 'text-left' },
  { label: 'RECOMMENDATION', className: 'text-left' },
  // Triggers
  { label: 'ENTRY', className: 'text-center' },
  { label: 'EXIT', className: 'text-center' },
  { label: 'REDUCE', className: 'text-center' },
  { label: 'ADD', className: 'text-center' },
  // Gates (separated visually)
  { label: 'PERF', className: 'text-center border-l border-paper-rule/40' },
  { label: 'SEC', className: 'text-center' },
  { label: 'STKS', className: 'text-center' },
  { label: 'MKT', className: 'text-center' },
  // Tenure
  { label: 'WEEKS', className: 'text-right' },
]

export function FundDecisionHistory({ decisions }: { decisions: FundDecisionRow[] }) {
  if (decisions.length === 0) {
    return <p className="font-sans text-sm text-ink-secondary">No decision history available</p>
  }

  return (
    <div className="overflow-x-auto border border-paper-rule rounded-sm">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule bg-paper">
            {HEADERS.map(h => (
              <th
                key={h.label}
                className={`px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap ${h.className}`}
              >
                {h.label}
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
              {/* Triggers */}
              <td className="px-3 py-2 font-mono text-xs text-center">
                <TriggerDot value={row.entry_trigger} />
              </td>
              <td className="px-3 py-2 font-mono text-xs text-center">
                <TriggerDot value={row.exit_trigger} />
              </td>
              <td className="px-3 py-2 font-mono text-xs text-center">
                <TriggerDot value={row.reduce_trigger} />
              </td>
              <td className="px-3 py-2 font-mono text-xs text-center">
                <TriggerDot value={row.add_trigger} />
              </td>
              {/* Gates */}
              <td className="px-3 py-2 text-center border-l border-paper-rule/40">
                <GateDot value={row.performance_gate} />
              </td>
              <td className="px-3 py-2 text-center">
                <GateDot value={row.sectors_gate} />
              </td>
              <td className="px-3 py-2 text-center">
                <GateDot value={row.stocks_gate} />
              </td>
              <td className="px-3 py-2 text-center">
                <GateDot value={row.market_gate} />
              </td>
              {/* Tenure */}
              <td className="px-3 py-2 font-mono text-xs text-ink-secondary text-right">
                {formatWeeksInState(row.weeks_in_current_state)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
