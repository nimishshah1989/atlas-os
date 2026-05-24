// frontend/src/app/matrix/[cell]/[rule]/page.tsx
// Single-rule deep view. Renders one full RuleCard + back link.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getCellDefinition } from '@/lib/api/v1'
import { RuleCard } from '@/components/v6/RuleCard'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'

export const dynamic = 'force-dynamic'

export default async function RuleDetailPage({ params }: { params: Promise<{ cell: string; rule: string }> }) {
  const { cell: cellEnc, rule: ruleEnc } = await params
  const cellId = decodeURIComponent(cellEnc)
  const ruleId = decodeURIComponent(ruleEnc)
  const { data: cell, meta, source_kind } = await getCellDefinition(cellId)
  if (!cell) notFound()

  const rule = cell.rules.find(r => r.rule_id === ruleId || r.name === ruleId)
  if (!rule) notFound()

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-xs text-ink-tertiary mb-1">
          <Link href="/matrix" className="text-teal hover:underline">Matrix</Link>
          <span className="mx-1.5">›</span>
          <Link href={`/matrix/${encodeURIComponent(cellId)}`} className="text-teal hover:underline">{cellId}</Link>
          <span className="mx-1.5">›</span>
          {rule.name}
        </div>
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
          {rule.name}
        </h1>
      </div>

      <DataSourceBanner source={source_kind} asOf={meta.data_as_of} />

      <div className="px-6 py-5">
        <RuleCard rule={rule} cellId={cell.cell_id} />
      </div>
    </div>
  )
}
