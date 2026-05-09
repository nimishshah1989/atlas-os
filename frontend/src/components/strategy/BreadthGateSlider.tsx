'use client'
// src/components/strategy/BreadthGateSlider.tsx
// Single breadth gate row with on/off toggle + slider when active.

import type { BreadthGate } from '@/lib/rule-catalogs'
import { formatBreadthValue } from '@/lib/rule-catalogs'

type Props = {
  gate: BreadthGate
  value: number | null
  onChange: (v: number | null) => void
}

export function BreadthGateSlider({ gate, value, onChange }: Props) {
  const isActive = value !== null

  const handleToggle = () => {
    if (isActive) {
      onChange(null)
    } else {
      // Default to midpoint of range on enable
      const mid = parseFloat(((gate.min + gate.max) / 2).toFixed(2))
      onChange(mid)
    }
  }

  const handleSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(parseFloat(e.target.value))
  }

  return (
    <div className="flex flex-col gap-1.5 py-2 border-b border-paper-rule/40 last:border-b-0">
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="font-sans text-xs font-medium text-ink-primary">{gate.label}</p>
          <p className="font-sans text-xs text-ink-tertiary">{gate.help}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {isActive && (
            <span
              data-testid={`gate-value-${gate.key}`}
              className="font-mono text-xs text-ink-primary min-w-[3rem] text-right"
            >
              ≥ {formatBreadthValue(value, gate.fmt)}
            </span>
          )}
          <button
            type="button"
            role="switch"
            aria-checked={isActive}
            aria-label={`Toggle ${gate.label}`}
            onClick={handleToggle}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
              isActive ? 'bg-accent' : 'bg-paper-rule'
            }`}
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                isActive ? 'translate-x-4' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
      </div>
      {isActive && (
        <input
          type="range"
          min={gate.min}
          max={gate.max}
          step={gate.step}
          value={value}
          onChange={handleSlider}
          aria-label={`${gate.label} threshold`}
          className="w-full accent-accent"
        />
      )}
    </div>
  )
}
