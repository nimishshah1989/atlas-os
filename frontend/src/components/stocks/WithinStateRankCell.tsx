// frontend/src/components/stocks/WithinStateRankCell.tsx
// Renders within_state_rank (0..1) as a 2-decimal number with a tiny
// progress bar. Replaces ConvictionCell — same visual real-estate, but
// the value now comes from the IC-validated state engine.

interface Props {
  value: number | null
}

export function WithinStateRankCell({ value }: Props) {
  if (value === null || value === undefined) {
    return <span className="font-mono text-xs text-ink-tertiary">—</span>
  }
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className="flex items-center gap-2 min-w-[80px]">
      <div
        className="h-1.5 flex-1 bg-paper-rule rounded-sm overflow-hidden"
        data-testid="wsr-track"
      >
        <div
          className="h-full bg-signal-pos"
          style={{ width: `${pct}%` }}
          data-testid="wsr-fill"
        />
      </div>
      <span className="font-mono text-xs text-ink-primary tabular-nums">
        {value.toFixed(2)}
      </span>
    </div>
  )
}
