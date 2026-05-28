// Trader-view tracking grid — at-call price, targets, realized today, band status.
// Only rendered when first_called_at exists (signal_call-backed verdicts).

export interface TrackingPoint {
  label: string
  value: string
  sub: string
  variant?: 'pos' | 'neg' | 'neutral'
}

interface TrackingGridProps {
  firstCalledAt: string
  points: TrackingPoint[]
}

export function TrackingGrid({ firstCalledAt, points }: TrackingGridProps) {
  return (
    <div className="py-3.5 border-t border-paper-rule">
      <div className="text-[10px] font-semibold tracking-wider uppercase text-ink-tertiary mb-2">
        Tracking since first call ({firstCalledAt})
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {points.map((p) => (
          <div key={p.label} data-testid="tracking-point">
            <div className="text-[10px] uppercase tracking-wider text-ink-tertiary">{p.label}</div>
            <div className={`font-mono text-[18px] font-semibold mt-1 ${
              p.variant === 'pos' ? 'text-signal-pos' :
              p.variant === 'neg' ? 'text-signal-neg' :
              'text-ink-secondary'
            }`}>
              {p.value}
            </div>
            <div className="text-[11px] text-ink-tertiary mt-0.5">{p.sub}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
