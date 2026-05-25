// frontend/src/app/regime/page.tsx
// Regime page v6 — RegimeHero (deployment_multiplier hero) + input panels + cells.

import Link from 'next/link'
import { getCellDefinitions } from '@/lib/api/v1'
import { getRegimeDetail } from '@/lib/queries/v6/regime'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { RegimeHero } from '@/components/v6/RegimeHero'
import { RegimeInputPanel } from '@/components/v6/RegimeInputPanel'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { ELI5Tooltip } from '@/components/v6/ELI5Tooltip'
import { formatIC } from '@/lib/format-cell'

export const dynamic = 'force-dynamic'

export default async function RegimePage() {
  const snapshotDate = await getLatestSnapshotDate()
  const [detail, cellsRes] = await Promise.all([
    getRegimeDetail(),
    getCellDefinitions(),
  ])
  const cells = cellsRes.data
  const cellsById = new Map(cells.map(c => [c.cell_id, c]))

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Page header */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Market Regime
        </div>
        <h1 className="font-serif text-3xl font-semibold text-ink-primary leading-none sr-only">
          Regime: {detail.regime_state}
        </h1>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      {/* Hero — deployment_multiplier front-and-center */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <RegimeHero detail={detail} />
      </div>

      {/* Input sparklines */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Regime classifier inputs
        </h2>
        <RegimeInputPanel inputs={detail.inputs} />
      </div>

      {/* Cells favored — empty state handled gracefully */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Cells favoured under {detail.regime_state}
        </h2>
        {cells.length === 0 ? (
          <p className="font-sans text-sm text-ink-tertiary">
            Cell-to-regime mapping pending backfill. Check back after nightly run.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {cells.slice(0, 12).map(cell => (
              <Link
                key={cell.cell_id}
                href={`/v6/cells/${encodeURIComponent(cell.cell_id)}`}
                className="block border border-paper-rule rounded-[2px] bg-paper p-3 hover:bg-paper-rule/10 transition-colors"
                aria-label={`Cell: ${cell.cell_id}`}
              >
                <div className="flex items-baseline justify-between mb-1">
                  <span className="font-sans text-sm font-semibold text-ink-primary">
                    {cell.cell_id}
                  </span>
                  {cell.best_archetype && (
                    <span className="font-mono text-xs tabular-nums text-ink-tertiary">
                      {cell.grade ?? '—'}
                    </span>
                  )}
                </div>
                {cell.best_archetype && (
                  <ELI5Tooltip term={cell.best_archetype}>
                    <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
                      {cell.best_archetype}
                    </span>
                  </ELI5Tooltip>
                )}
                <p className="font-sans text-xs text-ink-secondary leading-relaxed mt-1">
                  {cell.reason ?? '—'}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Regime → Matrix → Stocks nav */}
      <div className="px-6 py-5">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Regime → Matrix → Stocks
        </h2>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed max-w-[760px] mb-3">
          The regime sets the deployment multiplier and the universe of cells worth
          firing. Each cell holds validated rules. Stocks firing those rules today
          are the live opportunity set.
        </p>
        <div className="flex gap-3">
          <Link href="/matrix" className="font-sans text-sm text-teal hover:underline">
            Full matrix →
          </Link>
          <Link href="/stocks" className="font-sans text-sm text-teal hover:underline">
            Stocks today →
          </Link>
        </div>
      </div>
    </div>
  )
}
