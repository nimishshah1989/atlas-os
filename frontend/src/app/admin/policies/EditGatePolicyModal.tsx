'use client'
// allow-large: modal owns the full edit UX: checkbox group, diff preview, validation, pending state, error display

import { useEffect, useState, useTransition } from 'react'
import { updateGatePolicy } from './actions'
import type { DecisionPolicyRow } from '@/lib/queries/policies'
import { GATE_CONFIG, LOCKED_STATES } from '@/lib/policy-catalogs'

type Props = { policy: DecisionPolicyRow; onClose: () => void; onSaved: () => void }

export function EditGatePolicyModal({ policy, onClose, onSaved }: Props) {
  const config = GATE_CONFIG[policy.policy_key]
  if (!config) return null

  const currentStates = (Array.isArray(policy.policy_value) ? policy.policy_value : []) as string[]
  const [selected, setSelected] = useState<Set<string>>(new Set(currentStates))
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const toggle = (s: string) => {
    const next = new Set(selected)
    if (next.has(s)) next.delete(s); else next.add(s)
    setSelected(next)
    setError(null)
  }

  const changed =
    selected.size !== currentStates.length ||
    [...selected].some((s) => !currentStates.includes(s))

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!reason.trim()) { setError('Change reason is required'); return }
    startTransition(async () => {
      const result = await updateGatePolicy(policy.policy_key, [...selected], reason)
      if (result.ok) { onSaved(); onClose() } else setError(result.error)
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-primary/30"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-gate-policy-modal-title"
        className="bg-paper border border-paper-rule rounded-[2px] w-full max-w-lg mx-4 shadow-lg"
      >
        {/* Header */}
        <div className="border-b border-paper-rule px-6 py-4 flex items-start justify-between">
          <div>
            <h2 id="edit-gate-policy-modal-title" className="font-serif text-lg text-ink-primary leading-tight">
              {config.label}
            </h2>
            <p className="font-mono text-xs text-ink-tertiary mt-0.5">{policy.policy_key}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="font-sans text-ink-tertiary hover:text-ink-primary text-lg">×</button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-5 flex flex-col gap-4">
          <p className="font-sans text-xs text-ink-secondary">{config.description}</p>
          {/* Checkbox grid */}
          <fieldset className="flex flex-col gap-2">
            <legend className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide mb-1">
              Allowed states
            </legend>
            {config.catalog.map((s) => (
              <label key={s} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.has(s)}
                  onChange={() => toggle(s)}
                  disabled={isPending}
                  className="accent-accent"
                />
                <span className="font-mono text-xs text-ink-primary">{s}</span>
              </label>
            ))}
            {/* Locked states — always excluded */}
            <div className="mt-2 pt-2 border-t border-paper-rule/40">
              <p className="font-sans text-xs text-ink-tertiary mb-1">Always excluded (locked):</p>
              {LOCKED_STATES.map((s) => (
                <span key={s} className="font-mono text-xs text-ink-tertiary mr-2">{s}</span>
              ))}
            </div>
          </fieldset>
          {selected.size === 0 && (
            <p className="font-sans text-xs text-signal-warn">⚠ Empty set — this gate will block 100% of stocks.</p>
          )}
          {/* Diff */}
          {changed && (
            <div className="bg-accent/5 border border-accent/20 rounded-[2px] px-3 py-2">
              <p className="font-sans text-xs text-ink-secondary">
                Diff:{' '}
                <span className="font-mono text-signal-neg">{currentStates.join(', ') || '(empty)'}</span>
                {' → '}
                <span className="font-mono text-signal-pos">{[...selected].join(', ') || '(empty)'}</span>
              </p>
            </div>
          )}
          {/* Reason */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="edit-gate-policy-reason" className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide">
              Change Reason <span className="text-signal-neg">*</span>
            </label>
            <textarea
              id="edit-gate-policy-reason"
              value={reason}
              onChange={(e) => { setReason(e.target.value); setError(null) }}
              disabled={isPending}
              rows={3}
              placeholder="Why this change?"
              className="border border-paper-rule rounded-[2px] px-3 py-2 text-sm font-sans bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent resize-none disabled:opacity-60"
            />
          </div>
          {error && <p className="font-sans text-xs text-signal-neg">{error}</p>}
          <div className="flex items-center justify-end gap-3 pt-1">
            <button type="button" onClick={onClose} disabled={isPending} className="font-sans text-sm text-ink-secondary hover:text-ink-primary disabled:opacity-50">Cancel</button>
            <button
              type="submit"
              disabled={isPending || !reason.trim() || !changed}
              className="bg-accent text-paper font-sans text-sm px-4 py-2 rounded-[2px] hover:opacity-90 disabled:opacity-50"
            >
              {isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
