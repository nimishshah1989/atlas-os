// src/components/countries/RsCell.tsx — one relative-strength cell of the country grid.
//
// The number is the ADR-0002 RELATIVE form, (1+r_country)/(1+r_spy) − 1: what the market did
// AFTER taking the S&P out. +0.08 means it beat the S&P by eight percent over that window, not
// that it rose eight percent. That distinction is the whole point of the grid — an investor
// choosing a country is choosing it INSTEAD of the American default.
//
// COLOUR IS THE SECOND CHANNEL, NEVER THE ONLY ONE. The value is printed in every cell, so the
// grid is readable in greyscale, by a colour-blind reader, and in a screenshot pasted into a
// deck. The tint is there to make the shape of a row visible at a glance; it carries no
// information the text does not.
//
// The tint is `rsTint` — the one ramp every relative-strength cell on the board uses (src/lib/tone.ts
// holds the ceiling and the curve). This cell used to carry its own copy of the constant, which is
// how two surfaces drift apart.
import { rsTint } from '@/lib/scores'

export function RsCell({ value, first = false }: { value: string | null; first?: boolean }) {
  // `first` draws the rule that separates the relative-strength band from the score band, the
  // same single hairline Atlas India uses between its Return and RS groups.
  const edge = first ? 'border-l border-rule ' : ''
  const n = value === null ? null : Number(value)
  if (n === null || !Number.isFinite(n)) {
    // An em dash, not a zero. A window a fund is too young to have is not a flat one.
    return <td className={`${edge}px-3 py-2 text-right text-table text-ink-3`}>—</td>
  }
  return (
    <td className={`${edge}px-3 py-2 text-right text-table tabular-nums text-ink`} style={{ backgroundColor: rsTint(value) }}>
      {n >= 0 ? '+' : '−'}
      {(Math.abs(n) * 100).toFixed(1)}%
    </td>
  )
}
