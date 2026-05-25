// frontend/src/app/regime/page.tsx
// Full regime story v6 — RegimeIndicator hero + cells favored under regime.

import Link from 'next/link'
import { getCellDefinitions } from '@/lib/api/v1'
import { getCurrentRegime } from '@/lib/queries/v6/regime'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { RegimeIndicator } from '@/components/v6/RegimeIndicator'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { LinkedCellById } from '@/components/v6/LinkedCell'
import { ELI5Tooltip } from '@/components/v6/ELI5Tooltip'
import { formatIC } from '@/lib/format-cell'

export const dynamic = 'force-dynamic'

export default async function RegimePage() {
  const snapshotDate = await getLatestSnapshotDate()
  const [regime, cellsRes] = await Promise.all([
    getCurrentRegime(),
    getCellDefinitions(),
  ])
  const cells = cellsRes.data
  const cellsById = new Map(cells.map(c => [c.cell_id, c]))

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Market Regime
        </div>
        <h1 className="font-serif text-3xl font-semibold text-ink-primary leading-none">
          {regime.regime_state}
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          Deploy {regime.deployment_pct}%. Constructive regime — add fresh Stage 2a/2b breakouts;
          prefer leading sectors. {regime.cells_favored.length} cells are favoured
          under this regime.
        </p>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      <div className="px-6 py-5 border-b border-paper-rule">
        <RegimeIndicator regime={regime} />
      </div>

      <div className="px-6 py-5 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Cells favoured under {regime.regime_state}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {regime.cells_favored.map(cf => {
            const cell = cellsById.get(cf.cell_id)
            return (
              <Link
                key={cf.cell_id}
                href={`/matrix/${encodeURIComponent(cf.cell_id)}`}
                className="block border border-paper-rule rounded-[2px] bg-paper p-3 hover:bg-paper-rule/10 transition-colors"
              >
                <div className="flex items-baseline justify-between mb-1">
                  <span className="font-sans text-sm font-semibold text-ink-primary">
                    {cf.cell_id}
                  </span>
                  <span className="font-mono text-xs tabular-nums text-signal-pos">
                    IC {formatIC(cf.ic_in_regime)}
                  </span>
                </div>
                {cell?.best_archetype && (
                  <ELI5Tooltip term={cell.best_archetype}>
                    <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
                      {cell.best_archetype}
                    </span>
                  </ELI5Tooltip>
                )}
                <p className="font-sans text-xs text-ink-secondary leading-relaxed mt-1">
                  {cell?.reason ?? 'Cell summary loading…'}
                </p>
              </Link>
            )
          })}
        </div>
      </div>

      <div className="px-6 py-5">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Regime → Matrix → Stocks
        </h2>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed max-w-[760px] mb-3">
          The regime sets the deployment multiplier and the universe of cells worth firing.
          Each cell holds a small set of validated rules. The stocks firing those rules today
          are the universe of opportunities.
        </p>
        <div className="flex gap-3">
          <LinkedCellById cellId="Large-3m-POSITIVE" className="font-sans text-sm">
            <span className="text-teal hover:underline">Large 3m POSITIVE →</span>
          </LinkedCellById>
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
