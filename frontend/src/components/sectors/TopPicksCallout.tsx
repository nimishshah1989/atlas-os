// frontend/src/components/sectors/TopPicksCallout.tsx
'use client'
import { Sparkles } from 'lucide-react'
import type { StockRow } from '@/lib/queries/sector-deep-dive'

function pct(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

export function TopPicksCallout({ stocks }: { stocks: StockRow[] }) {
  // Selection: investable + Overweight RS + sorted by rs_pctile_3m desc, top 5
  const picks = stocks
    .filter(s =>
      s.is_investable === true
      && s.rs_state === 'Overweight_RS'
      && s.rs_pctile_3m != null
    )
    .sort((a, b) => {
      const av = a.rs_pctile_3m != null ? parseFloat(a.rs_pctile_3m) : -Infinity
      const bv = b.rs_pctile_3m != null ? parseFloat(b.rs_pctile_3m) : -Infinity
      return bv - av
    })
    .slice(0, 5)

  if (picks.length === 0) {
    const noDecisionData = stocks.every(s => s.market_gate == null)
    const marketOff = stocks.some(s => s.market_gate === false)
    const reason = noDecisionData
      ? 'Decision pipeline data not available for this sector.'
      : marketOff
        ? 'Market regime is Risk-Off — no deployment currently.'
        : 'No stocks have sufficient momentum (Improving / Accelerating) to pass all 6 investability gates right now.'
    return (
      <div className="px-4 py-3 border border-paper-rule bg-paper-rule/10 rounded-sm">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-3.5 h-3.5 text-ink-tertiary" />
          <span className="font-sans text-xs font-semibold text-ink-secondary uppercase tracking-wider">
            Top Picks
          </span>
        </div>
        <p className="font-sans text-xs text-ink-tertiary">{reason}</p>
      </div>
    )
  }

  return (
    <div className="px-4 py-3 border border-signal-pos/30 bg-signal-pos/5 rounded-sm">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Sparkles className="w-3.5 h-3.5 text-signal-pos" />
          <span className="font-sans text-xs font-semibold text-signal-pos uppercase tracking-wider">
            Top Picks
          </span>
          <span className="font-sans text-[11px] text-ink-tertiary">
            investable · Overweight RS · ranked by 3M RS percentile
          </span>
        </div>
        <span className="font-sans text-[11px] text-ink-tertiary">{picks.length} of {stocks.length}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
        {picks.map(p => (
          <div key={p.instrument_id} className="px-3 py-2 bg-paper border border-paper-rule rounded-sm">
            <div className="font-sans text-sm font-semibold text-ink-primary truncate" title={p.company_name}>
              {p.symbol}
            </div>
            <div className="font-sans text-[10px] text-ink-tertiary truncate mb-2" title={p.company_name}>
              {p.company_name}
            </div>
            <div className="flex items-center justify-between font-mono text-[11px]">
              <span className="text-ink-tertiary">RS pct</span>
              <span className="font-semibold text-signal-pos">
                {p.rs_pctile_3m != null ? `${(parseFloat(p.rs_pctile_3m) * 100).toFixed(0)}` : '—'}
              </span>
            </div>
            <div className="flex items-center justify-between font-mono text-[11px]">
              <span className="text-ink-tertiary">3M ret</span>
              <span className={parseFloat(p.ret_3m ?? '0') >= 0 ? 'text-signal-pos' : 'text-signal-neg'}>
                {pct(p.ret_3m)}
              </span>
            </div>
            <div className="flex items-center justify-between font-mono text-[11px]">
              <span className="text-ink-tertiary">Pos size</span>
              <span className="font-semibold text-ink-primary">
                {p.position_size_pct != null ? `${(parseFloat(p.position_size_pct) * 100).toFixed(2)}%` : '—'}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
