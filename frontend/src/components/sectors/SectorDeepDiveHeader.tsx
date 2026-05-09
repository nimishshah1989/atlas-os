// frontend/src/components/sectors/SectorDeepDiveHeader.tsx
import Link from 'next/link'
import { ChevronRight } from 'lucide-react'
import type { SectorDecision } from '@/lib/sectors-decision'
import type { SectorBriefSnapshot } from '@/lib/queries/sector-deep-dive'
import { TimeRangeToggle } from '@/components/ui/TimeRangeToggle'
import type { TimeRange } from '@/lib/time-range'

type SnapshotWithDecision = SectorBriefSnapshot & { decision: SectorDecision }

const STATE_TONE: Record<string, { bg: string; text: string; dot: string; label: string }> = {
  Overweight:  { bg: 'bg-signal-pos/10',  text: 'text-signal-pos',  dot: 'bg-signal-pos',  label: 'Overweight' },
  Neutral:     { bg: 'bg-signal-warn/10', text: 'text-signal-warn', dot: 'bg-signal-warn', label: 'Neutral' },
  Underweight: { bg: 'bg-signal-neg/10',  text: 'text-signal-neg',  dot: 'bg-signal-neg',  label: 'Underweight' },
  Avoid:       { bg: 'bg-signal-neg/10',  text: 'text-signal-neg',  dot: 'bg-signal-neg',  label: 'Avoid' },
}

const DECISION_STYLE: Record<SectorDecision, string> = {
  'ENTER':     'bg-signal-pos text-paper',
  'HOLD':      'bg-teal text-paper',
  'ROTATE IN': 'bg-signal-warn text-paper',
  'WATCH':     'bg-ink-tertiary/20 text-ink-secondary',
  'PASS':      'bg-ink-tertiary/20 text-ink-tertiary',
  'EXIT':      'bg-signal-neg text-paper',
}

export function SectorDeepDiveHeader({
  snapshot,
  range,
}: {
  snapshot: SnapshotWithDecision
  range: TimeRange
}) {
  const stateTone = STATE_TONE[snapshot.sector_state] ?? STATE_TONE['Neutral']
  const dataDate = snapshot.data_date instanceof Date
    ? snapshot.data_date
    : new Date(snapshot.data_date as unknown as string)

  return (
    <div className="sticky top-14 bg-paper border-b border-paper-rule z-30">
      <div className="px-6 py-4">
        {/* Breadcrumb + meta row */}
        <div className="flex items-center justify-between mb-3">
          <nav className="flex items-center gap-1 font-sans text-xs text-ink-tertiary" aria-label="Breadcrumb">
            <Link href="/sectors" className="hover:text-ink-secondary transition-colors">
              Sectors
            </Link>
            <ChevronRight className="w-3 h-3" />
            <span className="text-ink-secondary">{snapshot.sector_name}</span>
          </nav>
          <div className="flex items-center gap-3">
            <span className="font-sans text-xs text-ink-tertiary">
              Data as of {dataDate.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
            </span>
            <TimeRangeToggle value={range} options={['1M', '3M', '6M', '1Y']} />
          </div>
        </div>

        {/* Headline row */}
        <div className="flex items-end justify-between flex-wrap gap-4">
          <div className="flex items-end gap-4">
            <h1 className="font-serif text-3xl font-semibold text-ink-primary leading-none">
              {snapshot.sector_name}
            </h1>
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm ${stateTone.bg}`}>
              <span className={`inline-block w-2 h-2 rounded-full ${stateTone.dot}`} />
              <span className={`font-sans text-xs font-semibold uppercase tracking-wide ${stateTone.text}`}>
                {stateTone.label}
              </span>
            </span>
            <span className={`inline-flex items-center px-2.5 py-1 rounded-sm font-sans text-xs font-bold uppercase tracking-wider ${DECISION_STYLE[snapshot.decision]}`}>
              {snapshot.decision}
            </span>
          </div>

          <div className="flex items-center gap-5 font-sans text-xs text-ink-tertiary">
            <span>
              <span className="font-mono font-semibold text-ink-primary">{snapshot.constituent_count}</span> stocks
            </span>
            {snapshot.divergence_flag && (
              <span className="text-signal-warn">⚠ divergence flagged</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
