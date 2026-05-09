'use client'
// src/app/portfolios/[id]/CompositionView.tsx
// Composition view for portfolio detail — Static (instrument table)
// or Rule-Based (narrative from config JSONB + M16 placeholder).

type StaticInstrument = {
  instrument_id: string
  instrument_type: 'stock' | 'etf' | 'fund'
  weight_pct: number
}

export function StaticComposition({ instruments }: { instruments: StaticInstrument[] }) {
  if (instruments.length === 0) {
    return <p className="font-sans text-sm text-ink-tertiary">No instruments recorded.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-paper-rule">
            {['ID / Ticker', 'Type', 'Weight %'].map((col) => (
              <th key={col} className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {instruments.map((inst) => (
            <tr key={inst.instrument_id} className="border-b border-paper-rule/50">
              <td className="py-2 pr-4 font-mono text-xs text-ink-primary">{inst.instrument_id}</td>
              <td className="py-2 pr-4 font-sans text-xs text-ink-secondary capitalize">
                {inst.instrument_type}
              </td>
              <td className="py-2 font-mono text-sm text-right">
                {inst.weight_pct.toFixed(2)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function RuleBasedComposition({ config }: { config: Record<string, unknown> }) {
  const parts: string[] = []

  const rsFilter = config.rs_state_filter
  if (Array.isArray(rsFilter) && rsFilter.length > 0) {
    parts.push(`rs_state ∈ {${(rsFilter as string[]).join(', ')}}`)
  }

  const regimeFilter = config.regime_state_filter
  if (Array.isArray(regimeFilter) && regimeFilter.length > 0) {
    parts.push(`regime ∈ {${(regimeFilter as string[]).join(', ')}}`)
  }

  const breadthGate = config.breadth_gate as Record<string, number> | undefined
  if (breadthGate) {
    for (const [field, threshold] of Object.entries(breadthGate)) {
      parts.push(`${field} ≥ ${threshold}`)
    }
  }

  return (
    <div className="space-y-3">
      {parts.length > 0 ? (
        <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-2">
            Entry rules
          </p>
          <p className="font-mono text-sm text-ink-primary">
            Holds stocks where {parts.join(' AND ')}
          </p>
        </div>
      ) : (
        <p className="font-sans text-sm text-ink-tertiary">No rules configured.</p>
      )}
      <div className="border border-paper-rule rounded-[2px] p-4 bg-paper/50">
        <p className="font-sans text-sm text-ink-tertiary">
          Holdings will appear after the first nightly run (M16).
        </p>
      </div>
    </div>
  )
}
