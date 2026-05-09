'use client'
// src/components/strategy/RuleCard.tsx
// Generic rule section card with enable/disable toggle.
// When disabled, body is dimmed (opacity-50 pointer-events-none).

import type { ReactNode } from 'react'

type Props = {
  title: string
  description?: string
  enabled: boolean
  onToggleEnabled: () => void
  children: ReactNode
}

export function RuleCard({ title, description, enabled, onToggleEnabled, children }: Props) {
  return (
    <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
      {/* Header row: title + toggle */}
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex-1 min-w-0">
          <p className="font-sans text-sm font-semibold text-ink-primary">{title}</p>
          {description && (
            <p className="font-sans text-xs text-ink-tertiary mt-0.5">{description}</p>
          )}
        </div>
        <label className="flex items-center gap-2 cursor-pointer flex-shrink-0">
          <span className="font-sans text-xs text-ink-secondary">
            {enabled ? 'Active' : 'Use this rule'}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-label={`Toggle ${title}`}
            onClick={onToggleEnabled}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
              enabled ? 'bg-accent' : 'bg-paper-rule'
            }`}
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                enabled ? 'translate-x-4' : 'translate-x-1'
              }`}
            />
          </button>
        </label>
      </div>

      {/* Body — dimmed when disabled */}
      <div className={enabled ? '' : 'opacity-50 pointer-events-none'}>
        {children}
      </div>
    </div>
  )
}
