'use client'

import type { DecisionPolicyRow } from '@/lib/queries/policies'
import { GATE_CONFIG, LOCKED_STATES } from '@/lib/policy-catalogs'
import { formatIST } from '@/lib/format-date'

type Props = {
  policies: DecisionPolicyRow[]
  onEdit: (policyKey: string) => void
  onHistory: (policyKey: string) => void
}

function GateCard({
  policy,
  onEdit,
  onHistory,
}: {
  policy: DecisionPolicyRow
  onEdit: () => void
  onHistory: () => void
}) {
  const config = GATE_CONFIG[policy.policy_key]
  if (!config) return null

  const currentStates = (Array.isArray(policy.policy_value) ? policy.policy_value : []) as string[]

  return (
    <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
      {/* Card header */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="font-serif text-base text-ink-primary leading-tight">{config.label}</h3>
          <p className="font-sans text-xs text-ink-tertiary mt-0.5">
            Methodology §{config.methodologySection}
          </p>
        </div>
        {currentStates.length === 0 && (
          <span className="font-sans text-xs text-signal-warn border border-signal-warn/30 bg-signal-warn/10 rounded-[2px] px-1.5 py-0.5">
            Empty — 100% blocked
          </span>
        )}
      </div>

      {/* Description */}
      <p className="font-sans text-xs text-ink-secondary mb-3">{config.description}</p>

      {/* State tags */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {config.catalog.map((s) => {
          const active = currentStates.includes(s)
          return (
            <span
              key={s}
              className={`font-mono text-xs rounded-[2px] px-2 py-0.5 border ${
                active
                  ? 'bg-accent/10 border-accent/30 text-accent'
                  : 'bg-paper-rule/20 border-paper-rule text-ink-tertiary'
              }`}
            >
              {s}
            </span>
          )
        })}
        {LOCKED_STATES.map((s) => (
          <span
            key={s}
            className="font-mono text-xs rounded-[2px] px-2 py-0.5 border bg-paper-rule/10 border-paper-rule/40 text-ink-tertiary italic"
          >
            {s} (locked)
          </span>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between">
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

export function GatePoliciesTab({ policies, onEdit, onHistory }: Props) {
  const gateKeys = Object.keys(GATE_CONFIG)
  const policyMap = Object.fromEntries(policies.map((p) => [p.policy_key, p]))

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {gateKeys.map((key) => {
        const policy = policyMap[key]
        if (!policy) {
          return (
            <div key={key} className="border border-paper-rule rounded-[2px] p-4 bg-paper">
              <h3 className="font-serif text-base text-ink-primary">{GATE_CONFIG[key].label}</h3>
              <p className="font-sans text-xs text-signal-warn mt-2">
                ⚠ No DB row found for <span className="font-mono">{key}</span>. Run migration 024 to seed.
              </p>
            </div>
          )
        }
        return (
          <GateCard
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
