'use client'

import { useState } from 'react'
import type { ThresholdRow } from '@/lib/queries/thresholds'
import { EditThresholdModal } from '../thresholds/EditThresholdModal'
import { formatIST } from '@/lib/format-date'

type Props = {
  thresholds: ThresholdRow[]
  onThresholdSaved: () => void
}

// Curated list of atlas_thresholds keys that define state boundaries.
// These are surfaced with state-mapping context labels.
const STATE_CUTOFF_KEYS = [
  'rs_quintile_top',
  'rs_quintile_bottom',
  'sector_rs_quintile_top_pct',
  'sector_rs_quintile_bottom_pct',
  'momentum_ema_convergence_pct',
  'stage1_weak_weeks_min',
] as const

const STATE_CUTOFF_LABELS: Record<string, { heading: string; stateContext: string }> = {
  rs_quintile_top: {
    heading: 'Top RS percentile cutoff',
    stateContext: 'Leader / Strong threshold — stocks in the top N% of RS qualify',
  },
  rs_quintile_bottom: {
    heading: 'Bottom RS percentile cutoff',
    stateContext: 'Weak / Laggard threshold — stocks in the bottom N% of RS qualify',
  },
  sector_rs_quintile_top_pct: {
    heading: 'Sector Overweight cutoff',
    stateContext: 'Sectors in the top N% of RS → Overweight state',
  },
  sector_rs_quintile_bottom_pct: {
    heading: 'Sector Avoid / Underweight cutoff',
    stateContext: 'Sectors in the bottom N% of RS → Avoid / Underweight state',
  },
  momentum_ema_convergence_pct: {
    heading: 'Flat momentum band (EMA convergence)',
    stateContext: 'EMAs within N% of each other → Flat momentum_state',
  },
  stage1_weak_weeks_min: {
    heading: 'Stage-1 base qualification (weak weeks)',
    stateContext: 'Requires ≥N of last 10 weeks in weak territory for Stage-1 base',
  },
}

export function StateCutoffsTab({ thresholds, onThresholdSaved }: Props) {
  const [editingKey, setEditingKey] = useState<string | null>(null)

  const thresholdMap = Object.fromEntries(thresholds.map((t) => [t.threshold_key, t]))

  const editingThreshold = editingKey ? thresholdMap[editingKey] : undefined

  function handleSaved() {
    setEditingKey(null)
    onThresholdSaved()
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="font-sans text-xs text-ink-secondary">
        These thresholds define the numerical boundaries between states. Editing them changes what RS score counts as "Leader" vs "Strong", etc. Changes here affect the next recompute run.
      </p>

      <div className="border border-paper-rule rounded-[2px] overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-paper-rule/10 border-b border-paper-rule">
              <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2">
                Threshold
              </th>
              <th className="text-right font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2">
                Value
              </th>
              <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2 hidden md:table-cell">
                State Context
              </th>
              <th className="text-left font-sans text-xs text-ink-tertiary uppercase tracking-wide px-3 py-2 hidden lg:table-cell">
                Modified
              </th>
              <th className="px-3 py-2 w-16" />
            </tr>
          </thead>
          <tbody>
            {STATE_CUTOFF_KEYS.map((key, idx) => {
              const row = thresholdMap[key]
              const meta = STATE_CUTOFF_LABELS[key]
              const isLast = idx === STATE_CUTOFF_KEYS.length - 1

              if (!row) {
                return (
                  <tr key={key} className={`border-b border-paper-rule/40 ${isLast ? 'border-b-0' : ''}`}>
                    <td className="px-3 py-2.5" colSpan={5}>
                      <span className="font-mono text-xs text-ink-tertiary">{key}</span>
                      <span className="font-sans text-xs text-signal-warn ml-2">⚠ missing seed — run migration 013 or later</span>
                    </td>
                  </tr>
                )
              }

              return (
                <tr
                  key={key}
                  className={`border-b border-paper-rule/40 hover:bg-paper-rule/10 transition-colors ${isLast ? 'border-b-0' : ''}`}
                >
                  <td className="px-3 py-2.5 align-top">
                    <p className="font-sans text-xs text-ink-primary font-medium">{meta.heading}</p>
                    <p className="font-mono text-xs text-ink-tertiary mt-0.5">{key}</p>
                  </td>
                  <td className="px-3 py-2.5 align-top text-right">
                    <span className="font-mono text-xs text-ink-primary font-medium">
                      {row.threshold_value}
                    </span>
                    {row.units && (
                      <span className="font-sans text-xs text-ink-tertiary ml-1">{row.units}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 align-top hidden md:table-cell">
                    <span className="font-sans text-xs text-ink-secondary leading-relaxed">
                      {meta.stateContext}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 align-top hidden lg:table-cell">
                    <span className="font-sans text-xs text-ink-tertiary whitespace-nowrap">
                      {formatIST(row.last_modified_at, true)}
                    </span>
                    <span className="font-sans text-xs text-ink-tertiary block">
                      by {row.last_modified_by}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <button
                      type="button"
                      onClick={() => setEditingKey(key)}
                      className="font-sans text-xs text-accent hover:opacity-70 transition-opacity underline decoration-dotted underline-offset-2"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {editingKey && editingThreshold && (
        <EditThresholdModal
          threshold={editingThreshold}
          onClose={() => setEditingKey(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
