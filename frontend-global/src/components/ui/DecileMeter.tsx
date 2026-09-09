// src/components/ui/DecileMeter.tsx — the ten-segment decile glyph, ported from India's
// frontend/src/components/ui/DecileMeter.tsx so a decile reads the same on both boards.
//
// WHY A METER AND NOT JUST THE NUMBER. A chip prints "7" and a reader has to remember that seven
// is out of ten and that ten is best. A meter shows the position on the scale without being read,
// which is the whole point on a table of two thousand rows: the eye finds the full bars.
//
// COLOUR IS THE SECOND CHANNEL, NEVER THE ONLY ONE (src/lib/scores.ts). The meter is always shown
// beside the number, never instead of it, so the board survives greyscale, colour blindness and a
// screenshot pasted into a deck. Filled cells take the decile's own step off the `--decile-1..10`
// ramp in globals.css; empty cells are inset wells, so an unranked row reads as ten empty wells
// rather than as decile zero — there is no decile zero (rule #0).
import { decileColour } from '@/lib/scores'

const SIZES = {
  sm: { h: 7, w: 3, gap: 1.5 },
  md: { h: 10, w: 4, gap: 2 },
  lg: { h: 14, w: 6, gap: 2.5 },
} as const

export type MeterSize = keyof typeof SIZES

export function DecileMeter({
  decile,
  size = 'sm',
  title,
}: {
  decile: number | string | null | undefined
  size?: MeterSize
  /** The population the decile was cut in — the sentence the glyph is shorthand for. */
  title?: string
}) {
  const d = SIZES[size]
  const colour = decileColour(decile)
  const n = colour === null ? null : Math.round(Number(decile))
  return (
    <span
      className="inline-flex items-center align-middle"
      style={{ gap: d.gap }}
      role="img"
      aria-label={n == null ? 'Not ranked' : `Decile ${n} of 10`}
      title={title}
    >
      {Array.from({ length: 10 }, (_, i) => {
        const on = n != null && i < n
        return (
          <span
            key={i}
            style={{
              height: d.h,
              width: d.w,
              borderRadius: 1,
              background: on ? (colour as string) : 'var(--color-inset)',
              boxShadow: on ? undefined : 'inset 0 0 0 1px var(--color-hair)',
            }}
          />
        )
      })}
    </span>
  )
}
