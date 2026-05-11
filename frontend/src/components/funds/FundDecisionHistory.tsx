import type { FundDecisionRow } from '@/lib/queries/funds'

function formatDecisionDate(d: Date): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const date = new Date(d)
  return `${String(date.getDate()).padStart(2, '0')}-${months[date.getMonth()]}-${date.getFullYear()}`
}

function RatingBadge({ value }: { value: string | null }) {
  const colors: Record<string, string> = {
    Recommended: 'bg-signal-pos/15 text-signal-pos font-semibold',
    Hold:        'bg-signal-warn/10 text-signal-warn font-medium',
    Reduce:      'bg-signal-neg/10 text-signal-neg font-medium',
    Exit:        'bg-signal-neg/20 text-signal-neg font-semibold',
  }
  const cls = value ? (colors[value] ?? 'text-ink-tertiary') : 'text-ink-tertiary'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] ${cls}`}>
      {value ?? '—'}
    </span>
  )
}

type GateKey = 'performance_gate' | 'sectors_gate' | 'stocks_gate' | 'market_gate'
const GATE_LABELS: Record<GateKey, string> = {
  performance_gate: 'Perf',
  sectors_gate:     'Sectors',
  stocks_gate:      'Holdings',
  market_gate:      'Market',
}

function GateRow({ row }: { row: FundDecisionRow }) {
  const gates: GateKey[] = ['performance_gate', 'sectors_gate', 'stocks_gate', 'market_gate']
  const failing = gates.filter(g => row[g] === false)
  const passing = gates.filter(g => row[g] === true)
  if (failing.length === 0 && passing.length === 4) {
    return <span className="font-sans text-[10px] text-signal-pos">All 4 gates passing</span>
  }
  return (
    <div className="flex flex-wrap gap-2 items-center">
      {failing.map(g => (
        <span key={g} className="inline-flex items-center gap-0.5 font-sans text-[10px] text-signal-neg">
          <span className="font-bold">✗</span> {GATE_LABELS[g]}
        </span>
      ))}
      {passing.map(g => (
        <span key={g} className="inline-flex items-center gap-0.5 font-sans text-[10px] text-ink-tertiary/60">
          ✓ {GATE_LABELS[g]}
        </span>
      ))}
    </div>
  )
}

function hasTrigger(row: FundDecisionRow): boolean {
  return !!(row.entry_trigger || row.exit_trigger || row.reduce_trigger || row.add_trigger)
}

function TriggerBadges({ row }: { row: FundDecisionRow }) {
  if (!hasTrigger(row)) return null
  return (
    <div className="flex gap-1 mt-0.5">
      {row.entry_trigger  && <span className="px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-pos/15 text-signal-pos">ENTRY</span>}
      {row.add_trigger    && <span className="px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-pos/10 text-signal-pos">ADD</span>}
      {row.reduce_trigger && <span className="px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-warn/15 text-signal-warn">REDUCE</span>}
      {row.exit_trigger   && <span className="px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-neg/15 text-signal-neg">EXIT</span>}
    </div>
  )
}

type Period = { from: FundDecisionRow; to: FundDecisionRow; count: number }

function stateKey(row: FundDecisionRow): string {
  return [row.recommendation, row.performance_gate, row.sectors_gate, row.stocks_gate, row.market_gate].join('|')
}

function collapsePeriods(decisions: FundDecisionRow[]): Period[] {
  if (decisions.length === 0) return []
  const periods: Period[] = []
  let current: Period = { from: decisions[0], to: decisions[0], count: 1 }
  for (let i = 1; i < decisions.length; i++) {
    const row = decisions[i]
    if (stateKey(row) === stateKey(current.from) && !hasTrigger(row) && !hasTrigger(current.from)) {
      current.to = row
      current.count++
    } else {
      periods.push(current)
      current = { from: row, to: row, count: 1 }
    }
  }
  periods.push(current)
  return periods
}

export function FundDecisionHistory({ decisions }: { decisions: FundDecisionRow[] }) {
  if (decisions.length === 0) {
    return <p className="font-sans text-sm text-ink-secondary">No decision history available</p>
  }

  const periods = collapsePeriods(decisions)

  return (
    <div>
      <p className="font-sans text-[11px] text-ink-tertiary mb-3">
        Identical consecutive days collapsed into one row. A trigger event always starts a new row.
      </p>
      <div className="space-y-px">
        {periods.map((period, i) => {
          const sameDay = formatDecisionDate(period.from.date) === formatDecisionDate(period.to.date)
          return (
            <div
              key={i}
              className={`flex items-start gap-3 px-3 py-2 rounded-sm ${
                hasTrigger(period.from)
                  ? 'bg-signal-warn/5 border border-signal-warn/20'
                  : 'hover:bg-paper-rule/10'
              }`}
            >
              <div className="w-52 shrink-0">
                <div className="font-mono text-[10px] text-ink-secondary whitespace-nowrap">
                  {formatDecisionDate(period.from.date)}
                  {!sameDay && (
                    <span className="text-ink-tertiary/50"> → {formatDecisionDate(period.to.date)}</span>
                  )}
                </div>
                {period.count > 1 && (
                  <div className="font-sans text-[9px] text-ink-tertiary/50 mt-0.5">{period.count} days</div>
                )}
              </div>
              <div className="w-24 shrink-0 pt-0.5">
                <RatingBadge value={period.from.recommendation} />
                <TriggerBadges row={period.from} />
              </div>
              <div className="flex-1 pt-0.5">
                <GateRow row={period.from} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
