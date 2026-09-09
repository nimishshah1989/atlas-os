// src/components/ui/CompositeNumeral.tsx — the composite as one large tabular numeral beside the
// Lens bar: the hero size (2rem) on a detail page, the card value size in a row or card. NUMERIC
// arrives as a string.
import { formatNum } from '@/lib/format'

export function CompositeNumeral({
  value,
  size = 'lg',
  label = 'Composite',
  className = '',
}: {
  value: number | string | null | undefined
  size?: 'lg' | 'md'
  label?: string
  className?: string
}) {
  const n = value == null || value === '' ? null : Number(value)
  const text = n == null || Number.isNaN(n) ? '—' : formatNum(n)
  return (
    <span
      className={`num font-serif font-semibold text-ink ${size === 'lg' ? 'text-composite' : 'text-section'} ${className}`}
      aria-label={`${label} ${text}`}
      data-composite=""
    >
      {text}
    </span>
  )
}
