'use client'
// src/components/setup/PolicyPageClient.tsx
// Client island for /setup/policy.
// Owns: portfolio selector, save wiring to POST /api/policy, success/error states.
// Receives policy + portfolios from the RSC page shell (server-fetched).

import { useState } from 'react'
import { PolicyEditor } from '@/components/setup/PolicyEditor'
import type { PolicyEditorChanges } from '@/components/setup/PolicyEditor'
import type { EffectivePolicy } from '@/components/portfolio/PolicyPanel'
import type { PortfolioListRow } from '@/lib/queries/portfolios'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

type Props = {
  policy: EffectivePolicy
  portfolioId: string | null
  portfolios: PortfolioListRow[]
  onPortfolioChange: (id: string | null) => void
}

// ---------------------------------------------------------------------------
// Save state
// ---------------------------------------------------------------------------

type SaveState =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'success'; policy: EffectivePolicy }
  | { kind: 'error'; message: string }

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PolicyPageClient({
  policy,
  portfolioId,
  portfolios,
  onPortfolioChange,
}: Props) {
  const [saveState, setSaveState] = useState<SaveState>({ kind: 'idle' })
  // Effective policy shown in editor — may be updated after a successful save
  const [activePolicy, setActivePolicy] = useState<EffectivePolicy>(policy)

  const mode = portfolioId === null ? 'house-default' : 'portfolio'

  // When parent passes a new policy (e.g. portfolio selector changed), reset state
  // We track the policy prop to detect changes via useEffect would be cleaner but
  // the shell does a full navigation on selector change, so policy always arrives fresh.

  async function handleSave(changes: PolicyEditorChanges) {
    setSaveState({ kind: 'saving' })
    try {
      const res = await fetch('/api/policy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ portfolioId, changes }),
      })
      const data = await res.json()
      if (res.ok && data?.data) {
        setActivePolicy(data.data as EffectivePolicy)
        setSaveState({ kind: 'success', policy: data.data as EffectivePolicy })
      } else {
        const msg = data?.message ?? `Error ${res.status}`
        setSaveState({ kind: 'error', message: msg })
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error'
      setSaveState({ kind: 'error', message: msg })
    }
  }

  function handleSelectorChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const val = e.target.value
    onPortfolioChange(val === '' ? null : val)
    // Reset save state when context changes
    setSaveState({ kind: 'idle' })
    setActivePolicy(policy)
  }

  return (
    <div>
      {/* Portfolio selector */}
      <div className="mb-6">
        <label
          htmlFor="portfolio-selector"
          className="font-sans text-xs font-semibold uppercase tracking-wider text-txt-3 block mb-1"
        >
          Editing policy for
        </label>
        <select
          id="portfolio-selector"
          value={portfolioId ?? ''}
          onChange={handleSelectorChange}
          className="font-sans text-sm border border-edge-hair rounded-tile px-3 py-2 bg-surface-panel text-txt-1 focus:outline-none focus:border-brand w-72"
        >
          <option value="">House Default</option>
          {portfolios.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {/* Save feedback */}
      {saveState.kind === 'success' && (
        <div
          data-testid="save-success"
          className="mb-4 px-3 py-2 rounded-tile border border-sig-pos/40 bg-sig-pos-soft font-sans text-xs text-sig-pos"
        >
          Policy saved successfully.
        </div>
      )}
      {saveState.kind === 'error' && (
        <div
          data-testid="save-error"
          className="mb-4 px-3 py-2 rounded-tile border border-sig-neg/40 bg-sig-neg-soft font-sans text-xs text-sig-neg"
        >
          {saveState.message}
        </div>
      )}

      {/* Policy editor */}
      <PolicyEditor
        policy={saveState.kind === 'success' ? saveState.policy : activePolicy}
        mode={mode}
        onSave={handleSave}
      />
    </div>
  )
}
