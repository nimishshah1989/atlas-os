// frontend/src/components/sectors/SectorViews.tsx
'use client'
import { useState, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import dynamic from 'next/dynamic'
import { Info, ChevronDown, ChevronUp } from 'lucide-react'
import type { SectorDecision } from '@/lib/sectors-decision'
import type {
  SectorSnapshot,
  SectorStateRow,
  RRGHistoryRow,
  BreadthWaterfallRow,
  DaysInStateRow,
} from '@/lib/queries/sectors'
import { SectorBubbleChart } from './SectorBubbleChart'
import { SectorDecisionTable } from './SectorDecisionTable'
import { SectorHeatmap } from './SectorHeatmap'
import { StateTransitionCard } from './StateTransitionCard'
import { BreadthWaterfall } from './BreadthWaterfall'

const RRGChart = dynamic(() => import('./RRGChart').then(m => ({ default: m.RRGChart })), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-64">
      <div className="grid grid-cols-5 gap-3 opacity-40">
        {Array.from({ length: 15 }).map((_, i) => (
          <div key={i} className="w-4 h-4 rounded-full bg-paper-rule animate-pulse" />
        ))}
      </div>
    </div>
  ),
})

type SectorWithDecision = SectorSnapshot & { decision: SectorDecision }

type ExcludedSector = {
  sector_name: string
  reason: 'non_actionable' | 'too_small'
  constituent_count: number
}

type Props = {
  actionable: SectorWithDecision[]
  excluded: ExcludedSector[]
  allSectors: SectorWithDecision[]
  stateHistory: SectorStateRow[]
  rrgHistory: RRGHistoryRow[]
  breadthData: BreadthWaterfallRow[]
  daysInState: DaysInStateRow[]
  range: string
}

function SectionDivider({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex items-baseline gap-3 mb-4">
      <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider">
        {title}
      </h2>
      {subtitle && (
        <span className="font-sans text-xs text-ink-tertiary">{subtitle}</span>
      )}
    </div>
  )
}

function BubbleHowToRead() {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1.5 font-sans text-[11px] text-ink-tertiary hover:text-ink-primary transition-colors"
        aria-expanded={open}
      >
        <Info className="w-3 h-3" />
        How to read this matrix
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <div className="mt-2 px-3.5 py-3 bg-paper-rule/10 border border-paper-rule rounded-sm grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-1.5 font-sans text-[11px] text-ink-secondary leading-relaxed">
          <div><span className="font-semibold text-ink-primary">X-axis (horizontal):</span> 3-month relative strength vs Nifty 500. Right of zero = outperforming the index; left = underperforming.</div>
          <div><span className="font-semibold text-ink-primary">Y-axis (vertical):</span> Breadth — % of stocks in the sector above their 50-day EMA. Higher = broader internal participation.</div>
          <div><span className="font-semibold text-ink-primary">Bubble size:</span> Number of stocks in the sector (larger = more constituents).</div>
          <div><span className="font-semibold text-ink-primary">Bubble color:</span> Sector state — green (Overweight), amber (Neutral), red (Underweight/Avoid).</div>
          <div className="sm:col-span-2"><span className="font-semibold text-ink-primary">Quadrant logic:</span> Top-right (Leaders) = strong RS + broad participation — the ideal position. Top-left (Recovering) = breadth solid but RS lagging — watch for rotation. Bottom-right (Narrowing) = RS positive but few stocks participating — fragile leadership. Bottom-left (Laggards) = avoid, capital preservation only. Click any bubble for the full sector deep-dive.</div>
        </div>
      )}
    </div>
  )
}

function RRGHowToRead() {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1.5 font-sans text-[11px] text-ink-tertiary hover:text-ink-primary transition-colors"
        aria-expanded={open}
      >
        <Info className="w-3 h-3" />
        How to read the RRG
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <div className="mt-2 px-3.5 py-3 bg-paper-rule/10 border border-paper-rule rounded-sm grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-1.5 font-sans text-[11px] text-ink-secondary leading-relaxed">
          <div><span className="font-semibold text-ink-primary">X-axis — RS Strength:</span> How far to the right a sector sits = how much it has outperformed the Nifty 500 over 3 months. Zero is the average — right is better, left is worse. Mean-centered so the cross is always at (0,0).</div>
          <div><span className="font-semibold text-ink-primary">Y-axis — RS Momentum:</span> The change in 3-month RS over the last 20 trading days. Above zero = sector is gaining ground vs the index. Below zero = losing ground, even if RS is still positive.</div>
          <div><span className="font-semibold text-ink-primary">Leading (top-right):</span> Strong RS + improving momentum. Best sectors to own. Stay positioned here.</div>
          <div><span className="font-semibold text-ink-primary">Weakening (bottom-right):</span> RS still positive but momentum fading. Start rotating out before it crosses zero.</div>
          <div><span className="font-semibold text-ink-primary">Lagging (bottom-left):</span> Underperforming and losing further ground. Avoid or exit. Recovery takes time.</div>
          <div><span className="font-semibold text-ink-primary">Improving (top-left):</span> RS negative but momentum turning. Early rotation signal — watch closely for a cross into Leading.</div>
          <div className="sm:col-span-2"><span className="font-semibold text-ink-primary">Typical rotation:</span> Sectors move clockwise — Leading → Weakening → Lagging → Improving → Leading. Trailing dots show the last 5 trading days; the solid bubble is today. Fast-moving trails signal accelerating sector rotation.</div>
        </div>
      )}
    </div>
  )
}

function ExcludedNote({
  excluded,
  showAll,
  onToggle,
}: {
  excluded: ExcludedSector[]
  showAll: boolean
  onToggle: () => void
}) {
  if (excluded.length === 0) return null
  const tooSmall = excluded.filter(e => e.reason === 'too_small')
  const nonActionable = excluded.filter(e => e.reason === 'non_actionable')
  return (
    <div className="font-sans text-[11px] text-ink-tertiary mt-3 leading-relaxed flex flex-wrap items-start justify-between gap-2">
      <div>
        <span className="font-medium">Hidden by default:</span>{' '}
        {nonActionable.length > 0 && (
          <span>
            {nonActionable.map(e => e.sector_name).join(', ')}{' '}
            <span className="text-ink-tertiary/70">(non-actionable bucket)</span>
          </span>
        )}
        {nonActionable.length > 0 && tooSmall.length > 0 && <span> · </span>}
        {tooSmall.length > 0 && (
          <span>
            {tooSmall.map(e => `${e.sector_name} (${e.constituent_count} stock${e.constituent_count === 1 ? '' : 's'})`).join(', ')}{' '}
            <span className="text-ink-tertiary/70">— too few constituents for reliable breadth</span>
          </span>
        )}
      </div>
      <button
        onClick={onToggle}
        className="font-sans text-[11px] text-ink-secondary hover:text-ink-primary underline decoration-dotted underline-offset-2"
      >
        {showAll ? '← Hide small sectors' : 'Show all sectors →'}
      </button>
    </div>
  )
}

const HEATMAP_RANGES = [
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '9M', days: 270 },
  { label: '12M', days: 365 },
] as const

export function SectorViews({
  actionable,
  excluded,
  allSectors,
  stateHistory,
  rrgHistory,
  breadthData,
  daysInState,
  range,
}: Props) {
  const router = useRouter()
  const [showAll, setShowAll] = useState(false)
  const [heatmapRange, setHeatmapRange] = useState<90 | 180 | 270 | 365>(180)

  const visible = showAll ? allSectors : actionable

  const onSelect = (name: string) => {
    router.push(`/sectors/${encodeURIComponent(name)}?range=${range}`)
  }

  const daysMap = new Map(daysInState.map(d => [d.sector_name, d.days_in_state]))
  const visibleWithDays = visible.map(s => ({
    ...s,
    days_in_state: daysMap.get(s.sector_name),
  }))

  // Filter heatmap history to selected range
  const cutoff = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - heatmapRange)
    return d.toISOString().slice(0, 10)
  }, [heatmapRange])

  const filteredHistory = useMemo(
    () => stateHistory.filter(row => {
      const d = row.date instanceof Date
        ? row.date.toISOString().slice(0, 10)
        : String(row.date).slice(0, 10)
      return d >= cutoff
    }),
    [stateHistory, cutoff],
  )

  return (
    <div className="space-y-0">
      {/* State transitions — always visible */}
      <div className="px-6 pt-6 pb-4 border-b border-paper-rule">
        <StateTransitionCard sectors={allSectors} daysInState={daysInState} />
      </div>

      {/* ── Section 1: Rotation Matrix ── */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <SectionDivider
          title="Positioning Matrix — RS vs Breadth"
          subtitle="Current snapshot · click any bubble for the sector deep dive"
        />
        <BubbleHowToRead />
        <SectorBubbleChart data={visible} range={range} onSelect={onSelect} />
        <ExcludedNote
          excluded={excluded}
          showAll={showAll}
          onToggle={() => setShowAll(s => !s)}
        />
      </div>

      {/* ── Section 2: Relative Rotation Graph ── */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <SectionDivider
          title="Relative Rotation Graph"
          subtitle="RS Strength vs RS Momentum — trailing dots show last 5 days"
        />
        <RRGHowToRead />
        <RRGChart current={visible} history={rrgHistory} onSelect={onSelect} />
      </div>

      {/* ── Section 3: Decision Table ── */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <SectionDivider
          title="Sector Decision Table"
          subtitle="Click any row for the full sector deep dive"
        />
        <SectorDecisionTable data={visibleWithDays} onSelect={onSelect} />
      </div>

      {/* ── Section 4: State History ── */}
      <div className="px-6 py-6">
        {/* Breadth Waterfall */}
        <div className="mb-10">
          <div className="flex items-baseline gap-3 mb-4">
            <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
              Breadth by RS State
              <span title="Share of stocks in each RS classification across all sectors, stacked over time. Green tones = Leader/Strong; gray = Neutral; red/orange = Weak/Laggard.">
                <Info className="w-3 h-3 opacity-60 cursor-help" />
              </span>
            </h2>
            <span className="font-sans text-[11px] text-ink-tertiary">Stacked share of universe by RS classification</span>
          </div>
          <BreadthWaterfall data={breadthData} />
        </div>

        {/* Sector State Heatmap */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
              Sector State History
              <span title="Daily sector classification over the selected range. Green = Overweight, Amber = Neutral, Red = Underweight/Avoid. Look for sectors that flipped recently.">
                <Info className="w-3 h-3 opacity-60 cursor-help" />
              </span>
            </h2>
            {/* Time range toggle */}
            <div className="flex items-center gap-0.5 bg-paper-rule/20 rounded-sm p-0.5">
              {HEATMAP_RANGES.map(({ label, days }) => (
                <button
                  key={label}
                  onClick={() => setHeatmapRange(days as 90 | 180 | 270 | 365)}
                  className={
                    'px-2.5 py-0.5 font-sans text-[10px] rounded-[2px] transition-colors ' +
                    (heatmapRange === days
                      ? 'bg-paper text-ink-primary font-medium shadow-sm'
                      : 'text-ink-tertiary hover:text-ink-secondary')
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <SectorHeatmap
            history={filteredHistory}
            sectors={visible.map(s => s.sector_name)}
          />
        </div>
      </div>
    </div>
  )
}
