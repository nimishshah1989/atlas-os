// src/app/strategies/v6/page.tsx
// v6 Trading Model — Command Center (server shell, ≤250 LOC).
// Renders against the mock query layer until Plan 2 wires real backend.
export const dynamic = 'force-dynamic'

import { getV6Book } from '@/lib/queries/v6'
import { V6CommandCenter } from './V6CommandCenter'

export default async function V6CommandCenterPage() {
  const book = await getV6Book()
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6 flex items-baseline justify-between">
        <div>
          <h1 className="font-serif text-2xl text-ink-primary">
            v6 RS Trading Model — Command Center
          </h1>
          <p className="font-sans text-xs text-ink-tertiary mt-1">
            {book.holdings.length} holdings · Gross {book.gross_exposure_pct.toFixed(1)}% ·
            Crisis sleeve {book.crisis_sleeve.total_pct.toFixed(1)}% ·
            As of {book.as_of}
          </p>
        </div>
        <div className="text-right">
          <p className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
            Goal-post
          </p>
          <p
            className={`font-mono text-sm font-semibold mt-0.5 ${
              book.goal_post.passes_all_constraints
                ? 'text-emerald-700'
                : 'text-amber-700'
            }`}
          >
            {book.goal_post.passes_all_constraints ? 'ALL PASS' : 'PARTIAL'}
          </p>
        </div>
      </header>

      <V6CommandCenter book={book} />
    </main>
  )
}
