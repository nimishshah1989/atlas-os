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

function Collapsible({
  label,
  defaultOpen = false,
  children,
}: {
  label: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1.5 font-sans text-[11px] text-ink-tertiary hover:text-ink-primary transition-colors"
        aria-expanded={open}
      >
        <Info className="w-3 h-3" />
        {label}
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <div className="mt-2 px-3.5 py-3 bg-paper-rule/10 border border-paper-rule rounded-sm grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-1.5 font-sans text-[11px] text-ink-secondary leading-relaxed">
          {children}
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

const BREADTH_RANGES = [
  { label: '3M',  days: 90 },
  { label: '6M',  days: 180 },
  { label: '1Y',  days: 365 },
  { label: '2Y',  days: 730 },
  { label: '3Y',  days: 1095 },
] as const

function RangeToggle<T extends number>({
  value,
  options,
  onChange,
}: {
  value: T
  options: readonly { label: string; days: number }[]
  onChange: (days: T) => void
}) {
  return (
    <div className="flex items-center gap-0.5 bg-paper-rule/20 rounded-sm p-0.5">
      {options.map(({ label, days }) => (
        <button
          key={label}
          onClick={() => onChange(days as T)}
          className={
            'px-2.5 py-0.5 font-sans text-[10px] rounded-[2px] transition-colors ' +
            (value === days
              ? 'bg-paper text-ink-primary font-medium shadow-sm'
              : 'text-ink-tertiary hover:text-ink-secondary')
          }
        >
          {label}
        </button>
      ))}
    </div>
  )
}

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
  const [breadthRange, setBreadthRange] = useState<90 | 180 | 365 | 730 | 1095>(365)

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
  const heatmapCutoff = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - heatmapRange)
    return d.toISOString().slice(0, 10)
  }, [heatmapRange])

  const filteredHistory = useMemo(
    () => stateHistory.filter(row => {
      const d = row.date instanceof Date
        ? row.date.toISOString().slice(0, 10)
        : String(row.date).slice(0, 10)
      return d >= heatmapCutoff
    }),
    [stateHistory, heatmapCutoff],
  )

  // Filter breadth data to selected range
  const breadthCutoff = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - breadthRange)
    return d.toISOString().slice(0, 10)
  }, [breadthRange])

  const filteredBreadthData = useMemo(
    () => breadthData.filter(row => String(row.date).slice(0, 10) >= breadthCutoff),
    [breadthData, breadthCutoff],
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
        <Collapsible label="How to read this matrix" defaultOpen>
          <div><span className="font-semibold text-ink-primary">X-axis (horizontal):</span> 3-month relative strength vs Nifty 500. Right of zero = outperforming the index; left = underperforming.</div>
          <div><span className="font-semibold text-ink-primary">Y-axis (vertical):</span> Breadth — % of stocks in the sector above their 50-day EMA. Higher = broader internal participation.</div>
          <div><span className="font-semibold text-ink-primary">Bubble size:</span> Number of stocks in the sector (larger = more constituents).</div>
          <div><span className="font-semibold text-ink-primary">Bubble color:</span> Sector state — green (Overweight), amber (Neutral), red (Underweight/Avoid).</div>
          <div className="sm:col-span-2"><span className="font-semibold text-ink-primary">Quadrant logic:</span> Top-right (Leaders) = strong RS + broad participation — the ideal position. Top-left (Recovering) = breadth solid but RS lagging — watch for rotation. Bottom-right (Narrowing) = RS positive but few stocks participating — fragile leadership. Bottom-left (Laggards) = avoid, capital preservation only. Click any bubble for the full sector deep-dive.</div>
        </Collapsible>
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
        <p className="font-sans text-[11px] text-ink-secondary mb-3 max-w-3xl leading-relaxed">
          The RRG plots where each sector sits relative to the Nifty 500 on two axes: how much it has outperformed (X) and whether that outperformance is accelerating or fading (Y). Sectors rotate clockwise through four quadrants — <span className="font-medium text-signal-pos">Leading</span> → <span className="font-medium text-signal-warn">Weakening</span> → <span className="font-medium text-ink-tertiary">Lagging</span> → <span className="font-medium text-teal">Improving</span> → Leading. Trailing dots show the last 5 trading days; fast-moving trails signal active sector rotation. Use this to get ahead of transitions before they show up in price.
        </p>
        <Collapsible label="Detailed axis and quadrant guide" defaultOpen>
          <div><span className="font-semibold text-ink-primary">X-axis — RS Strength:</span> How far to the right a sector sits = how much it has outperformed the Nifty 500 over 3 months. Zero is the average — right is better, left is worse. Mean-centered so the cross is always at (0,0).</div>
          <div><span className="font-semibold text-ink-primary">Y-axis — RS Momentum:</span> The change in 3-month RS over the last 20 trading days. Above zero = sector is gaining ground vs the index. Below zero = losing ground, even if RS is still positive.</div>
          <div><span className="font-semibold text-ink-primary">Leading (top-right):</span> Strong RS + improving momentum. Best sectors to own. Stay positioned here.</div>
          <div><span className="font-semibold text-ink-primary">Weakening (bottom-right):</span> RS still positive but momentum fading. Start rotating out before it crosses zero.</div>
          <div><span className="font-semibold text-ink-primary">Lagging (bottom-left):</span> Underperforming and losing further ground. Avoid or exit. Recovery takes time.</div>
          <div><span className="font-semibold text-ink-primary">Improving (top-left):</span> RS negative but momentum turning. Early rotation signal — watch closely for a cross into Leading.</div>
          <div className="sm:col-span-2"><span className="font-semibold text-ink-primary">How to act on it:</span> Own Leading sectors with broad RS breadth. Trim Weakening positions. Avoid Lagging. Watch Improving sectors — they are tomorrow&apos;s Leading if the regime supports risk. Fast clockwise rotation with large trailing dots = conviction. Slow or counter-clockwise = indecision.</div>
        </Collapsible>
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

      {/* ── Section 4: Breadth + State History ── */}
      <div className="px-6 py-6">
        {/* Breadth Waterfall */}
        <div className="mb-10">
          <div className="flex items-center justify-between mb-1">
            <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
              Breadth by RS State
              <span title="Share of ALL stocks in the universe in each RS classification, stacked over time. Green tones = Leader/Strong; gray = Neutral; red/orange = Weak/Laggard. Regime health = how much green sits at the top.">
                <Info className="w-3 h-3 opacity-60 cursor-help" />
              </span>
            </h2>
            <RangeToggle
              value={breadthRange}
              options={BREADTH_RANGES}
              onChange={setBreadthRange}
            />
          </div>
          <p className="font-sans text-[11px] text-ink-secondary mb-4 max-w-3xl leading-relaxed">
            Each stacked bar shows the proportion of all universe stocks in each RS classification on that date.
            A healthy market has a thick green band (Leader + Strong) at the top. Watch for the green band expanding after risk-off periods — that&apos;s the first sign of a broadening recovery.
            Rising Laggard + Weak (red/orange) below the midline signals deteriorating breadth before price follows.
          </p>
          <BreadthWaterfall data={filteredBreadthData} />
        </div>

        {/* Sector State Heatmap */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <h2 className="font-sans text-xs font-semibold text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
              Sector State History
              <span title="Daily sector classification over the selected range. Green = Overweight, Amber = Neutral, Red = Underweight/Avoid.">
                <Info className="w-3 h-3 opacity-60 cursor-help" />
              </span>
            </h2>
            <RangeToggle
              value={heatmapRange}
              options={HEATMAP_RANGES}
              onChange={setHeatmapRange}
            />
          </div>
          <p className="font-sans text-[11px] text-ink-secondary mb-4 max-w-3xl leading-relaxed">
            Each cell shows a sector&apos;s classification for that day.{' '}
            <span className="text-signal-pos font-medium">Green = Overweight</span>,{' '}
            <span className="text-signal-warn font-medium">Amber = Neutral</span>,{' '}
            <span className="text-signal-neg font-medium">Red = Underweight/Avoid</span>.
            Sustained runs signal conviction and momentum alignment. Fresh color flips — especially sector → Overweight — signal active rotations worth investigating in the bubble chart.
            A sector that has stayed Overweight for 60+ days is a core position; one that flipped in the last 5 is a new entry candidate.
          </p>
          <SectorHeatmap
            history={filteredHistory}
            sectors={visible.map(s => s.sector_name)}
          />
        </div>
      </div>
    </div>
  )
}
