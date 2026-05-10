import type { FundDecisionRow } from '@/lib/queries/funds'
import { formatWeeksInState } from '@/lib/fund-formatters'

function formatDecisionDate(d: Date): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const date = new Date(d)
  return `${String(date.getDate()).padStart(2, '0')}-${months[date.getMonth()]}-${date.getFullYear()}`
}

function GateDot({ value }: { value: boolean | null }) {
  if (value === null) return <span className="font-mono text-[10px] text-ink-tertiary">?</span>
  return (
    <span className={`font-mono text-xs font-semibold ${value ? 'text-signal-pos' : 'text-signal-neg'}`}>
      {value ? '✓' : '✗'}
    </span>
  )
}

const TRIGGER_COLORS: Record<string, string> = {
  Entry:  'bg-signal-pos/15 text-signal-pos',
  Add:    'bg-signal-pos/10 text-signal-pos',
  Reduce: 'bg-signal-warn/15 text-signal-warn',
  Exit:   'bg-signal-neg/15 text-signal-neg',
}

function TriggerCell({ value, label }: { value: boolean | null; label: string }) {
  if (!value) return <span className="text-ink-tertiary/40 text-xs">—</span>
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${TRIGGER_COLORS[label] ?? ''}`}>
      {label}
    </span>
  )
}

export function FundDecisionHistory({ decisions }: { decisions: FundDecisionRow[] }) {
  if (decisions.length === 0) {
    return <p className="font-sans text-sm text-ink-secondary">No decision history available</p>
  }

  return (
    <div>
      <p className="font-sans text-[11px] text-ink-tertiary mb-3">
        Daily recommendation log. All 4 gate criteria (Performance, Sectors, Holdings, Market) must pass
        for a fund to be Recommended. A trigger badge appears only on the week the rating changes.
      </p>
      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse text-center">
          <thead>
            <tr className="border-b border-paper-rule/40 bg-paper-rule/10">
              <th colSpan={2} className="px-3 py-1" />
              <th colSpan={4} className="px-3 py-1 font-sans text-[9px] font-semibold text-ink-tertiary uppercase tracking-wider border-l border-paper-rule/40">
                Rating Change Triggers
              </th>
              <th colSpan={4} className="px-3 py-1 font-sans text-[9px] font-semibold text-ink-tertiary uppercase tracking-wider border-l border-paper-rule/40">
                Quality Gates
              </th>
              <th className="px-3 py-1" />
            </tr>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-left whitespace-nowrap">Date</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider text-left whitespace-nowrap">Rating</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap border-l border-paper-rule/40">Entry</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap">Exit</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap">Reduce</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap">Add</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap border-l border-paper-rule/40" title="NAV performance vs peers — strong uptrend required">Performance</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap" title="Sector composition — must not be Misaligned vs market">Sectors</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap" title="Portfolio holdings — must not be predominantly Weak stocks">Holdings</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap" title="Market regime — blocked in Risk-Off or Dislocation">Market</th>
              <th className="px-3 py-2 font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider whitespace-nowrap text-right">In State</th>
            </tr>
          </thead>
          <tbody>
            {decisions.map((row, i) => (
              <tr
                key={i}
                className={`border-b border-paper-rule/40 ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
              >
                <td className="px-3 py-2 font-mono text-xs text-ink-secondary whitespace-nowrap text-left">
                  {formatDecisionDate(row.date)}
                </td>
                <td className="px-3 py-2 font-sans text-xs text-ink-primary text-left">
                  {row.recommendation ?? '—'}
                </td>
                <td className="px-3 py-2 border-l border-paper-rule/40">
                  <TriggerCell value={row.entry_trigger} label="Entry" />
                </td>
                <td className="px-3 py-2">
                  <TriggerCell value={row.exit_trigger} label="Exit" />
                </td>
                <td className="px-3 py-2">
                  <TriggerCell value={row.reduce_trigger} label="Reduce" />
                </td>
                <td className="px-3 py-2">
                  <TriggerCell value={row.add_trigger} label="Add" />
                </td>
                <td className="px-3 py-2 border-l border-paper-rule/40">
                  <GateDot value={row.performance_gate} />
                </td>
                <td className="px-3 py-2">
                  <GateDot value={row.sectors_gate} />
                </td>
                <td className="px-3 py-2">
                  <GateDot value={row.stocks_gate} />
                </td>
                <td className="px-3 py-2">
                  <GateDot value={row.market_gate} />
                </td>
                <td className="px-3 py-2 font-mono text-xs text-ink-secondary text-right">
                  {formatWeeksInState(row.weeks_in_current_state)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
