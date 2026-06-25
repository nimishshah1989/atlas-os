// SectorBreadthTable — compact table form of sector EMA participation (replaces the
// card grid; occupies less space, all numbers filled). Sorted by %>EMA20 desc.
import type { SectorBreadthMVRow } from '@/lib/queries/v6/sectors'

const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`)
const heat = (v: number | null) => {
  if (v == null) return 'text-txt-3'
  const p = v * 100
  return p >= 60 ? 'text-sig-pos' : p >= 40 ? 'text-txt-2' : 'text-sig-neg'
}

export function SectorBreadthTable({ rows }: { rows: SectorBreadthMVRow[] }) {
  if (rows.length === 0) {
    return <div className="py-6 text-center font-sans text-sm text-txt-3">Breadth data unavailable.</div>
  }
  const sorted = [...rows].sort((a, b) => (b.pct_above_ema20 ?? -1) - (a.pct_above_ema20 ?? -1))
  return (
    <table className="w-full text-right" data-testid="sector-breadth-table">
      <thead>
        <tr className="font-num text-[10px] text-txt-3 uppercase tracking-wider border-b border-edge-rule">
          <th className="text-left py-1.5 font-semibold">Sector</th>
          <th className="py-1.5 font-semibold">Stocks</th>
          <th className="py-1.5 font-semibold">&gt; EMA20</th>
          <th className="py-1.5 font-semibold">&gt; EMA50</th>
          <th className="py-1.5 font-semibold">&gt; EMA200</th>
          <th className="text-left py-1.5 font-semibold pl-6">Top movers</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map(r => (
          <tr key={r.sector_name} className="border-b border-edge-hair">
            <td className="text-left py-1.5 font-sans text-xs text-txt-1">
              <a href={`/sectors/${encodeURIComponent(r.sector_name)}`} className="text-txt-1 no-underline hover:text-brand hover:underline">
                {r.sector_name}
              </a>
            </td>
            <td className="py-1.5 font-num text-[11px] tabular-nums text-txt-3">{r.constituent_count}</td>
            <td className={`py-1.5 font-num text-xs tabular-nums ${heat(r.pct_above_ema20)}`}>{pct(r.pct_above_ema20)}</td>
            <td className={`py-1.5 font-num text-xs tabular-nums ${heat(r.pct_above_ema50)}`}>{pct(r.pct_above_ema50)}</td>
            <td className={`py-1.5 font-num text-xs tabular-nums ${heat(r.pct_above_ema200)}`}>{pct(r.pct_above_ema200)}</td>
            <td className="text-left py-1.5 pl-6">
              <span className="flex flex-wrap gap-x-2">
                {r.top_movers.slice(0, 3).map(m => (
                  <span key={m.symbol} className="font-num text-[10px] tabular-nums text-sig-pos">{m.symbol} +{m.ret_pct.toFixed(1)}%</span>
                ))}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
