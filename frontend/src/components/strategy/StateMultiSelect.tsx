'use client'
// src/components/strategy/StateMultiSelect.tsx
// Chip-based multi-select for state values.
// Click toggles individual chips. Mirrors EditGatePolicyModal checkbox-group pattern.

type Props = {
  title: string
  options: readonly string[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
  help?: string
}

export function StateMultiSelect({ title, options, selected, onChange, help }: Props) {
  const toggle = (value: string) => {
    const next = new Set(selected)
    if (next.has(value)) {
      next.delete(value)
    } else {
      next.add(value)
    }
    onChange(next)
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <p className="font-sans text-xs font-medium text-ink-secondary uppercase tracking-wide">
          {title}
        </p>
        {selected.size > 0 && (
          <span className="font-sans text-xs text-ink-tertiary">
            ({selected.size} selected)
          </span>
        )}
      </div>
      {help && (
        <p className="font-sans text-xs text-ink-tertiary">{help}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = selected.has(option)
          return (
            <button
              key={option}
              type="button"
              onClick={() => toggle(option)}
              aria-pressed={isSelected}
              className={`font-mono text-xs px-2.5 py-1 rounded-[2px] border transition-colors ${
                isSelected
                  ? 'bg-accent text-white border-accent'
                  : 'bg-paper text-ink-secondary border-paper-rule hover:border-accent hover:text-ink-primary'
              }`}
            >
              {option}
            </button>
          )
        })}
      </div>
    </div>
  )
}
