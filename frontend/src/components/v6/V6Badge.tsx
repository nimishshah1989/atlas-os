// src/components/v6/V6Badge.tsx
// Compact v6 status badge for stock detail pages.
// Renders: IN BOOK / TOP PICK / EXCLUDED (reason) / BENCH HOLD / NOT IN UNIVERSE.

import type { V6BadgeStatus } from '@/lib/queries/v6'
import Link from 'next/link'

type Props = { status: V6BadgeStatus; symbol: string }

export function V6Badge({ status, symbol }: Props) {
  if (status.state === 'NOT_IN_UNIVERSE') return null

  const baseClass =
    'inline-flex items-center gap-1.5 px-2.5 py-1 border rounded-[2px] font-sans text-[11px] uppercase tracking-wide'

  if (status.state === 'IN_BOOK') {
    return (
      <Link
        href={`/strategies/v6/picks/${symbol}`}
        className={`${baseClass} bg-emerald-50 text-emerald-900 border-emerald-200 hover:border-emerald-400 transition-colors`}
      >
        <span className="font-semibold">v6: In Book</span>
        <span className="text-emerald-700">·</span>
        <span className="font-mono">{status.weight_pct.toFixed(1)}%</span>
        <span className="text-emerald-700">·</span>
        <span className="font-mono">composite {status.composite.toFixed(2)}</span>
      </Link>
    )
  }

  if (status.state === 'TOP_PICK') {
    return (
      <Link
        href={`/strategies/v6/picks/${symbol}`}
        className={`${baseClass} bg-amber-50 text-amber-900 border-amber-200 hover:border-amber-400 transition-colors`}
      >
        <span className="font-semibold">v6: Top Pick</span>
        <span className="text-amber-700">·</span>
        <span className="font-mono">rank {status.rank}</span>
        <span className="text-amber-700">·</span>
        <span className="font-mono">composite {status.composite.toFixed(2)}</span>
      </Link>
    )
  }

  if (status.state === 'EXCLUDED') {
    return (
      <Link
        href="/strategies/v6/exclusions"
        className={`${baseClass} bg-rose-50 text-rose-900 border-rose-200 hover:border-rose-400 transition-colors`}
        title={status.reason}
      >
        <span className="font-semibold">v6: Excluded</span>
        <span className="text-rose-700">·</span>
        <span className="font-sans normal-case text-rose-800">{status.reason}</span>
      </Link>
    )
  }

  return (
    <span className={`${baseClass} bg-stone-50 text-stone-700 border-stone-200`}>
      <span>v6: Bench Hold</span>
      <span className="text-stone-500">·</span>
      <span className="font-mono">composite {status.composite.toFixed(2)}</span>
    </span>
  )
}
