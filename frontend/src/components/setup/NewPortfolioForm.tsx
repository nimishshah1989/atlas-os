'use client'
// src/components/setup/NewPortfolioForm.tsx
// Form for /setup/new-portfolio — name + instrument_universe.
// POSTs to /api/portfolio/create; on success links to the new portfolio.
// Inherits house-default policy (editable later in /setup/policy).

import { useState } from 'react'
import Link from 'next/link'

// ---------------------------------------------------------------------------
// Universe options — mirrors policy.ts INSTRUMENT_UNIVERSE_LABEL
// ---------------------------------------------------------------------------

const UNIVERSE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'direct_equity', label: 'Direct Equity' },
  { value: 'etf', label: 'ETF' },
  { value: 'mutual_fund', label: 'Mutual Fund' },
  { value: 'mixed', label: 'Mixed' },
]

// ---------------------------------------------------------------------------
// Submit state
// ---------------------------------------------------------------------------

type SubmitState =
  | { kind: 'idle' }
  | { kind: 'submitting' }
  | { kind: 'success'; id: string; name: string }
  | { kind: 'error'; message: string }

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function NewPortfolioForm() {
  const [name, setName] = useState('')
  const [universe, setUniverse] = useState('direct_equity')
  const [submitState, setSubmitState] = useState<SubmitState>({ kind: 'idle' })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    if (!name.trim()) {
      setSubmitState({ kind: 'error', message: 'Portfolio name is required' })
      return
    }

    setSubmitState({ kind: 'submitting' })

    try {
      const res = await fetch('/api/portfolio/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), instrument_universe: universe }),
      })
      const data = await res.json()

      if (res.ok && data?.data?.id) {
        setSubmitState({ kind: 'success', id: data.data.id, name: data.data.name })
      } else {
        const msg = data?.message ?? `Error ${res.status}`
        setSubmitState({ kind: 'error', message: msg })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      setSubmitState({ kind: 'error', message: msg })
    }
  }

  const isSubmitting = submitState.kind === 'submitting'

  // ---- Success state ----
  if (submitState.kind === 'success') {
    return (
      <div data-testid="create-success" className="space-y-4">
        <div className="px-4 py-3 rounded-[2px] border border-signal-pos/40 bg-signal-pos/5">
          <p className="font-sans text-sm text-signal-pos font-semibold">
            Portfolio created: {submitState.name}
          </p>
          <p className="font-sans text-xs text-ink-secondary mt-1">
            The portfolio inherits the house-default policy. You can customise it in{' '}
            <Link href="/setup/policy" className="text-accent hover:underline">
              /setup/policy
            </Link>
            .
          </p>
        </div>
        <div className="flex gap-3">
          <Link
            href={`/portfolios/${submitState.id}`}
            className="font-sans text-sm px-4 py-2 bg-accent text-white rounded-[2px] hover:bg-accent/90 transition-colors"
          >
            View Portfolio
          </Link>
          <button
            type="button"
            onClick={() => {
              setName('')
              setUniverse('direct_equity')
              setSubmitState({ kind: 'idle' })
            }}
            className="font-sans text-sm px-4 py-2 border border-paper-rule rounded-[2px] text-ink-secondary hover:text-ink-primary transition-colors"
          >
            Create Another
          </button>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      {/* Name */}
      <div>
        <label
          htmlFor="portfolio-name"
          className="font-sans text-xs font-semibold uppercase tracking-wider text-ink-secondary block mb-1"
        >
          Portfolio Name
        </label>
        <input
          id="portfolio-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Banking Leaders Q2 2026"
          disabled={isSubmitting}
          className="w-full md:w-96 font-sans text-sm px-3 py-2 border border-paper-rule rounded-[2px] bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent disabled:opacity-50"
        />
      </div>

      {/* Instrument universe */}
      <div>
        <label
          htmlFor="instrument-universe"
          className="font-sans text-xs font-semibold uppercase tracking-wider text-ink-secondary block mb-1"
        >
          Instrument Universe
        </label>
        <select
          id="instrument-universe"
          value={universe}
          onChange={(e) => setUniverse(e.target.value)}
          disabled={isSubmitting}
          className="font-sans text-sm border border-paper-rule rounded-[2px] px-3 py-2 bg-paper text-ink-primary focus:outline-none focus:border-accent disabled:opacity-50"
        >
          {UNIVERSE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Policy note */}
      <p className="font-sans text-xs text-ink-tertiary max-w-sm">
        This portfolio will inherit the house-default policy. You can override individual
        fields per-portfolio in{' '}
        <Link href="/setup/policy" className="text-accent hover:underline">
          Setup / Policy
        </Link>{' '}
        after creation.
      </p>

      {/* Error */}
      {submitState.kind === 'error' && (
        <p
          data-testid="form-error"
          className="font-sans text-sm text-signal-neg"
        >
          {submitState.message}
        </p>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={isSubmitting}
        className="font-sans text-sm px-6 py-2.5 rounded-[2px] bg-accent text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent/90 transition-colors"
      >
        {isSubmitting ? 'Creating…' : 'Create Portfolio'}
      </button>
    </form>
  )
}
