// frontend/src/app/matrix/page.tsx
// The soul page — 3×8 grid of all 24 cells. Click any cell → /matrix/<cell_id>.

import Link from 'next/link'
import { CellMatrix } from '@/components/v6/CellMatrix'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { ELI5Tooltip } from '@/components/v6/ELI5Tooltip'
import { getCellDefinitions } from '@/lib/api/v1'

export const dynamic = 'force-dynamic'

export default async function MatrixPage() {
  const { data: cells, meta, source_kind } = await getCellDefinitions()

  // Cells lit today = cells with at least one rule whose population_today > 0,
  // OR (fallback) cells with grade=green and n_gate_pass > 0.
  const litCells = cells
    .filter(c => c.rules.some(r => r.population_today > 0) || (c.grade === 'green' && c.n_gate_pass > 0))
    .map(c => c.cell_id)

  const greenCount = cells.filter(c => c.grade === 'green').length
  const amberCount = cells.filter(c => c.grade === 'amber').length
  const redCount = cells.filter(c => c.grade === 'red').length

  // Best rules across the matrix — top 5 by IC.
  const bestRules = cells
    .filter(c => c.best_rule_ic != null && c.grade === 'green')
    .sort((a, b) => Math.abs(b.best_rule_ic ?? 0) - Math.abs(a.best_rule_ic ?? 0))
    .slice(0, 5)

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Atlas v6 — The Soul Page
        </div>
        <h1 className="font-serif text-3xl font-semibold text-ink-primary leading-none">
          The 24-Cell Matrix
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          Twenty-four cells (3 market-cap tiers × 4 tenures × 2 directions) define
          Atlas&apos;s discovery space. Each cell holds the strongest validated rule
          for its slice — every page in the platform is a different projection of
          this matrix.
        </p>
      </div>

      <DataSourceBanner source={source_kind} asOf={meta.data_as_of} hint={`Methodology lock 2026-05-23 · source ${meta.source}`} />

      <div className="px-6 py-4 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
          {greenCount} ship-ready
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-warn" />
          {amberCount} park
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" />
          {redCount} no signal
        </span>
        <span className="ml-auto font-sans text-xs text-ink-tertiary">
          Click any cell → cell drill-down with top-5 rules + stock list firing today
        </span>
      </div>

      <div className="px-6 py-6 border-b border-paper-rule">
        <CellMatrix cells={cells} highlight={litCells} />
      </div>

      <div className="px-6 py-5 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Strongest rules across the matrix
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {bestRules.map(c => (
            <Link
              key={c.cell_id}
              href={`/matrix/${encodeURIComponent(c.cell_id)}`}
              className="block border border-paper-rule rounded-[2px] bg-paper p-3 hover:bg-paper-rule/10 transition-colors"
            >
              <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
                {c.cell_id}
              </div>
              <div className="font-mono text-base font-semibold tabular-nums text-ink-primary">
                IC {c.best_rule_ic?.toFixed(3)}
              </div>
              <div className="font-mono text-[11px] tabular-nums text-ink-secondary mt-0.5 break-all">
                {c.best_rule_id}
              </div>
              <div className="mt-1">
                <ELI5Tooltip term={c.best_archetype ?? ''}>
                  <span className="font-sans text-[10px] text-ink-tertiary">
                    {c.best_archetype}
                  </span>
                </ELI5Tooltip>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div className="px-6 py-5">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-2">
          What this is
        </h2>
        <div className="prose prose-sm max-w-[760px]">
          <p className="font-sans text-sm text-ink-secondary leading-relaxed mb-2">
            For each cell, the deep-search engine evaluates 191–321 candidate
            predicates, applies a benjamini-hochberg multiple-testing correction
            (within-cell <em>and</em> cross-cell, 6,144 total tests), and keeps
            only the rules that pass:
          </p>
          <ul className="font-sans text-sm text-ink-secondary leading-relaxed list-disc list-inside space-y-1">
            <li>IC magnitude above the cell-specific floor (0.02–0.05)</li>
            <li>BH-FDR q-value ≤ 0.10 (cross-cell)</li>
            <li>Friction-adjusted excess return ≥ 0 (after slippage)</li>
            <li>Per-window consistency across 3 rolling OOS windows (2022–2025)</li>
          </ul>
          <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2">
            Green cells (ship) drive the live conviction tape on every stock.
            Amber cells (park) are validated but flagged with a disclaimer
            (survivorship bias on the NEGATIVE side). Red cells have nothing
            that clears the gate today.
            <Link href="/methodology" className="text-teal hover:underline ml-1">
              Methodology →
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
