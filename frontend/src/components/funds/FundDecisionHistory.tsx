import type { FundDecisionRow } from '@/lib/queries/funds'

function fmt(d: Date): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const date = new Date(d)
  return `${String(date.getDate()).padStart(2, '0')}-${months[date.getMonth()]}-${date.getFullYear()}`
}

function RatingBadge({ value }: { value: string | null }) {
  const colors: Record<string, string> = {
    Recommended: 'bg-signal-pos/15 text-signal-pos font-semibold',
    Hold: 'bg-signal-warn/10 text-signal-warn font-medium',
    Reduce: 'bg-signal-neg/10 text-signal-neg font-medium',
    Exit: 'bg-signal-neg/20 text-signal-neg font-semibold',
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
  sectors_gate: 'Sectors',
  stocks_gate: 'Holdings',
  market_gate: 'Market',
}
const GATE_DESCRIPTIONS: Record<GateKey, string> = {
  performance_gate: 'Performance gate: fund return vs category over 3 months',
  sectors_gate: 'Sectors gate: sector composition quality vs index',
  stocks_gate: 'Holdings gate: individual stock RS state quality',
  market_gate: 'Market gate: broad market regime allows investment',
}

function GateRow({ row }: { row: FundDecisionRow }) {
  const gates: GateKey[] = ['performance_gate', 'sectors_gate', 'stocks_gate', 'market_gate']
  const failing = gates.filter((g) => row[g] === false)
  const passing = gates.filter((g) => row[g] === true)
  if (failing.length === 0 && passing.length === 4) {
    return (
      <span className="font-sans text-[10px] text-signal-pos">All 4 gates passing</span>
    )
  }
  return (
    <div className="flex flex-wrap gap-2 items-center">
      {failing.map((g) => (
        <span
          key={g}
          className="inline-flex items-center gap-0.5 font-sans text-[10px] text-signal-neg"
          title={GATE_DESCRIPTIONS[g]}
        >
          <span className="font-bold">✗</span> {GATE_LABELS[g]}
        </span>
      ))}
      {passing.map((g) => (
        <span
          key={g}
          className="inline-flex items-center gap-0.5 font-sans text-[10px] text-ink-tertiary/60"
          title={GATE_DESCRIPTIONS[g]}
        >
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
    <div className="flex gap-1 mt-1">
      {row.entry_trigger && (
        <span
          className="px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-pos/15 text-signal-pos"
          title="Entry signal triggered — all 4 gates passing"
        >
          ENTRY
        </span>
      )}
      {row.add_trigger && (
        <span
          className="px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-pos/10 text-signal-pos"
          title="Add signal triggered — strong gates, can increase position"
        >
          ADD
        </span>
      )}
      {row.reduce_trigger && (
        <span
          className="px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-warn/15 text-signal-warn"
          title="Reduce signal triggered — gates deteriorating, trim position"
        >
          REDUCE
        </span>
      )}
      {row.exit_trigger && (
        <span
          className="px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-neg/15 text-signal-neg"
          title="Exit signal triggered — gates failing, consider full exit"
        >
          EXIT
        </span>
      )}
    </div>
  )
}

type Period = { from: FundDecisionRow; to: FundDecisionRow; count: number }

function stateKey(row: FundDecisionRow): string {
  return [
    row.recommendation,
    row.performance_gate,
    row.sectors_gate,
    row.stocks_gate,
    row.market_gate,
  ].join('|')
}

function collapsePeriods(decisions: FundDecisionRow[]): Period[] {
  if (decisions.length === 0) return []
  const asc = [...decisions].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  )
  const periods: Period[] = []
  let current: Period = { from: asc[0], to: asc[0], count: 1 }
  for (let i = 1; i < asc.length; i++) {
    const row = asc[i]
    if (
      stateKey(row) === stateKey(current.from) &&
      !hasTrigger(row) &&
      !hasTrigger(current.from)
    ) {
      current.to = row
      current.count++
    } else {
      periods.push(current)
      current = { from: row, to: row, count: 1 }
    }
  }
  periods.push(current)
  return periods.reverse()
}

export function FundDecisionHistory({ decisions }: { decisions: FundDecisionRow[] }) {
  if (decisions.length === 0) {
    return <p className="font-sans text-sm text-ink-secondary">No decision history available.</p>
  }

  const periods = collapsePeriods(decisions)

  return (
    <div>
      <p className="font-sans text-[11px] text-ink-tertiary mb-4">
        Each row is a distinct state. Identical consecutive days are collapsed. A trigger event
        (Entry/Add/Reduce/Exit) always starts a new row. Gates must all pass for an Entry trigger.
      </p>

      <div className="relative pl-6">
        {/* Continuous vertical line */}
        <div className="absolute left-[9px] top-2 bottom-2 w-px bg-paper-rule" />

        <div className="space-y-0">
          {periods.map((period, i) => {
            const trigger = hasTrigger(period.from)
            const sameDay = fmt(period.from.date) === fmt(period.to.date)
            const isLatest = i === 0

            return (
              <div key={i} className="relative flex items-start gap-3 pb-3">
                {/* Timeline node */}
                <div
                  className={`absolute -left-[3px] mt-2 w-3 h-3 rounded-full border-2 shrink-0 z-10 ${
                    trigger
                      ? 'bg-signal-warn border-signal-warn'
                      : isLatest
                        ? 'bg-teal border-teal'
                        : 'bg-paper border-paper-rule'
                  }`}
                />

                {/* Card */}
                <div
                  className={`flex-1 flex items-start gap-3 px-3 py-2 rounded-sm transition-colors ${
                    trigger
                      ? 'bg-signal-warn/5 border border-signal-warn/20'
                      : isLatest
                        ? 'bg-teal/5 border border-teal/20'
                        : 'hover:bg-paper-rule/5 border border-transparent'
                  }`}
                >
                  {/* Date range */}
                  <div className="w-48 shrink-0">
                    <div className="font-mono text-[10px] text-ink-secondary whitespace-nowrap">
                      {fmt(period.from.date)}
                      {!sameDay && (
                        <span className="text-ink-tertiary/50"> → {fmt(period.to.date)}</span>
                      )}
                    </div>
                    {period.count > 1 && (
                      <div className="font-sans text-[9px] text-ink-tertiary/50 mt-0.5">
                        {period.count} days
                      </div>
                    )}
                  </div>

                  {/* Recommendation + triggers */}
                  <div className="w-28 shrink-0">
                    <RatingBadge value={period.from.recommendation} />
                    <TriggerBadges row={period.from} />
                  </div>

                  {/* Gate status */}
                  <div className="flex-1">
                    <GateRow row={period.from} />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="mt-2 pl-6 font-sans text-[10px] text-ink-tertiary space-y-0.5">
        <p>Gates: Perf = performance vs category · Sectors = sector quality · Holdings = individual stock states · Market = regime</p>
        <p>Teal dot = latest state · Orange dot = action trigger fired</p>
      </div>
    </div>
  )
}
