'use client'
// src/components/strategy/KPICard.tsx
// Reusable KPI tile for strategy metrics.

type Props = {
  label: string
  value: string | null
  delta?: string | null    // e.g. "+2.3% vs benchmark"
  deltaPositive?: boolean  // controls color of delta
  loading?: boolean
}

export function KPICard({ label, value, delta, deltaPositive, loading = false }: Props) {
  if (loading) {
    return (
      <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
        <div className="animate-pulse space-y-2">
          <div className="h-3 bg-paper-rule/30 rounded-[2px] w-2/3" />
          <div className="h-6 bg-paper-rule/30 rounded-[2px] w-1/2 mt-2" />
        </div>
      </div>
    )
  }

  return (
    <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
      <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-1">
        {label}
      </p>
      <p className="font-mono text-xl font-semibold text-ink-primary">
        {value ?? '—'}
      </p>
      {delta != null && (
        <p
          className={`font-sans text-xs mt-1 ${
            deltaPositive ? 'text-signal-pos' : 'text-signal-neg'
          }`}
        >
          {delta}
        </p>
      )}
    </div>
  )
}
