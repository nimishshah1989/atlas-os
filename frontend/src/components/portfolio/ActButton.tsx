'use client'
// Task 3.4 — Act affordance on stock detail.
// Renders a policy-sized "Add to portfolio" button.
// When no portfolio is active: disabled with honest message.
// When active: shows suggested size + binding constraint in plain English.
// On click: POSTs to /api/portfolio/propose; shows confirmation or error.

import { useState } from 'react'

// ---------------------------------------------------------------------------
// Constraint → plain-English label
// ---------------------------------------------------------------------------

const CONSTRAINT_LABELS: Record<string, string> = {
  target_gap: 'gap-bound',
  max_per_stock: 'stock-cap-bound',
  regime_cap: 'regime-cap-bound',
  none: 'manual',
}

function constraintLabel(binding: string | null): string {
  if (!binding) return 'manual'
  return CONSTRAINT_LABELS[binding] ?? binding
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export type ActButtonProps = {
  /** UUID of the active portfolio, or undefined when none is selected. */
  portfolioId: string | undefined
  /** Display name of the portfolio (e.g. "Banking Leaders"). */
  portfolioName: string | undefined
  /** UUID of the instrument being viewed. */
  instrumentId: string
  /**
   * Suggested position size as a whole-number percent string (e.g. "5.0").
   * Null when the suggestion cannot be computed (policy not loaded, etc.).
   */
  suggestedPct: string | null
  /**
   * Which cap bound the suggestion — 'target_gap' | 'max_per_stock' |
   * 'regime_cap' | 'none'. Null when suggestion unavailable.
   */
  bindingConstraint: string | null
}

// ---------------------------------------------------------------------------
// States
// ---------------------------------------------------------------------------

type SubmitState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'confirmed'; proposalId: string }
  | { kind: 'error'; message: string }

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ActButton({
  portfolioId,
  portfolioName,
  instrumentId,
  suggestedPct,
  bindingConstraint,
}: ActButtonProps) {
  const [submitState, setSubmitState] = useState<SubmitState>({ kind: 'idle' })

  // ---- No portfolio selected ----
  if (!portfolioId || !portfolioName) {
    return (
      <div className="flex items-center gap-3">
        <button
          disabled
          className="px-4 py-2 rounded-[3px] border border-paper-rule font-sans text-xs text-ink-tertiary bg-paper cursor-not-allowed"
          aria-label="Select a portfolio to size this position"
        >
          Select a portfolio to size this position
        </button>
      </div>
    )
  }

  // ---- Portfolio active but suggestion is zero or unavailable ----
  const weightValue = suggestedPct !== null ? parseFloat(suggestedPct) : NaN
  const isSuggestable = !isNaN(weightValue) && weightValue > 0

  const label = constraintLabel(bindingConstraint)
  const rationale = isSuggestable ? `${label} ${suggestedPct}%` : label

  // ---- Handlers ----
  async function handlePropose() {
    if (!isSuggestable) return
    setSubmitState({ kind: 'loading' })
    try {
      const res = await fetch('/api/portfolio/propose', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          portfolio_id: portfolioId,
          instrument_id: instrumentId,
          proposed_weight: suggestedPct,
          rationale,
        }),
      })
      const data = await res.json()
      if (res.ok && data?.data?.id) {
        setSubmitState({ kind: 'confirmed', proposalId: data.data.id })
      } else {
        const msg = data?.message ?? `Error ${res.status}`
        setSubmitState({ kind: 'error', message: msg })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      setSubmitState({ kind: 'error', message: msg })
    }
  }

  // ---- Confirmed state ----
  if (submitState.kind === 'confirmed') {
    return (
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[3px] bg-signal-pos/10 border border-signal-pos/20 font-sans text-xs text-signal-pos">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-signal-pos" />
          Proposed — pending in {portfolioName}
        </span>
      </div>
    )
  }

  // ---- Active state ----
  const isLoading = submitState.kind === 'loading'
  const isDisabled = !isSuggestable || isLoading

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={handlePropose}
        disabled={isDisabled}
        className={`
          inline-flex items-center gap-2 px-4 py-2 rounded-[3px] border font-sans text-xs
          transition-colors
          ${isDisabled
            ? 'border-paper-rule text-ink-tertiary bg-paper cursor-not-allowed'
            : 'border-teal/40 text-teal bg-teal/5 hover:bg-teal/10 cursor-pointer'
          }
        `}
        aria-label={
          isSuggestable
            ? `Add to ${portfolioName} — suggest ${suggestedPct}% (${label})`
            : 'Position sizing unavailable'
        }
      >
        {isLoading ? (
          <span>Proposing…</span>
        ) : isSuggestable ? (
          <>
            <span>Add to {portfolioName}</span>
            <span className="text-ink-tertiary">—</span>
            <span>suggest {suggestedPct}%</span>
            <span className="font-mono text-[10px] px-1.5 py-0.5 rounded-[2px] border border-teal/20 text-teal/80 bg-teal/5">
              {label}
            </span>
          </>
        ) : (
          <span>Sizing unavailable ({label})</span>
        )}
      </button>

      {submitState.kind === 'error' && (
        <p className="font-sans text-xs text-signal-neg px-1">
          {submitState.message}
        </p>
      )}
    </div>
  )
}
