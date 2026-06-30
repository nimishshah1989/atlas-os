// FundSectorComposition — the fund's holdings rolled up to sector weights, as a simple proportion
// bar list (single calm hue, not a red→green heatmap). Top sectors shown; the long tail rolls into
// "Other". Bar width = the sector's share of the portfolio (weights are already percentages).
import type { SectorSlice } from '@/lib/v6/fundStats'

export function FundSectorComposition({ slices, topN = 12 }: { slices: SectorSlice[]; topN?: number }) {
  if (slices.length === 0) return null
  const total = slices.reduce((a, s) => a + s.weight, 0)
  const shown = slices.slice(0, topN)
  const rest = slices.slice(topN)
  const restW = rest.reduce((a, s) => a + s.weight, 0)
  const rows = restW > 0
    ? [...shown, { sector: `Other (${rest.length})`, weight: restW, count: rest.reduce((a, s) => a + s.count, 0) }]
    : shown
  return (
    <div>
      <div className="space-y-1.5">
        {rows.map((r) => (
          <div key={r.sector} className="flex items-center gap-3">
            <span className="w-[170px] shrink-0 truncate font-sans text-[12px] text-txt-2" title={r.sector}>{r.sector}</span>
            <span className="relative h-[14px] flex-1 overflow-hidden rounded-tile bg-surface-inset">
              <span className="block h-full rounded-tile bg-brand/70" style={{ width: `${Math.min(100, r.weight)}%` }} />
            </span>
            <span className="w-[48px] shrink-0 text-right font-num text-[12px] tabular-nums text-txt-1">{r.weight.toFixed(1)}%</span>
            <span className="w-[30px] shrink-0 text-right font-num text-[10px] tabular-nums text-txt-3" title="holdings in this sector">{r.count}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 font-sans text-[11px] text-txt-3">
        {slices.length} sectors · {total.toFixed(0)}% of the portfolio mapped to a sector (rest = cash / unclassified).
      </div>
    </div>
  )
}
