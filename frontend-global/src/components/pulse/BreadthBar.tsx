// src/components/pulse/BreadthBar.tsx — "how many of them", as a bar with its own denominator.
//
// THE DENOMINATOR IS PART OF THE FACT. "312 above their 200-day average" is not a breadth reading;
// "312 of 487 measured" is. An instrument without 200 sessions has no 200-day average, so it is
// neither above nor below one — counting it as a "no" would report every young fund as weak. The
// bar's width is the share of what was MEASURED, and the caption prints both numbers so the
// reader can see how much of the population could be asked at all.
//
// Colour is the second channel: over half is the positive token, under half the negative, and the
// number is always printed beside it.
import { formatNum } from '@/lib/format'

export function BreadthBar({
  label,
  count,
  measured,
  note,
}: {
  label: string
  count: number
  /** How many rows carry the measure. Zero means nobody could be asked — not "none of them". */
  measured: number
  note?: string
}) {
  if (measured === 0) {
    return (
      <div className="grid grid-cols-[11rem_1fr_5.5rem] items-center gap-2">
        <span className="text-meta text-ink-2">{label}</span>
        <span className="text-meta text-ink-3">not measured on any member yet</span>
        <span className="num text-right text-meta text-ink-3">—</span>
      </div>
    )
  }
  const share = count / measured
  const tone = share >= 0.5 ? 'var(--color-pos)' : 'var(--color-neg)'
  return (
    <div className="grid grid-cols-[11rem_1fr_5.5rem] items-center gap-2" title={note}>
      <span className="text-meta text-ink-2">{label}</span>
      <span className="h-2.5 rounded-sm bg-inset">
        <span className="block h-2.5 rounded-sm" style={{ width: `${(share * 100).toFixed(1)}%`, background: tone }} />
      </span>
      <span className="num text-right text-meta text-ink">
        {(share * 100).toFixed(0)}%
        <span className="ml-1 text-ink-3">
          {formatNum(count)}/{formatNum(measured)}
        </span>
      </span>
    </div>
  )
}
