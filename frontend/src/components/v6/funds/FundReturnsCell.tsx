// FundReturnsCell — compact ABSOLUTE NAV total-return strip for a fund, over 1W/1M/3M/6M/12M.
// Same look as the RS matrix cell (one row, signed + coloured) so the raw return and the relative
// read sit side by side. Green = positive, red = negative.
import type { FundReturns } from '@/lib/queries/v6/fund_metrics'

const WINDOWS: { key: keyof FundReturns; label: string }[] = [
  { key: 'w1', label: '1W' }, { key: 'm1', label: '1M' }, { key: 'm3', label: '3M' },
  { key: 'm6', label: '6M' }, { key: 'm12', label: '12M' },
]

const tone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0.005 ? 'text-sig-pos' : v <= -0.005 ? 'text-sig-neg' : 'text-txt-2'
const pct = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)

export function FundReturnsCell({ ret }: { ret?: FundReturns }) {
  if (!ret || ret.m3 == null) return <span className="font-num text-[11px] text-txt-3">—</span>
  return (
    <div className="inline-grid grid-cols-5 items-center justify-items-center gap-x-2 gap-y-0.5">
      {WINDOWS.map((w) => (
        <span key={w.key} className="text-center font-num text-[8px] uppercase tracking-wide text-txt-3">{w.label}</span>
      ))}
      {WINDOWS.map((w) => (
        <span key={w.key} title={`${w.label} NAV return: ${pct(ret[w.key])}`} className={`text-center font-num text-[10px] tabular-nums ${tone(ret[w.key])}`}>
          {pct(ret[w.key])}
        </span>
      ))}
    </div>
  )
}
