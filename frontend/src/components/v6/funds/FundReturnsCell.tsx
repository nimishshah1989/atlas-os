// FundReturnsCell — compact ABSOLUTE NAV total-return block for a fund, over 1W/1M/3M/6M/12M.
// Laid out in TWO rows (like the RS matrix cell) so the values don't crowd: short windows on the
// top row (1W/1M/3M), longer windows below (6M/12M). Green = positive, red = negative.
import type { FundReturns } from '@/lib/queries/v6/fund_metrics'

const ROWS: { key: keyof FundReturns; label: string }[][] = [
  [{ key: 'w1', label: '1W' }, { key: 'm1', label: '1M' }, { key: 'm3', label: '3M' }],
  [{ key: 'm6', label: '6M' }, { key: 'm12', label: '12M' }],
]

const tone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0.005 ? 'text-sig-pos' : v <= -0.005 ? 'text-sig-neg' : 'text-txt-2'
const pct = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)

function Cell({ w, ret }: { w: { key: keyof FundReturns; label: string }; ret: FundReturns }) {
  return (
    <span className="flex flex-col items-center leading-tight" title={`${w.label} NAV return: ${pct(ret[w.key])}`}>
      <span className="font-num text-[8px] uppercase tracking-wide text-txt-3">{w.label}</span>
      <span className={`font-num text-[10px] tabular-nums ${tone(ret[w.key])}`}>{pct(ret[w.key])}</span>
    </span>
  )
}

export function FundReturnsCell({ ret }: { ret?: FundReturns }) {
  if (!ret || ret.m3 == null) return <span className="font-num text-[11px] text-txt-3">—</span>
  return (
    <div className="inline-flex flex-col gap-y-0.5">
      {ROWS.map((row, i) => (
        <div key={i} className="grid grid-cols-3 items-center justify-items-center gap-x-2.5">
          {row.map((w) => <Cell key={w.key} w={w} ret={ret} />)}
        </div>
      ))}
    </div>
  )
}
