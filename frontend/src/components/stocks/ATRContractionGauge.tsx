// frontend/src/components/stocks/ATRContractionGauge.tsx
// Horizontal 0-2 gauge for ATR contraction ratio with 1.0 midpoint marked.
// Pure server component — no Recharts, all CSS.
import type { ATRContraction } from '@/lib/queries/stocks'

interface ATRContractionGaugeProps {
  data: ATRContraction | null
}

export function ATRContractionGauge({ data }: ATRContractionGaugeProps) {
  if (data === null) {
    return (
      <section data-testid="atr-gauge">
        <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          Volatility contraction (ATR ratio)
        </h3>
        <p className="text-xs text-ink-tertiary mt-2">
          ATR contraction data unavailable (need 252+ trading days)
        </p>
      </section>
    )
  }

  const { ratio } = data
  const isContracting = ratio < 1.0
  const valueClass = isContracting ? 'text-signal-pos' : 'text-signal-neg'
  const barClass   = isContracting ? 'bg-signal-pos'  : 'bg-signal-neg'
  const label      = isContracting ? 'contracting (base-forming)' : 'expanding'

  // Gauge bar: clamp ratio to [0, 2.0], express as % of 0-2 scale
  const barPct = Math.min(ratio / 2.0, 1.0) * 100

  return (
    <section data-testid="atr-gauge">
      <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
        Volatility contraction (ATR ratio)
      </h3>

      <div className="flex items-baseline gap-3 mt-1">
        <span
          className={`font-mono text-lg font-medium ${valueClass}`}
          data-testid="atr-ratio"
        >
          {ratio.toFixed(2)}
        </span>
        <span className="text-xs text-ink-tertiary">{label}</span>
      </div>

      {/* Horizontal gauge: 0.0 (left) → 2.0 (right), with 1.0 line marked */}
      <div className="relative h-2 bg-paper-rule mt-3 rounded-full" data-testid="atr-gauge-track">
        {/* 1.0 midpoint marker */}
        <div
          className="absolute top-0 h-2 w-px bg-ink-secondary"
          style={{ left: '50%' }}
          aria-label="1.0 baseline"
        />
        {/* Fill bar */}
        <div
          className={`absolute top-0 h-2 rounded-full ${barClass}`}
          style={{ left: '0', width: `${barPct}%` }}
          data-testid="atr-gauge-fill"
        />
      </div>

      {/* Scale labels */}
      <div className="flex justify-between text-[10px] font-mono text-ink-tertiary mt-1">
        <span>0.0</span>
        <span>1.0</span>
        <span>2.0</span>
      </div>

      <p className="text-xs text-ink-tertiary mt-2 max-w-prose">
        Validated at 63d horizon (IR -0.48). Sub-1.0 = ATR-14 below its 252-day
        average — vol contracting — Minervini VCP base-forming. Sustained contraction
        precedes breakout.
      </p>
    </section>
  )
}
