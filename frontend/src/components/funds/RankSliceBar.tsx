// RankSliceBar — a thin daily-slice strip of a fund's category rank over time. One vertical
// slice per trading day, coloured green (best in category) → red (worst) by the within-category
// percentile (rank-1)/(size-1). Hover a slice for its date + rank. Pure/presentational; the
// data is atlas_foundation.fund_rank_daily via getFundRankHistory.
import type { RankSlice } from '@/lib/rankHistory'

// green (best) → amber → red (worst). Continuous so the eye reads the trajectory, not buckets.
function sliceColor(rank: number, size: number): string {
  const p = size > 1 ? (rank - 1) / (size - 1) : 0 // 0 best → 1 worst
  const hue = Math.round((1 - p) * 140) // 140 = green, 0 = red
  return `hsl(${hue} 42% 52%)` // muted saturation to match the calmer RAG palette (FM feedback)
}

export function RankSliceBar({ slices, max = 60, height = 18 }: { slices: RankSlice[]; max?: number; height?: number }) {
  const shown = slices.slice(-max)
  if (shown.length === 0) return <span className="font-num text-[11px] text-txt-3">—</span>
  return (
    <div className="inline-flex items-stretch gap-px rounded-[2px]" style={{ height }} aria-hidden>
      {shown.map((s) => (
        <span
          key={s.d}
          title={`${s.d}: rank ${s.r} / ${s.s}`}
          className="w-[3px] first:rounded-l-[2px] last:rounded-r-[2px]"
          style={{ backgroundColor: sliceColor(s.r, s.s) }}
        />
      ))}
    </div>
  )
}
