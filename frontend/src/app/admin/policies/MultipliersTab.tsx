'use client'

import type { DecisionPolicyRow } from '@/lib/queries/policies'
import { MULTIPLIER_CONFIG } from '@/lib/policy-catalogs'
import { formatIST } from '@/lib/format-date'

type Props = {
  policies: DecisionPolicyRow[]
  onEdit: (policyKey: string) => void
  onHistory: (policyKey: string) => void
}

function parseMultiplierValue(
  policy_value: string[] | Record<string, string>,
): Record<string, number> {
  if (Array.isArray(policy_value)) return {}
  const result: Record<string, number> = {}
  for (const [k, v] of Object.entries(policy_value)) {
    result[k] = Number(v)
  }
  return result
}

function MultiplierSection({
  policy,
  onEdit,
  onHistory,
}: {
  policy: DecisionPolicyRow
  onEdit: () => void
  onHistory: () => void
}) {
  const config = MULTIPLIER_CONFIG[policy.policy_key]
  if (!config) return null

  const values = parseMultiplierValue(policy.policy_value as Record<string, string>)

  return (
    <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
      {/* Header */}
      <div className="flex items-start justify-between mb-1">
        <div>
          <h3 className="font-serif text-base text-ink-primary leading-tight">{config.label}</h3>
          <p className="font-sans text-xs text-ink-tertiary mt-0.5">
            Methodology §{config.methodologySection}
          </p>
        </div>
      </div>
      <p className="font-sans text-xs text-ink-secondary mb-4">{config.description}</p>

      {/* Slider rows (read-only display) */}
      <div className="flex flex-col gap-3 mb-4">
        {config.catalog.map((state) => {
          const val = values[state]
          const configured = state in values
          const pct = configured
            ? ((val - config.min) / (config.max - config.min)) * 100
            : 0

          return (
            <div key={state} className="flex items-center gap-3">
              <span className="font-mono text-xs text-ink-primary w-28 flex-shrink-0">{state}</span>
              <div className="flex-1 relative h-1.5 bg-paper-rule rounded-full">
                <div
                  className="absolute left-0 top-0 h-full bg-accent rounded-full"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="font-mono text-xs text-ink-primary w-10 text-right flex-shrink-0">
                {configured ? `${val.toFixed(1)}×` : '—'}
              </span>
              {!configured && (
                <span className="font-sans text-xs text-ink-tertiary italic">(default)</span>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-paper-rule/40 pt-3">
        <p className="font-sans text-xs text-ink-tertiary">
          {formatIST(policy.last_modified_at, true)} by {policy.last_modified_by}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onEdit}
            className="font-sans text-xs text-accent hover:opacity-70 transition-opacity underline decoration-dotted underline-offset-2"
          >
            Edit
          </button>
          <span className="text-ink-tertiary text-xs">·</span>
          <button
            type="button"
            onClick={onHistory}
            className="font-sans text-xs text-ink-secondary hover:text-ink-primary transition-colors underline decoration-dotted underline-offset-2"
          >
            History
          </button>
        </div>
      </div>
    </div>
  )
}

export function MultipliersTab({ policies, onEdit, onHistory }: Props) {
  const multiplierKeys = Object.keys(MULTIPLIER_CONFIG)
  const policyMap = Object.fromEntries(policies.map((p) => [p.policy_key, p]))

  return (
    <div className="flex flex-col gap-6">
      {multiplierKeys.map((key) => {
        const policy = policyMap[key]
        if (!policy) {
          return (
            <div key={key} className="border border-paper-rule rounded-[2px] p-4 bg-paper">
              <h3 className="font-serif text-base text-ink-primary">{MULTIPLIER_CONFIG[key].label}</h3>
              <p className="font-sans text-xs text-signal-warn mt-2">
                ⚠ No DB row found for <span className="font-mono">{key}</span>. Run migration 024 to seed.
              </p>
            </div>
          )
        }
        return (
          <MultiplierSection
            key={key}
            policy={policy}
            onEdit={() => onEdit(key)}
            onHistory={() => onHistory(key)}
          />
        )
      })}
    </div>
  )
}
