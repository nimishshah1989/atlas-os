'use client'
// allow-large: modal owns the full edit UX: form, diff preview, validation, pending state, error display

import { useState, useTransition } from 'react'
import { updateThreshold } from './actions'
import type { ThresholdRow } from '@/lib/queries/thresholds'

type Props = {
  threshold: ThresholdRow
  onClose: () => void
  onSaved: () => void
}

export function EditThresholdModal({ threshold, onClose, onSaved }: Props) {
  const [value, setValue] = useState(threshold.threshold_value)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const currentNum = parseFloat(threshold.threshold_value)
  const newNum = parseFloat(value)
  const hasValidNum = Number.isFinite(newNum)
  const changed = hasValidNum && newNum !== currentNum
  const minNum = parseFloat(threshold.min_allowed)
  const maxNum = parseFloat(threshold.max_allowed)
  const outOfRange = hasValidNum && (newNum < minNum || newNum > maxNum)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!reason.trim()) {
      setError('Change reason is required')
      return
    }
    if (!hasValidNum) {
      setError('Value must be a number')
      return
    }
    if (outOfRange) {
      setError(`Value must be between ${threshold.min_allowed} and ${threshold.max_allowed}`)
      return
    }

    startTransition(async () => {
      const result = await updateThreshold(threshold.threshold_key, value, reason)
      if (result.ok) {
        onSaved()
        onClose()
      } else {
        setError(result.error)
      }
    })
  }

  return (
    /* backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-primary/30"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-paper border border-paper-rule rounded-[2px] w-full max-w-md mx-4 shadow-lg">
        {/* Header */}
        <div className="border-b border-paper-rule px-6 py-4 flex items-start justify-between">
          <div>
            <h2 className="font-serif text-lg text-ink-primary leading-tight">
              Edit Threshold
            </h2>
            <p className="font-mono text-xs text-ink-tertiary mt-0.5">
              {threshold.threshold_key}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="font-sans text-ink-tertiary hover:text-ink-primary transition-colors text-lg leading-none mt-0.5"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="px-6 py-5 flex flex-col gap-4">
          {/* Description */}
          <div>
            <p className="font-sans text-xs text-ink-secondary leading-relaxed">
              {threshold.description}
            </p>
            {threshold.methodology_section && (
              <p className="font-sans text-xs text-ink-tertiary mt-1">
                Methodology: {threshold.methodology_section}
              </p>
            )}
          </div>

          {/* Value input */}
          <div className="flex flex-col gap-1.5">
            <label className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide">
              Value{threshold.units ? ` (${threshold.units})` : ''}
            </label>
            <input
              type="number"
              step="any"
              value={value}
              onChange={(e) => { setValue(e.target.value); setError(null) }}
              disabled={isPending}
              className="border border-paper-rule rounded-[2px] px-3 py-2 text-sm font-mono bg-paper text-ink-primary focus:outline-none focus:border-accent disabled:opacity-60"
            />
            <p className="font-sans text-xs text-ink-tertiary">
              Allowed range: [{threshold.min_allowed}, {threshold.max_allowed}]
              {' '}· Default: {threshold.default_value}
            </p>
          </div>

          {/* Diff preview */}
          {changed && (
            <div className="bg-accent/5 border border-accent/20 rounded-[2px] px-3 py-2">
              <p className="font-sans text-xs text-ink-secondary">
                Diff preview:{' '}
                <span className="font-mono text-signal-neg">{threshold.threshold_value}</span>
                {' → '}
                <span className={`font-mono ${outOfRange ? 'text-signal-neg' : 'text-signal-pos'}`}>
                  {value}
                </span>
                {outOfRange && (
                  <span className="text-signal-neg ml-2">⚠ out of range</span>
                )}
              </p>
            </div>
          )}

          {/* Reason textarea */}
          <div className="flex flex-col gap-1.5">
            <label className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide">
              Change Reason <span className="text-signal-neg">*</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => { setReason(e.target.value); setError(null) }}
              disabled={isPending}
              rows={3}
              placeholder="Describe why this value is changing…"
              className="border border-paper-rule rounded-[2px] px-3 py-2 text-sm font-sans bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent resize-none disabled:opacity-60"
            />
          </div>

          {/* Inline error */}
          {error && (
            <p className="font-sans text-xs text-signal-neg">{error}</p>
          )}

          {/* Footer buttons */}
          <div className="flex items-center justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="font-sans text-sm text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending || !reason.trim() || !hasValidNum}
              className="bg-accent text-paper font-sans text-sm px-4 py-2 rounded-[2px] hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
