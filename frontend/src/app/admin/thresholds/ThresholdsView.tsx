'use client'
// allow-large: owns all interactive state for threshold admin — edit modal, history drawer, recompute panel, and grouped table rendering

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import type { ThresholdRow, RecentRunRow } from '@/lib/queries/thresholds'
import { EditThresholdModal } from './EditThresholdModal'
import { HistoryDrawer } from './HistoryDrawer'
import { RecomputePanel } from './RecomputePanel'
import { formatIST } from '@/lib/format-date'
import { formatThreshold } from '@/lib/format-number'

type Props = {
  byCategory: Record<string, ThresholdRow[]>
  sortedCategories: string[]
  recentRuns: RecentRunRow[]
}

function CategoryTable({
  category,
  rows,
  onEdit,
  onHistory,
}: {
  category: string
  rows: ThresholdRow[]
  onEdit: (key: string) => void
  onHistory: (key: string) => void
}) {
  return (
    <div className="mb-6">
      <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-2 capitalize">
        {category}
      </h2>
      <div className="border border-paper-rule rounded-[2px] overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-paper-rule/10 border-b border-paper-rule">
              <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2">
                Key
              </th>
              <th className="text-right font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2">
                Value
              </th>
              <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2 hidden sm:table-cell">
                Range
              </th>
              <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2 hidden md:table-cell">
                Description
              </th>
              <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2 hidden lg:table-cell">
                Modified
              </th>
              <th className="px-3 py-2 w-28" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={row.threshold_key}
                className={`border-b border-paper-rule/40 hover:bg-paper-rule/10 transition-colors ${idx === rows.length - 1 ? 'border-b-0' : ''}`}
              >
                <td className="px-3 py-2.5 align-middle">
                  <span className="font-mono text-xs text-ink-primary">
                    {row.threshold_key}
                  </span>
                </td>
                <td className="px-3 py-2.5 align-middle text-right">
                  <span className="font-mono text-xs text-ink-primary font-medium">
                    {formatThreshold(row.threshold_value)}
                  </span>
                  {row.units && (
                    <span className="font-sans text-xs text-ink-tertiary ml-1">
                      {row.units}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5 align-middle hidden sm:table-cell">
                  <span className="font-mono text-xs text-ink-tertiary">
                    [{formatThreshold(row.min_allowed)}, {formatThreshold(row.max_allowed)}]
                  </span>
                </td>
                <td className="px-3 py-2.5 align-middle hidden md:table-cell">
                  <span className="font-sans text-xs text-ink-secondary leading-relaxed">
                    {row.description}
                  </span>
                </td>
                <td className="px-3 py-2.5 align-middle hidden lg:table-cell">
                  <span className="font-sans text-xs text-ink-tertiary">
                    {formatIST(row.last_modified_at, true)}
                  </span>
                  <span className="font-sans text-xs text-ink-tertiary block">
                    by {row.last_modified_by}
                  </span>
                </td>
                <td className="px-3 py-2.5 align-middle">
                  <div className="flex items-center gap-2 justify-end">
                    <button
                      type="button"
                      onClick={() => onEdit(row.threshold_key)}
                      className="font-sans text-xs text-accent hover:opacity-70 transition-opacity underline decoration-dotted underline-offset-2"
                    >
                      Edit
                    </button>
                    <span className="text-ink-tertiary text-xs">·</span>
                    <button
                      type="button"
                      onClick={() => onHistory(row.threshold_key)}
                      className="font-sans text-xs text-ink-secondary hover:text-ink-primary transition-colors underline decoration-dotted underline-offset-2"
                    >
                      History
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ThresholdsView({ byCategory, sortedCategories, recentRuns }: Props) {
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const router = useRouter()

  // Flatten the map to find a ThresholdRow by key
  const findRow = (key: string): ThresholdRow | undefined =>
    Object.values(byCategory).flat().find((r) => r.threshold_key === key)

  const editingThreshold = editingKey ? findRow(editingKey) : undefined

  function handleSaved() {
    setEditingKey(null)
    router.refresh() // re-runs the RSC fetch and updates the table
  }

  return (
    <>
      <RecomputePanel recentRuns={recentRuns} />

      {sortedCategories.map((cat) => (
        <CategoryTable
          key={cat}
          category={cat}
          rows={byCategory[cat]}
          onEdit={setEditingKey}
          onHistory={setSelectedKey}
        />
      ))}

      {editingKey && editingThreshold && (
        <EditThresholdModal
          threshold={editingThreshold}
          onClose={() => setEditingKey(null)}
          onSaved={handleSaved}
        />
      )}

      {selectedKey && (
        <HistoryDrawer
          thresholdKey={selectedKey}
          onClose={() => setSelectedKey(null)}
        />
      )}
    </>
  )
}
