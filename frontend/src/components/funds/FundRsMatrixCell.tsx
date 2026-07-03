// FundRsMatrixCell — a compact relative-strength matrix for a fund: NAV return minus index return
// over 1m/3m/6m/12m, against Nifty 50 and Nifty 500 (the same baselines as stock RS; the fund's
// stated TR benchmark isn't in our price data). Green = the fund beat the index over that window,
// red = it lagged. Hover any cell for the exact RS plus the underlying fund/index returns.
import type { FundRsMatrix } from '@/lib/queries/fund_metrics'

const WINDOWS: { key: 'm1' | 'm3' | 'm6' | 'm12'; label: string }[] = [
  { key: 'm1', label: '1m' }, { key: 'm3', label: '3m' }, { key: 'm6', label: '6m' }, { key: 'm12', label: '12m' },
]

// RS (a fraction) → text colour. Beating the index reads green, lagging reads red; flat is muted.
function tone(rs: number | null): string {
  if (rs == null) return 'text-txt-3'
  if (rs >= 0.005) return 'text-sig-pos'
  if (rs <= -0.005) return 'text-sig-neg'
  return 'text-txt-2'
}
const pct = (v: number | null, signed = true) =>
  v == null ? '—' : `${signed && v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`

function Row({ label, rs, ret, baseline }: { label: string; rs: FundRsMatrix['n50']; ret: FundRsMatrix['ret']; baseline: string }) {
  return (
    <>
      <span className="pr-1 text-right font-num text-[8px] uppercase tracking-wide text-txt-3">{label}</span>
      {WINDOWS.map((w) => {
        const v = rs[w.key]
        const r = ret[w.key]
        const idx = v != null && r != null ? r - v : null // index return = fund return − RS
        return (
          <span
            key={w.key}
            title={`${w.label} RS vs ${baseline}: ${pct(v)}  (fund ${pct(r, false)} − ${baseline} ${pct(idx, false)})`}
            className={`text-center font-num text-[10px] tabular-nums ${tone(v)}`}
          >
            {v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(0)}%`}
          </span>
        )
      })}
    </>
  )
}

export function FundRsMatrixCell({ rs }: { rs?: FundRsMatrix }) {
  if (!rs || rs.ret.m3 == null) return <span className="font-num text-[11px] text-txt-3">—</span>
  return (
    <div className="inline-grid grid-cols-[auto_repeat(4,1fr)] items-center justify-items-center gap-x-2 gap-y-0.5">
      <span />
      {WINDOWS.map((w) => (
        <span key={w.key} className="text-center font-num text-[8px] uppercase tracking-wide text-txt-3">{w.label}</span>
      ))}
      <Row label="N50" rs={rs.n50} ret={rs.ret} baseline="Nifty 50" />
      <Row label="N500" rs={rs.n500} ret={rs.ret} baseline="Nifty 500" />
    </div>
  )
}
