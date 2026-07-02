// The signature glyph: a 10-segment decile meter. Recurs everywhere a score
// appears so the whole product reads as one calibrated instrument. Filled cells
// take the decile's ramp colour (with a faint glow); empty cells are inset wells.
import { decileColor } from './decile'

const SIZES = {
  sm: { h: 8, w: 4, gap: 2 },
  md: { h: 11, w: 6, gap: 2.5 },
  lg: { h: 15, w: 7, gap: 3 },
} as const

export function DecileMeter({ decile, size = 'md' }: { decile: number | null; size?: keyof typeof SIZES }) {
  const d = SIZES[size]
  const color = decileColor(decile)
  return (
    <span className="inline-flex items-center" style={{ gap: d.gap }} aria-hidden="true">
      {Array.from({ length: 10 }, (_, i) => {
        const on = decile != null && i < decile
        return (
          <span
            key={i}
            style={{
              height: d.h,
              width: d.w,
              borderRadius: 1.5,
              background: on ? color : 'var(--color-surface-inset)',
              boxShadow: on ? undefined : 'inset 0 0 0 1px var(--color-edge-rule)',
            }}
          />
        )
      })}
    </span>
  )
}
