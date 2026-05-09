// src/app/admin/thresholds/page.tsx
// RSC — server fetches all thresholds + recent runs, hands to client island.
import { getAllThresholds, getRecentRuns } from '@/lib/queries/thresholds'
import { ThresholdsView } from './ThresholdsView'
import type { ThresholdRow, RecentRunRow } from '@/lib/queries/thresholds'

const CATEGORY_ORDER = [
  'rs', 'momentum', 'risk', 'volume', 'gate', 'sector', 'regime', 'fund', 'decision', 'etf',
]

export default async function ThresholdsPage() {
  const [thresholds, recentRuns]: [ThresholdRow[], RecentRunRow[]] = await Promise.all([
    getAllThresholds(),
    getRecentRuns(5),
  ])

  const byCategory = thresholds.reduce<Record<string, ThresholdRow[]>>((acc, t) => {
    acc[t.category] = acc[t.category] ?? []
    acc[t.category].push(t)
    return acc
  }, {})

  const sortedCategories = Object.keys(byCategory).sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a)
    const bi = CATEGORY_ORDER.indexOf(b)
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
  })

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <h1 className="font-serif text-2xl text-ink-primary">Threshold Admin</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          Methodology threshold values · {thresholds.length} rows · grouped by category
        </p>
      </header>
      <ThresholdsView
        byCategory={byCategory}
        sortedCategories={sortedCategories}
        recentRuns={recentRuns}
      />
    </main>
  )
}
