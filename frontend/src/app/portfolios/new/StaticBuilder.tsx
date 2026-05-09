'use client'
// src/app/portfolios/new/StaticBuilder.tsx
// Static portfolio builder — 4-step form: Name → Picker → Weights → Submit.
// Client island. Calls createStaticPortfolio Server Action.

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import type { StockPickerRow, ETFPickerRow, FundPickerRow } from '@/lib/queries/instruments'
import { InstrumentPicker, type SelectedInstrument } from '@/components/portfolio/InstrumentPicker'
import { WeightTable, type WeightedInstrument } from '@/components/portfolio/WeightTable'
import { createStaticPortfolio, getPortfolioStatusAction } from './actions'

type Props = {
  stocks: StockPickerRow[]
  etfs: ETFPickerRow[]
  funds: FundPickerRow[]
}

type SubmitState =
  | { phase: 'idle' }
  | { phase: 'creating' }
  | { phase: 'polling'; portfolioId: string; elapsed: number }
  | { phase: 'error'; message: string }

export function StaticBuilder({ stocks, etfs, funds }: Props) {
  const router = useRouter()
  const [name, setName] = useState('')
  const [selected, setSelected] = useState<SelectedInstrument[]>([])
  const [weighted, setWeighted] = useState<WeightedInstrument[]>([])
  const [submitState, setSubmitState] = useState<SubmitState>({ phase: 'idle' })

  const selectedIds = new Set(selected.map((s) => s.instrument_id))

  const handleSelect = useCallback((instrument: SelectedInstrument) => {
    setSelected((prev) => [...prev, instrument])
  }, [])

  const handleRemove = useCallback((instrument_id: string) => {
    setSelected((prev) => prev.filter((s) => s.instrument_id !== instrument_id))
  }, [])

  async function handleSubmit() {
    if (!name.trim()) {
      setSubmitState({ phase: 'error', message: 'Portfolio name is required' })
      return
    }
    if (selected.length === 0) {
      setSubmitState({ phase: 'error', message: 'Pick at least one instrument' })
      return
    }

    setSubmitState({ phase: 'creating' })

    const instruments = weighted.map((w) => ({
      instrument_id: w.instrument_id,
      instrument_type: w.instrument_type,
      weight_pct: w.weight_pct,
    }))

    const result = await createStaticPortfolio(name, instruments)

    if (!result.ok) {
      setSubmitState({ phase: 'error', message: result.error })
      return
    }

    // Poll until backtest completes
    const portfolioId = result.portfolio_id
    const startTime = Date.now()
    setSubmitState({ phase: 'polling', portfolioId, elapsed: 0 })

    const poll = async () => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      setSubmitState({ phase: 'polling', portfolioId, elapsed })

      const status = await getPortfolioStatusAction(portfolioId)
      if (!status.ok) {
        // Network error — keep polling optimistically
        setTimeout(poll, 3000)
        return
      }
      if (status.status === 'completed') {
        router.push(`/portfolios/${portfolioId}`)
        return
      }
      setTimeout(poll, 3000)
    }
    setTimeout(poll, 3000)
  }

  const isSubmitting =
    submitState.phase === 'creating' || submitState.phase === 'polling'

  return (
    <div className="space-y-8">
      {/* Step 1: Name */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-2">
          Step 1: Name your portfolio
        </h2>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Banking Leaders Q2 2026"
          className="w-full md:w-96 font-sans text-sm px-3 py-2 border border-paper-rule rounded-[2px] bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent"
          disabled={isSubmitting}
        />
      </section>

      {/* Step 2: Pick instruments */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-2">
          Step 2: Pick instruments
          {selected.length > 0 && (
            <span className="ml-2 font-sans text-xs text-ink-tertiary font-normal">
              ({selected.length} selected)
            </span>
          )}
        </h2>
        <div className="flex gap-4 flex-col lg:flex-row">
          <div className="flex-1 min-w-0">
            <InstrumentPicker
              stocks={stocks}
              etfs={etfs}
              funds={funds}
              selectedIds={selectedIds}
              onSelect={handleSelect}
            />
          </div>
          {selected.length > 0 && (
            <div className="lg:w-64 flex-shrink-0">
              <div className="border border-paper-rule rounded-[2px] p-3 sticky top-20">
                <p className="font-sans text-xs font-semibold text-ink-secondary uppercase tracking-wide mb-2">
                  Selected ({selected.length})
                </p>
                <div className="space-y-1 max-h-64 overflow-y-auto">
                  {selected.map((s) => (
                    <div
                      key={s.instrument_id}
                      className="flex items-center justify-between gap-2 py-1"
                    >
                      <span className="font-mono text-xs text-ink-primary truncate">
                        {s.display_name}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRemove(s.instrument_id)}
                        className="font-sans text-xs text-ink-tertiary hover:text-signal-neg flex-shrink-0"
                        aria-label={`Remove ${s.display_name}`}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Step 3: Set weights */}
      {selected.length > 0 && (
        <section>
          <h2 className="font-sans text-sm font-semibold text-ink-primary mb-2">
            Step 3: Set weights
          </h2>
          <WeightTable
            selected={selected}
            onWeightsChange={setWeighted}
            onRemove={handleRemove}
          />
        </section>
      )}

      {/* Step 4: Submit */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-2">
          Step 4: Submit
        </h2>
        {submitState.phase === 'error' && (
          <p className="font-sans text-sm text-signal-neg mb-3">{submitState.message}</p>
        )}
        {submitState.phase === 'polling' && (
          <p className="font-sans text-sm text-ink-secondary mb-3">
            Backtest running… ({submitState.elapsed}s elapsed)
          </p>
        )}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting}
          className={`font-sans text-sm px-6 py-2.5 rounded-[2px] border transition-colors ${
            isSubmitting
              ? 'bg-paper-rule/30 border-paper-rule text-ink-tertiary cursor-wait'
              : 'bg-accent text-white border-accent hover:bg-accent/90'
          }`}
        >
          {submitState.phase === 'creating'
            ? 'Creating…'
            : submitState.phase === 'polling'
            ? 'Backtest running…'
            : 'Create + Backtest'}
        </button>
      </section>
    </div>
  )
}
