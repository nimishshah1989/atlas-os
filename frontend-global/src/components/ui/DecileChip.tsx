// src/components/ui/DecileChip.tsx — a peer decile, 1 (weakest) to 10 (strongest), on the muted
// ramp shared with India (`--decile-N` in globals.css, theme-scoped). Deciles only.

export function DecileChip({ decile, className = '' }: { decile: number | string | null | undefined; className?: string }) {
  const n = decile == null || decile === '' ? NaN : Math.round(Number(decile))
  if (!Number.isInteger(n) || n < 1 || n > 10) {
    return <span className={`num text-meta text-ink-3 ${className}`}>—</span>
  }
  return (
    <span
      className={`decile-chip num ${className}`}
      style={{ backgroundColor: `var(--decile-${n})` }}
      aria-label={`Decile ${n} of 10`}
      data-decile={n}
    >
      {n}
    </span>
  )
}
