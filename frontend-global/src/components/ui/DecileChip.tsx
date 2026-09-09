// src/components/ui/DecileChip.tsx — a peer decile, 1 (weakest) to 10 (strongest), on the ramp
// `--decile-N` in globals.css (neg → amber → pos). The chip names its step as `--decile`; the
// stylesheet draws ink on a tint of it with the step as the border. Deciles only.
import type { CSSProperties } from 'react'

export function DecileChip({ decile, className = '' }: { decile: number | string | null | undefined; className?: string }) {
  const n = decile == null || decile === '' ? NaN : Math.round(Number(decile))
  if (!Number.isInteger(n) || n < 1 || n > 10) {
    return <span className={`num text-meta text-ink-3 ${className}`}>—</span>
  }
  return (
    <span
      className={`decile-chip num ${className}`}
      style={{ '--decile': `var(--decile-${n})` } as CSSProperties}
      aria-label={`Decile ${n} of 10`}
      data-decile={n}
    >
      {n}
    </span>
  )
}
