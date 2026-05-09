'use client'

import { ThresholdsView } from '../thresholds/ThresholdsView'
import type { ThresholdRow, RecentRunRow } from '@/lib/queries/thresholds'

type Props = { thresholds: ThresholdRow[]; recentRuns: RecentRunRow[] }

export function AdvancedTab({ thresholds, recentRuns }: Props) {
  // Group by category — same logic as the M13 page.tsx
  const byCategory = thresholds.reduce<Record<string, ThresholdRow[]>>((acc, t) => {
    acc[t.category] = acc[t.category] ?? []
    acc[t.category].push(t)
    return acc
  }, {})
  const CATEGORY_ORDER = ['rs', 'momentum', 'risk', 'volume', 'gate', 'sector', 'regime', 'fund', 'decision', 'etf']
  const sortedCategories = Object.keys(byCategory).sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a)
    const bi = CATEGORY_ORDER.indexOf(b)
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
  })

  return <ThresholdsView byCategory={byCategory} sortedCategories={sortedCategories} recentRuns={recentRuns} />
}
