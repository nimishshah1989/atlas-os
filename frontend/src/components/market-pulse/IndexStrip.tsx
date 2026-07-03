// Broad-market index strip — opens the page with "where the market is": level + 1d/1w/1m.
import type { IndexQuote } from '@/lib/queries/market_pulse'

const fmtLvl = (n: number | null) => (n == null ? '—' : n.toLocaleString('en-IN', { maximumFractionDigits: 0 }))
const fmtPct = (n: number | null) => (n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`)
const tone = (n: number | null) => (n == null ? 'var(--color-txt-3)' : n > 0 ? 'var(--color-sig-pos)' : n < 0 ? 'var(--color-sig-neg)' : 'var(--color-txt-2)')

export function IndexStrip({ quotes }: { quotes: IndexQuote[] }) {
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
      {quotes.map((q) => (
        <div key={q.code} className="rounded-tile border border-edge-rule bg-surface-raised px-3.5 py-2.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-sans text-[11px] font-medium text-txt-2">{q.label}</span>
            <span className="font-num text-[12px] tabular-nums" style={{ color: tone(q.d1) }}>{fmtPct(q.d1)}</span>
          </div>
          <div className="mt-1 font-num text-[20px] font-semibold leading-none tabular-nums text-txt-1">{fmtLvl(q.close)}</div>
          <div className="mt-1.5 flex gap-3 font-num text-[10px] tabular-nums text-txt-3">
            <span>1w <span style={{ color: tone(q.d1w) }}>{fmtPct(q.d1w)}</span></span>
            <span>1m <span style={{ color: tone(q.d1m) }}>{fmtPct(q.d1m)}</span></span>
          </div>
        </div>
      ))}
    </div>
  )
}
