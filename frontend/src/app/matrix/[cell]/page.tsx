// frontend/src/app/matrix/[cell]/page.tsx
// Cell drill-down — top-5 RuleCards + stock list firing the cell.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getCellDefinition } from '@/lib/api/v1'
import { RuleCard } from '@/components/v6/RuleCard'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { ELI5Tooltip } from '@/components/v6/ELI5Tooltip'
import { LinkedTicker } from '@/components/ui/LinkedToken'
import { StateBadge } from '@/components/ui/StateBadge'
import { formatIC, formatFricAdj, formatGatePass } from '@/lib/format-cell'

export const dynamic = 'force-dynamic'

const GRADE_STATE: Record<string, string> = {
  green: 'Recommended',
  amber: 'Hold',
  red: 'Avoid',
  unknown: 'Neutral',
}

export default async function CellDetailPage({ params }: { params: Promise<{ cell: string }> }) {
  const { cell: cellId } = await params
  const decoded = decodeURIComponent(cellId)
  const { data: cell, meta, source_kind } = await getCellDefinition(decoded)

  if (!cell) {
    notFound()
  }

  const topRules = cell.rules.slice(0, 5)

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-xs text-ink-tertiary mb-1">
          <Link href="/matrix" className="text-teal hover:underline">Matrix</Link>
          <span className="mx-1.5">›</span>
          {cell.tier}
          <span className="mx-1">·</span>
          {cell.tenure}
          <span className="mx-1">·</span>
          {cell.direction}
        </div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
            {cell.cell_id}
          </h1>
          <StateBadge state={GRADE_STATE[cell.grade]} size="sm" />
          <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">
            {cell.ship_or_park.replace(/_/g, ' ')}
          </span>
        </div>
        {cell.best_archetype && (
          <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
            Lead archetype: <ELI5Tooltip term={cell.best_archetype}><strong>{cell.best_archetype}</strong></ELI5Tooltip>.
            {' '}{cell.reason}
          </p>
        )}
      </div>

      <DataSourceBanner source={source_kind} asOf={meta.data_as_of} />

      <div className="px-6 py-4 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <Metric label="Best IC" value={formatIC(cell.best_rule_ic)} />
        <Metric label="Best fric-adj (ann)" value={formatFricAdj(cell.best_rule_fric_adj_ann)} />
        <Metric label="Gate pass" value={formatGatePass(cell.n_gate_pass, cell.n_candidates)} />
        <Metric label="Candidates" value={`${cell.n_candidates}`} />
        {cell.disclaimers_applicable.length > 0 && (
          <span className="font-sans text-[10px] text-ink-tertiary ml-auto">
            Disclaimers: {cell.disclaimers_applicable.join(', ')}
          </span>
        )}
      </div>

      <div className="px-6 py-5 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Top {topRules.length} rules
        </h2>
        {topRules.length === 0 ? (
          <p className="font-sans text-sm text-ink-secondary">
            No rules cleared the gate for this cell. Best candidate {cell.best_rule_id ?? '—'} did not pass; see the matrix overview for context.
          </p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {topRules.map(rule => (
              <RuleCard key={rule.rule_id} rule={rule} cellId={cell.cell_id} />
            ))}
          </div>
        )}
      </div>

      <div className="px-6 py-5">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-2">
          Stocks firing this cell today
        </h2>
        {topRules[0]?.population_today_iids?.length ? (
          <div className="flex flex-wrap gap-2">
            {topRules[0].population_today_iids.slice(0, 30).map(iid => (
              <LinkedTicker key={iid} symbol={iid} className="font-mono text-xs" />
            ))}
          </div>
        ) : (
          <p className="font-sans text-sm text-ink-secondary">
            Population list not yet wired (backend endpoint will return today&apos;s firing iids in the rules[*].population_today_iids array).
            {' '}Top rule reports {topRules[0]?.population_today ?? 0} stocks firing.
          </p>
        )}
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</div>
      <div className="font-mono text-lg font-semibold tabular-nums text-ink-primary leading-none mt-0.5">
        {value}
      </div>
    </div>
  )
}
