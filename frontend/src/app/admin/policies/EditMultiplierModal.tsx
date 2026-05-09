'use client'
// allow-large: modal owns the full edit UX: slider per state, diff preview, validation, pending state, error display

import { useEffect, useState, useTransition } from 'react'
import { updateMultiplier } from './actions'
import type { DecisionPolicyRow } from '@/lib/queries/policies'
import { MULTIPLIER_CONFIG } from '@/lib/policy-catalogs'

type Props = { policy: DecisionPolicyRow; onClose: () => void; onSaved: () => void }

function parseMultiplierValue(
  policy_value: string[] | Record<string, string> | null,
): Record<string, number> {
  if (!policy_value || Array.isArray(policy_value)) return {}
  const result: Record<string, number> = {}
  for (const [k, v] of Object.entries(policy_value)) {
    result[k] = Number(v)
  }
  return result
}

export function EditMultiplierModal({ policy, onClose, onSaved }: Props) {
  const config = MULTIPLIER_CONFIG[policy.policy_key]
  if (!config) return null

  const currentValues = parseMultiplierValue(policy.policy_value as Record<string, string> | null)
  const [values, setValues] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {}
    for (const state of config.catalog) {
      init[state] = currentValues[state] ?? config.min
    }
    return init
  })
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const setSlider = (state: string, v: number) => {
    setValues((prev) => ({ ...prev, [state]: v }))
    setError(null)
  }

  const changed = config.catalog.some(
    (s) => values[s] !== (currentValues[s] ?? config.min)
  )

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!reason.trim()) { setError('Change reason is required'); return }
    startTransition(async () => {
      const result = await updateMultiplier(policy.policy_key, values, reason)
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
        aria-labelledby="edit-multiplier-modal-title"
        className="bg-paper border border-paper-rule rounded-[2px] w-full max-w-lg mx-4 shadow-lg max-h-[90vh] flex flex-col"
      >
        {/* Header */}
        <div className="border-b border-paper-rule px-6 py-4 flex items-start justify-between flex-shrink-0">
          <div>
            <h2 id="edit-multiplier-modal-title" className="font-serif text-lg text-ink-primary leading-tight">
              {config.label}
            </h2>
            <p className="font-mono text-xs text-ink-tertiary mt-0.5">{policy.policy_key}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="font-sans text-ink-tertiary hover:text-ink-primary text-lg">×</button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-5 flex flex-col gap-4 overflow-y-auto">
          <p className="font-sans text-xs text-ink-secondary">{config.description}</p>
          <p className="font-sans text-xs text-ink-tertiary">
            Range [{config.min}, {config.max}] · step {config.step}
          </p>
          {/* Sliders */}
          <div className="flex flex-col gap-4">
            {config.catalog.map((state) => {
              const val = values[state] ?? config.min
              const wasConfigured = state in currentValues
              return (
                <div key={state} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between">
                    <label htmlFor={`slider-${state}`} className="font-mono text-xs text-ink-primary">
                      {state}
                    </label>
                    <span className="font-mono text-xs text-ink-primary font-medium">
                      {val.toFixed(1)}×
                    </span>
                  </div>
                  <input
                    id={`slider-${state}`}
                    type="range"
                    min={config.min}
                    max={config.max}
                    step={config.step}
                    value={val}
                    onChange={(e) => setSlider(state, Number(e.target.value))}
                    disabled={isPending}
                    className="w-full accent-accent disabled:opacity-60"
                  />
                  {!wasConfigured && (
                    <p className="font-sans text-xs text-ink-tertiary italic">
                      (not configured — falling back to default)
                    </p>
                  )}
                </div>
              )
            })}
          </div>
          {/* Diff */}
          {changed && (
            <div className="bg-accent/5 border border-accent/20 rounded-[2px] px-3 py-2">
              <p className="font-sans text-xs text-ink-secondary mb-1">Changes:</p>
              {config.catalog
                .filter((s) => values[s] !== (currentValues[s] ?? config.min))
                .map((s) => (
                  <p key={s} className="font-mono text-xs">
                    <span className="text-ink-secondary">{s}:</span>{' '}
                    <span className="text-signal-neg">{(currentValues[s] ?? config.min).toFixed(1)}</span>
                    {' → '}
                    <span className="text-signal-pos">{values[s].toFixed(1)}</span>
                  </p>
                ))}
            </div>
          )}
          {/* Reason */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="edit-multiplier-reason" className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide">
              Change Reason <span className="text-signal-neg">*</span>
            </label>
            <textarea
              id="edit-multiplier-reason"
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
