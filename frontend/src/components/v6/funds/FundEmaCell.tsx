// FundEmaCell — within-fund trend breadth: how many of the fund's holdings trade above their
// 21/50/200-day EMA. A high count near the short EMA (21) with a high long-EMA (200) count = a
// portfolio of names in healthy uptrends. Coloured green→muted by the share above each EMA; hover
// for the count and share of priced holdings.
import type { FundEma } from '@/lib/queries/v6/fund_metrics'

const BARS: { key: 'a21' | 'a50' | 'a200'; label: string }[] = [
  { key: 'a21', label: '21' }, { key: 'a50', label: '50' }, { key: 'a200', label: '200' },
]

function tone(share: number): string {
  if (share >= 0.6) return 'text-sig-pos'
  if (share >= 0.4) return 'text-txt-2'
  return 'text-sig-neg'
}

export function FundEmaCell({ ema }: { ema?: FundEma }) {
  if (!ema || ema.n_priced === 0) return <span className="font-num text-[11px] text-txt-3">—</span>
  const n = ema.n_priced
  return (
    <div className="inline-flex items-center gap-2">
      {BARS.map((b) => {
        const c = ema[b.key]
        const share = n > 0 ? c / n : 0
        return (
          <span key={b.key} title={`${c} of ${n} holdings above the ${b.label}-day EMA (${Math.round(share * 100)}%)`}
            className="font-num text-[11px] tabular-nums">
            <span className="text-txt-3">{b.label}</span>{' '}
            <span className={tone(share)}>{c}</span>
          </span>
        )
      })}
    </div>
  )
}
