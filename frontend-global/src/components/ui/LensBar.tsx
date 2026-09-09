// src/components/ui/LensBar.tsx — the one memorable element (docs/global/frontend-design.md §2.1).
// A proportional bar: each segment's WIDTH is its lens weight and its FILL is that lens's score
// (0–100). An absent lens (score null) is an empty track, so a reader sees at once which lenses
// contributed. Identical on every row, card and detail page; the composite numeral sits beside it.
import { formatNum } from '@/lib/format'

export type LensSegment = {
  key: string
  label?: string
  /** Blend weight (a fraction, e.g. 0.35). Widths are proportional within the bar. */
  weight: number
  /** 0–100, or null when the lens is absent for this instrument. */
  score: number | null
}

type Size = 'sm' | 'lg'

const HEIGHT: Record<Size, number> = { sm: 10, lg: 18 }

const clamp = (n: number) => Math.min(100, Math.max(0, n))

function describe(segments: LensSegment[]): string {
  return segments
    .map((s) => `${s.label ?? s.key} ${s.score == null ? 'absent' : formatNum(s.score)}`)
    .join(', ')
}

export function LensBar({
  segments,
  size = 'sm',
  animate = false,
  className = '',
}: {
  segments: LensSegment[]
  size?: Size
  /** Fill from empty on mount — the detail page's first paint (240 ms, reduced-motion aware). */
  animate?: boolean
  className?: string
}) {
  const total = segments.reduce((sum, s) => sum + (s.weight > 0 ? s.weight : 0), 0)
  const flexOf = (s: LensSegment) => `${total > 0 ? s.weight / total : 1} 1 0%`

  return (
    <div className={`w-full ${className}`} role="img" aria-label={describe(segments)} data-lens-bar={size}>
      <div className="flex w-full gap-[2px]" style={{ height: HEIGHT[size] }}>
        {segments.map((s) => (
          <div
            key={s.key}
            data-lens-segment={s.key}
            data-lens-weight={s.weight}
            className="relative overflow-hidden bg-inset"
            style={{ flex: flexOf(s) }}
            title={`${s.label ?? s.key}: weight ${formatNum(s.weight * 100)}%, ${
              s.score == null ? 'absent' : `score ${formatNum(s.score)}`
            }`}
          >
            {s.score != null && (
              <div
                data-lens-fill=""
                className={`absolute inset-y-0 left-0 bg-accent ${animate ? 'lens-fill--animate' : ''}`}
                style={{ width: `${clamp(s.score)}%` }}
              />
            )}
          </div>
        ))}
      </div>
      {size === 'lg' && (
        <div className="mt-1 flex w-full gap-[2px] text-meta text-ink-3">
          {segments.map((s) => (
            <div key={s.key} className="num truncate" style={{ flex: flexOf(s) }}>
              {s.label ?? s.key}
              {s.score != null && <span className="ml-1 text-ink-2">{formatNum(s.score)}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
