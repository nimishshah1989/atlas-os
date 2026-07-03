// FundSectorHistory — how the fund's sector mix has shifted over its last few disclosed holdings
// snapshots. A sector × snapshot-date table (sector left-aligned, every other column centered), with
// a Δ column = latest − earliest weight so the shift is explicit. Top sectors shown; tail → "Other".
import type { SectorHistory } from '@/lib/fundStats'

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const fmtDate = (d: string) => {
  const [, m, dd] = d.split('-')
  return `${dd} ${MON[Number(m) - 1] ?? '?'}`
}
const fmtW = (w: number | null) => (w == null ? '·' : `${w.toFixed(1)}`)
const firstLast = (ws: (number | null)[]) => {
  const present = ws.map((w, i) => ({ w, i })).filter((x) => x.w != null) as { w: number; i: number }[]
  if (present.length < 2) return null
  return present[present.length - 1].w - present[0].w
}
const deltaTone = (d: number | null) =>
  d == null ? 'text-txt-3' : d >= 0.5 ? 'text-sig-pos' : d <= -0.5 ? 'text-sig-neg' : 'text-txt-2'

export function FundSectorHistory({ history, topN = 12 }: { history: SectorHistory; topN?: number }) {
  const { dates, rows } = history
  if (dates.length < 2 || rows.length === 0) return null

  // top N by latest weight; roll the tail into a single "Other" row (sum per date).
  const shown = rows.slice(0, topN)
  const tail = rows.slice(topN)
  if (tail.length) {
    const weights = dates.map((_, i) => {
      const vals = tail.map((r) => r.weights[i]).filter((v): v is number => v != null)
      return vals.length ? vals.reduce((a, b) => a + b, 0) : null
    })
    shown.push({ sector: `Other (${tail.length})`, weights })
  }

  return (
    <div className="overflow-x-auto">
      <table className="tbl-centered w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-rule">
            <th className="px-2 pb-2 text-left font-sans text-[10px] uppercase tracking-wider text-txt-3">Sector</th>
            {dates.map((d) => (
              <th key={d} className="px-2 pb-2 text-center font-sans text-[10px] uppercase tracking-wider text-txt-3 whitespace-nowrap">{fmtDate(d)}</th>
            ))}
            <th className="px-2 pb-2 text-center font-sans text-[10px] uppercase tracking-wider text-txt-3">Δ</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => {
            const delta = firstLast(r.weights)
            return (
              <tr key={r.sector} className="border-b border-edge-hair">
                <td className="max-w-[180px] truncate px-2 py-1.5 text-left font-sans text-[12px] text-txt-1">{r.sector}</td>
                {r.weights.map((w, i) => (
                  <td key={i} className="px-2 py-1.5 text-center font-num text-[12px] tabular-nums text-txt-2">{fmtW(w)}</td>
                ))}
                <td className={`px-2 py-1.5 text-center font-num text-[12px] tabular-nums ${deltaTone(delta)}`}>
                  {delta == null ? '·' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}`}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="mt-2 font-sans text-[11px] text-txt-3">
        Weights are % of the portfolio at each disclosed snapshot. Δ = latest − earliest. A dot (·) = the fund did not hold the sector in that snapshot.
      </div>
    </div>
  )
}
