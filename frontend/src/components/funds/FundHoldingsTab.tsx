import type { FundHoldingRow } from '@/lib/queries/funds'

const RS_STYLE: Record<string, string> = {
  Leader:   'bg-teal/20 text-teal',
  Strong:   'bg-signal-pos/20 text-signal-pos',
  Average:  'bg-paper-rule/40 text-ink-secondary',
  Weak:     'bg-signal-neg/10 text-signal-neg',
  Laggard:  'bg-signal-neg/20 text-signal-neg',
}

const MOM_STYLE: Record<string, string> = {
  Accelerating:  'text-signal-pos',
  Improving:     'text-signal-pos/70',
  Flat:          'text-ink-tertiary',
  Deteriorating: 'text-signal-neg/70',
  Collapsing:    'text-signal-neg',
}

const RISK_STYLE: Record<string, string> = {
  Low:           'text-signal-pos',
  Normal:        'text-ink-secondary',
  Elevated:      'text-signal-warn',
  High:          'text-signal-neg',
  'Below Trend': 'text-signal-neg',
}

function pctStr(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function weightStr(v: string | null): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(1)}%`
}

function StateBadge({ state, styleMap }: { state: string | null; styleMap: Record<string, string> }) {
  if (!state) return <span className="text-ink-tertiary">—</span>
  const cls = styleMap[state] ?? 'text-ink-secondary'
  return <span className={`font-sans text-[11px] font-medium ${cls}`}>{state}</span>
}

export function FundHoldingsTab({ holdings }: { holdings: FundHoldingRow[] }) {
  if (holdings.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          No holdings data available. Fund disclosures are typically delayed 30–60 days.
        </p>
      </div>
    )
  }

  const holdingsDate = holdings[0]?.holdings_date
  const strongCount = holdings.filter(h => h.rs_state === 'Leader' || h.rs_state === 'Strong').length
  const weakCount = holdings.filter(h => h.rs_state === 'Weak' || h.rs_state === 'Laggard').length

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-6 font-sans text-xs text-ink-secondary">
        <span>Top <span className="font-semibold text-ink-primary">{holdings.length}</span> holdings</span>
        <span className="text-signal-pos font-semibold">{strongCount} Leader/Strong</span>
        <span className="text-signal-neg font-semibold">{weakCount} Weak/Laggard</span>
        {holdingsDate && (
          <span className="ml-auto text-ink-tertiary text-[10px]">
            Holdings as of{' '}
            {new Date(holdingsDate).toLocaleDateString('en-IN', {
              day: '2-digit', month: 'short', year: 'numeric',
            }).replace(',', '')}
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full font-sans text-xs border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Stock</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Sector</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Weight</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">RS State</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Momentum</th>
              <th className="px-3 py-2 text-left font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">Risk</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">1M</th>
              <th className="px-3 py-2 text-right font-semibold text-ink-tertiary uppercase tracking-wider text-[10px]">3M</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h, i) => (
              <tr key={h.symbol ?? i} className="border-b border-paper-rule/50 hover:bg-paper-rule/10 transition-colors">
                <td className="px-3 py-2.5">
                  <div className="font-semibold text-ink-primary">{h.symbol ?? '—'}</div>
                  {h.company_name && (
                    <div className="text-[10px] text-ink-tertiary truncate max-w-[140px]">{h.company_name}</div>
                  )}
                </td>
                <td className="px-3 py-2.5 text-ink-secondary">{h.sector ?? '—'}</td>
                <td className="px-3 py-2.5 text-right font-mono font-semibold text-ink-primary">{weightStr(h.weight)}</td>
                <td className="px-3 py-2.5">
                  {h.rs_state ? (
                    <span className={`px-1.5 py-0.5 rounded-[2px] text-[10px] font-semibold ${RS_STYLE[h.rs_state] ?? 'bg-paper-rule/30 text-ink-secondary'}`}>
                      {h.rs_state}
                    </span>
                  ) : <span className="text-ink-tertiary">—</span>}
                </td>
                <td className="px-3 py-2.5"><StateBadge state={h.momentum_state} styleMap={MOM_STYLE} /></td>
                <td className="px-3 py-2.5"><StateBadge state={h.risk_state} styleMap={RISK_STYLE} /></td>
                <td className={`px-3 py-2.5 text-right font-mono ${h.ret_1m != null && parseFloat(h.ret_1m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pctStr(h.ret_1m)}
                </td>
                <td className={`px-3 py-2.5 text-right font-mono ${h.ret_3m != null && parseFloat(h.ret_3m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                  {pctStr(h.ret_3m)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
