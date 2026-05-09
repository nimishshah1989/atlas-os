'use client'
// src/components/portfolio/WeightTable.tsx
// Editable weight table for the Static portfolio builder.
// Equal-weight default. Per-row % input. Sum indicator. Auto-Normalize button.

import { useState, useEffect } from 'react'
import type { SelectedInstrument } from './InstrumentPicker'

export type WeightedInstrument = SelectedInstrument & {
  weight_pct: number
}

type Props = {
  selected: SelectedInstrument[]
  onWeightsChange: (weighted: WeightedInstrument[]) => void
  onRemove: (instrument_id: string) => void
}

const SUM_TOLERANCE = 0.5

function equalWeight(count: number): number {
  if (count === 0) return 0
  return parseFloat((100 / count).toFixed(4))
}

export function WeightTable({ selected, onWeightsChange, onRemove }: Props) {
  // Initialize weights as equal-weight for each instrument
  const [weights, setWeights] = useState<Record<string, number>>(() => {
    const w: Record<string, number> = {}
    const eq = equalWeight(selected.length)
    selected.forEach((s) => { w[s.instrument_id] = eq })
    return w
  })

  // When the selection changes (add/remove), reset to equal-weight
  useEffect(() => {
    const eq = equalWeight(selected.length)
    const newW: Record<string, number> = {}
    selected.forEach((s) => { newW[s.instrument_id] = eq })
    setWeights(newW)
  }, [selected.length]) // intentional: only reset when count changes

  // Notify parent on every weight change
  useEffect(() => {
    const weighted: WeightedInstrument[] = selected.map((s) => ({
      ...s,
      weight_pct: weights[s.instrument_id] ?? 0,
    }))
    onWeightsChange(weighted)
  }, [weights]) // intentional: notify on weight object change only

  const weightSum = Object.values(weights).reduce((a, b) => a + b, 0)
  const isValid = Math.abs(weightSum - 100) <= SUM_TOLERANCE

  function handleWeightChange(id: string, raw: string) {
    const val = parseFloat(raw)
    setWeights((prev) => ({ ...prev, [id]: isNaN(val) ? 0 : val }))
  }

  function handleNormalize() {
    if (weightSum === 0) return
    setWeights((prev) => {
      const normalized: Record<string, number> = {}
      for (const [id, w] of Object.entries(prev)) {
        normalized[id] = parseFloat(((w / weightSum) * 100).toFixed(4))
      }
      return normalized
    })
  }

  if (selected.length === 0) {
    return (
      <p className="font-sans text-xs text-ink-tertiary py-3">
        No instruments selected yet. Pick instruments above.
      </p>
    )
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              {['Instrument', 'Type', 'Weight %', ''].map((col) => (
                <th
                  key={col}
                  className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {selected.map((inst) => (
              <tr key={inst.instrument_id} className="border-b border-paper-rule/50">
                <td className="py-2 pr-4">
                  <p className="font-mono text-xs text-ink-primary">{inst.display_name}</p>
                  <p className="font-sans text-xs text-ink-tertiary">{inst.meta}</p>
                </td>
                <td className="py-2 pr-4 font-sans text-xs text-ink-secondary capitalize">
                  {inst.instrument_type}
                </td>
                <td className="py-2 pr-4">
                  <input
                    type="number"
                    min="0.01"
                    max="100"
                    step="0.01"
                    value={weights[inst.instrument_id] ?? 0}
                    onChange={(e) => handleWeightChange(inst.instrument_id, e.target.value)}
                    className="w-20 font-mono text-xs px-2 py-1 border border-paper-rule rounded-[2px] bg-paper text-ink-primary text-right focus:outline-none focus:border-accent"
                    aria-label={`Weight for ${inst.display_name}`}
                  />
                </td>
                <td className="py-2">
                  <button
                    type="button"
                    onClick={() => onRemove(inst.instrument_id)}
                    className="font-sans text-xs text-ink-tertiary hover:text-signal-neg transition-colors"
                    aria-label={`Remove ${inst.display_name}`}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Sum indicator + normalize */}
      <div className="flex items-center gap-4 mt-3">
        <span
          className={`font-sans text-xs font-medium ${
            isValid ? 'text-signal-pos' : 'text-signal-warn'
          }`}
        >
          {isValid
            ? `✓ Sums to 100%`
            : `⚠ ${weightSum.toFixed(2)}% allocated`}
        </span>
        <button
          type="button"
          onClick={handleNormalize}
          className="font-sans text-xs text-accent underline decoration-dotted hover:decoration-solid transition-all"
        >
          Auto-Normalize
        </button>
      </div>
    </div>
  )
}
