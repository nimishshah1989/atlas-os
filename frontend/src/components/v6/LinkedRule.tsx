// frontend/src/components/v6/LinkedRule.tsx
// Linker primitive for cell-rule names. cellId required so we know the route.

import Link from 'next/link'

type Props = {
  cellId: string
  ruleId: string
  className?: string
  children?: React.ReactNode
}

export function LinkedRule({ cellId, ruleId, className = '', children }: Props) {
  return (
    <Link
      href={`/stocks?cell=${encodeURIComponent(cellId)}`}
      className={`font-mono text-xs text-ink-primary hover:text-teal hover:underline transition-colors ${className}`}
    >
      {children ?? ruleId}
    </Link>
  )
}
