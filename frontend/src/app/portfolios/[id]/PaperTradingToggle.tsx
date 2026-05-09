'use client'
// src/app/portfolios/[id]/PaperTradingToggle.tsx
// Toggle button for paper_trading_active. Calls togglePaperTradingAction.
// Tooltip: "Paper trading hookup ships with M16."

import { useState } from 'react'
import { togglePaperTradingAction } from '../new/actions'

type Props = {
  portfolioId: string
  currentActive: boolean
}

export function PaperTradingToggle({ portfolioId, currentActive }: Props) {
  const [active, setActive] = useState(currentActive)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleToggle() {
    setLoading(true)
    setError(null)
    const result = await togglePaperTradingAction(portfolioId, !active)
    setLoading(false)
    if (result.ok) {
      setActive((prev) => !prev)
    } else {
      setError(result.error)
    }
  }

  return (
    <div className="flex items-center gap-4">
      <button
        type="button"
        onClick={handleToggle}
        disabled={loading}
        title="Paper trading hookup ships with M16."
        className={`font-sans text-sm px-4 py-2 rounded-[2px] border transition-colors ${
          active
            ? 'bg-signal-pos/10 border-signal-pos/30 text-signal-pos hover:bg-signal-pos/20'
            : 'bg-paper border-paper-rule text-ink-secondary hover:border-accent hover:text-accent'
        } ${loading ? 'opacity-60 cursor-wait' : ''}`}
      >
        {loading ? 'Saving…' : active ? 'Deactivate Paper Trading' : 'Activate Paper Trading'}
      </button>
      <span className="font-sans text-xs text-ink-tertiary">
        Paper trading hookup ships with M16.
      </span>
      {error && (
        <span className="font-sans text-xs text-signal-neg">{error}</span>
      )}
    </div>
  )
}
