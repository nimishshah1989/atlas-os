// frontend/src/components/stocks/DwellTimeline.tsx
// 252-day color-coded state strip. Each bar = one trading day.
// Most recent day is rightmost. Pure server component.
import type { StateHistoryEntry } from '@/lib/queries/states'

interface DwellTimelineProps {
  /** Ordered most recent first (as returned by getStateHistory). */
  history: StateHistoryEntry[]
}

const MIN_BARS = 30

// ---------------------------------------------------------------------------
// State → Tailwind background color class
// ---------------------------------------------------------------------------

const STATE_BAR_COLOR: Record<string, string> = {
  stage_1:      'bg-paper-rule',
  stage_2a:     'bg-signal-pos',
  stage_2b:     'bg-signal-pos opacity-80',
  stage_2c:     'bg-signal-warn',
  stage_3:      'bg-signal-warn opacity-60',
  stage_4:      'bg-signal-neg',
  uninvestable: 'bg-ink-tertiary',
}

// For legend display
const LEGEND_ITEMS: { state: string; label: string; colorClass: string }[] = [
  { state: 'stage_1',      label: 'Stage 1',      colorClass: 'bg-paper-rule' },
  { state: 'stage_2a',     label: 'Stage 2A',     colorClass: 'bg-signal-pos' },
  { state: 'stage_2b',     label: 'Stage 2B',     colorClass: 'bg-signal-pos opacity-80' },
  { state: 'stage_2c',     label: 'Stage 2C',     colorClass: 'bg-signal-warn' },
  { state: 'stage_3',      label: 'Stage 3',      colorClass: 'bg-signal-warn opacity-60' },
  { state: 'stage_4',      label: 'Stage 4',      colorClass: 'bg-signal-neg' },
  { state: 'uninvestable', label: 'Uninvestable', colorClass: 'bg-ink-tertiary' },
]

function barColor(state: string): string {
  return STATE_BAR_COLOR[state] ?? 'bg-paper-rule'
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DwellTimeline({ history }: DwellTimelineProps) {
  if (history.length < MIN_BARS) {
    return (
      <section data-testid="dwell-timeline">
        <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
          State history · 252 days
        </h3>
        <p className="text-xs text-ink-tertiary mt-2">Insufficient history (need 30+ days)</p>
      </section>
    )
  }

  // getStateHistory returns most-recent-first; reverse for left→right display
  const bars = [...history].reverse()

  // Determine which states are actually present (for legend)
  const presentStates = new Set(history.map((h) => h.state))

  return (
    <section data-testid="dwell-timeline">
      <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
        State history · {history.length} days
      </h3>

      {/* Color-coded bar strip */}
      <div
        className="flex w-full gap-px mt-3 rounded-[2px] overflow-hidden"
        style={{ height: 16 }}
        role="img"
        aria-label={`${history.length}-day state history`}
        data-testid="dwell-bars"
      >
        {bars.map((entry) => (
          <div
            key={entry.date}
            className={`flex-1 ${barColor(entry.state)}`}
            style={{ minWidth: 1 }}
            title={`${entry.date}: ${entry.state} (day ${entry.dwell_days} in state)`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {LEGEND_ITEMS.filter((item) => presentStates.has(item.state)).map((item) => (
          <span
            key={item.state}
            className="flex items-center gap-1 text-[10px] font-sans text-ink-secondary"
          >
            <span className={`inline-block w-3 h-3 rounded-[1px] ${item.colorClass}`} />
            {item.label}
          </span>
        ))}
      </div>
    </section>
  )
}
