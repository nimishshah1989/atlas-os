'use client'
import type { StockRowWithSector } from '@/lib/queries/stocks'

export function SignalCell({ row }: { row: StockRowWithSector }) {
  const p = row.rs_pctile_3m != null ? Math.round(parseFloat(row.rs_pctile_3m) * 100) : null
  const pColor = p != null ? (p >= 75 ? 'text-signal-pos' : p < 25 ? 'text-signal-neg' : 'text-ink-secondary') : 'text-ink-tertiary'
  const isS2 = row.above_30w_ma === true
  const mom = row.momentum_state
  const vol = row.volume_state
  const risk = row.risk_state
  const momCls: Record<string, string> = { Accelerating: 'text-signal-pos', Improving: 'text-signal-pos', Flat: 'text-ink-secondary', Deteriorating: 'text-signal-neg', Collapsing: 'text-signal-neg' }
  const volCls: Record<string, string> = { Accumulation: 'text-signal-pos', 'Steady-Buying': 'text-signal-pos', Neutral: 'text-ink-tertiary', Distribution: 'text-signal-neg', 'Heavy Distribution': 'text-signal-neg' }
  const momFull: Record<string, string> = { Accelerating: 'Accelerating', Improving: 'Improving', Flat: 'Flat', Deteriorating: 'Deteriorating', Collapsing: 'Collapsing' }
  const volFull: Record<string, string> = { Accumulation: 'Accumulation', 'Steady-Buying': 'Steady Buying', Neutral: 'Neutral', Distribution: 'Distribution', 'Heavy Distribution': 'Heavy Dist.' }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="font-sans text-[9px] text-ink-tertiary w-8 shrink-0">RS</span>
        {p != null
          ? <span className={`font-mono text-[10px] font-semibold ${pColor}`}>{p}th%</span>
          : <span className="font-mono text-[10px] text-ink-tertiary">—</span>}
      </div>
      <div className="flex items-center gap-2">
        <span className="font-sans text-[9px] text-ink-tertiary w-8 shrink-0">Stage</span>
        <span className={`font-mono text-[10px] font-medium px-1 rounded ${isS2 ? 'bg-teal/10 text-teal' : 'text-ink-tertiary'}`}>
          {isS2 ? 'Stage 2' : 'Below MA'}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="font-sans text-[9px] text-ink-tertiary w-8 shrink-0">Mom</span>
        {mom
          ? <span className={`font-mono text-[10px] font-medium ${momCls[mom] ?? 'text-ink-secondary'}`}>{momFull[mom] ?? mom}</span>
          : <span className="font-mono text-[10px] text-ink-tertiary">—</span>}
      </div>
      <div className="flex items-center gap-2">
        <span className="font-sans text-[9px] text-ink-tertiary w-8 shrink-0">Vol</span>
        {vol
          ? <span className={`font-mono text-[10px] font-medium ${volCls[vol] ?? 'text-ink-secondary'}`}>{volFull[vol] ?? vol}</span>
          : <span className="font-mono text-[10px] text-ink-tertiary">—</span>}
      </div>
      {(risk === 'High' || risk === 'Elevated') && (
        <div className="flex items-center gap-2">
          <span className="font-sans text-[9px] text-ink-tertiary w-8 shrink-0">Risk</span>
          <span className={`font-mono text-[10px] font-bold ${risk === 'High' ? 'text-signal-neg' : 'text-amber-500'}`}>
            {risk === 'High' ? '⚠ High' : 'Elevated'}
          </span>
        </div>
      )}
    </div>
  )
}
