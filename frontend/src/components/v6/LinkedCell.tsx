// frontend/src/components/v6/LinkedCell.tsx
// Linker primitive for matrix cells.

import Link from 'next/link'
import type { Tier, Tenure } from '@/lib/api/v1'

type Props = {
  tier: Tier
  tenure: Tenure
  direction: 'POSITIVE' | 'NEGATIVE'
  className?: string
  /** Optional override text — defaults to "Large 3m POSITIVE" style. */
  children?: React.ReactNode
}

export function LinkedCell({ tier, tenure, direction, className = '', children }: Props) {
  const cellId = `${tier}-${tenure}-${direction}`
  const label = children ?? `${tier} ${tenure} ${direction}`
  return (
    <Link
      href={`/matrix/${encodeURIComponent(cellId)}`}
      className={`text-ink-primary hover:text-teal hover:underline transition-colors ${className}`}
    >
      {label}
    </Link>
  )
}

export function LinkedCellById({ cellId, className = '', children }: { cellId: string; className?: string; children?: React.ReactNode }) {
  return (
    <Link
      href={`/matrix/${encodeURIComponent(cellId)}`}
      className={`text-ink-primary hover:text-teal hover:underline transition-colors ${className}`}
    >
      {children ?? cellId}
    </Link>
  )
}
