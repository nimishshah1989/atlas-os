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
import { EXCLUDED_SECTORS } from '@/lib/sectors-filter'
import { SectorBubbleChart, type XView } from './SectorBubbleChart'
import { SectorDecisionTable } from './SectorDecisionTable'
import { SectorHeatmap } from './SectorHeatmap'
import { StateTransitionCard } from './StateTransitionCard'
import { BreadthWaterfall } from './BreadthWaterfall'
import { SectorDualChartGuide } from './SectorDualChartGuide'
import { SectorEventPlaybook } from './SectorEventPlaybook'
import type { PlaybookEntry } from '@/lib/queries/sectors'

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
  playbook: PlaybookEntry[]
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
  playbook,
  range,
}: Props) {
  const router = useRouter()
  const [showAll, setShowAll] = useState(false)
  const [bubbleXView, setBubbleXView] = useState<'rs-3m' | 'ret-1m' | 'ret-3m' | 'ret-6m'>('rs-3m')
  const [heatmapRange, setHeatmapRange] = useState<90 | 180 | 270 | 365>(180)
  const [breadthRange, setBreadthRange] = useState<90 | 180 | 365 | 730 | 1095>(365)

  const filteredAllSectors = useMemo(
    () => allSectors.filter(s => !EXCLUDED_SECTORS.includes(s.sector_name)),
    [allSectors],
  )
  const visible = showAll ? filteredAllSectors : actionable

  const onSelect = (name: string) => {
    router.push(`/sectors/${encodeURIComponent(name)}?range=${range}`)
  }

  const daysMap = new Map(daysInState.map(d => [d.sector_name, d.days_in_state]))
  const visibleWithDays = visible.map(s => ({
    ...s,
    days_in_state: daysMap.get(s.sector_name),
  }))

  const overweightSectors = visible
    .filter(s => s.sector_state === 'Overweight')
    .map(s => s.sector_name)

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

  const meanRS = useMemo(() => {
    const vals = visible
      .map(s => parseFloat(s.bottomup_rs_3m_nifty500 ?? 'NaN'))
      .filter(v => !isNaN(v))
    return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
  }, [visible])

  const leadingRRGCount = useMemo(
    () =>
      visible.filter(s => {
        const rs  = parseFloat(s.bottomup_rs_3m_nifty500 ?? 'NaN')
        const mom = parseFloat(s.rs_momentum ?? 'NaN')
        return !isNaN(rs) && !isNaN(mom) && rs - meanRS > 0 && mom > 0
      }).length,
    [visible, meanRS],
  )

  return (
    <div className="space-y-0">
      {/* State transitions — always visible */}
      <div className="px-6 pt-6 pb-4 border-b border-paper-rule">
        <StateTransitionCard sectors={allSectors} daysInState={daysInState} />
      </div>

      {/* ── Section 1: Rotation Matrix ── */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <div className="flex items-baseline justify-between gap-3 mb-4">
          <SectionDivider
            title="Positioning Matrix — RS vs Breadth"
            subtitle="Current snapshot · click any bubble for the sector deep dive"
          />
          {/* X-axis toggle */}
          <div className="flex items-center gap-1 flex-shrink-0">
            <span className="font-sans text-[10px] text-ink-tertiary mr-1">X axis:</span>
            {([['rs-3m', 'RS 3M'], ['ret-1m', '1M Ret'], ['ret-3m', '3M Ret'], ['ret-6m', '6M Ret']] as [XView, string][]).map(([v, label]) => (
              <button
                key={v}
                onClick={() => setBubbleXView(v)}
                className={`px-2 py-0.5 rounded-[2px] font-sans text-[10px] transition-colors ${
                  bubbleXView === v
                    ? 'bg-ink-primary text-paper'
                    : 'border border-paper-rule text-ink-tertiary hover:text-ink-primary'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <Collapsible label="How to read this matrix" defaultOpen>
          <div><span className="font-semibold text-ink-primary">X-axis (horizontal):</span> {bubbleXView === 'rs-3m' ? '3-month relative strength vs Nifty 500. Right of zero = outperforming the index; left = underperforming.' : `Bottom-up average return over the selected period. Toggle between RS 3M and 1M/3M/6M returns using the buttons above — RS view shows relative performance; return view shows absolute gains.`}</div>
          <div><span className="font-semibold text-ink-primary">Y-axis (vertical):</span> Breadth — % of stocks in the sector above their 50-day EMA. Higher = broader internal participation.</div>
          <div><span className="font-semibold text-ink-primary">Bubble size:</span> Number of stocks in the sector (larger = more constituents).</div>
          <div><span className="font-semibold text-ink-primary">Bubble color:</span> Sector state — green (Overweight), amber (Neutral), red (Underweight/Avoid).</div>
          <div className="sm:col-span-2"><span className="font-semibold text-ink-primary">Note on temporal toggles:</span> The RRG (below) is anchored to 3M RS because relative strength requires a fixed lookback period — 1M RS and 6M RS would need separate backend computation. Use the X-axis toggle above (on this bubble chart) to compare sectors by 1M or 6M absolute returns instead.</div>
        </Collapsible>
        <SectorBubbleChart data={visible} xView={bubbleXView} onSelect={onSelect} />
        <ExcludedNote
          excluded={excluded}
          showAll={showAll}
          onToggle={() => setShowAll(s => !s)}
        />
      </div>

      {/* ── Dual Chart Reading Guide ── */}
      <SectorDualChartGuide sectors={visible} />

      {/* ── Section 2: Relative Rotation Graph ── */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <SectionDivider
          title="Relative Rotation Graph"
          subtitle="RS Strength vs RS Momentum — trailing dots show last 5 days"
        />
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_260px] gap-6 items-start">
          {/* Chart — fills the left column */}
          <RRGChart current={visible} history={rrgHistory} onSelect={onSelect} />

          {/* Commentary panel — always visible on the right */}
          <div className="font-sans text-[11px] text-ink-secondary space-y-4 pt-1">
            <p className="leading-relaxed text-ink-tertiary">
              The RRG plots where each sector sits on two axes: how much it has outperformed the Nifty 500 (X) and whether that outperformance is accelerating or fading (Y). Sectors rotate <span className="font-medium text-ink-primary">clockwise</span>. Trailing dots = last 5 days; fast trails = active rotation.
            </p>

            <div className="space-y-2">
              <div className="font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">Axes</div>
              <div><span className="font-medium text-ink-primary">X — RS Strength:</span> outperformance vs Nifty 500 over 3M. Mean-centered — zero is the average, right is better.</div>
              <div><span className="font-medium text-ink-primary">Y — RS Momentum:</span> change in RS over last 20 days. Above zero = gaining ground vs index.</div>
            </div>

            <div className="space-y-2">
              <div className="font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">Quadrants</div>
              <div className="flex items-start gap-2">
                <span className="mt-0.5 inline-block w-2 h-2 rounded-full bg-signal-pos flex-shrink-0" />
                <span><span className="font-medium text-ink-primary">Leading (↗)</span> — strong RS + improving momentum. Own and stay.</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="mt-0.5 inline-block w-2 h-2 rounded-full bg-signal-warn flex-shrink-0" />
                <span><span className="font-medium text-ink-primary">Weakening (↘)</span> — RS positive but fading. Start trimming before it crosses zero.</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="mt-0.5 inline-block w-2 h-2 rounded-full bg-ink-tertiary flex-shrink-0" />
                <span><span className="font-medium text-ink-primary">Lagging (↙)</span> — underperforming and losing further ground. Avoid / exit.</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="mt-0.5 inline-block w-2 h-2 rounded-full bg-teal flex-shrink-0" />
                <span><span className="font-medium text-ink-primary">Improving (↖)</span> — RS negative but momentum turning. Early signal — watch for a Leading cross.</span>
              </div>
            </div>

            <div className="space-y-1 border-t border-paper-rule pt-3">
              <div className="font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">How to act</div>
              <div className="leading-relaxed">Own <span className="font-medium text-ink-primary">Leading</span> sectors with broad RS breadth. Trim <span className="font-medium text-ink-primary">Weakening</span> before the X-axis cross. Avoid <span className="font-medium text-ink-primary">Lagging</span>. Watch <span className="font-medium text-ink-primary">Improving</span> — tomorrow&apos;s Leading if the regime supports risk. Fast clockwise trails = conviction; slow or counter-clockwise = indecision.</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Section 3: Decision Table ── */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <SectionDivider
          title="Sector Decision Table"
          subtitle="Click any row for the full sector deep dive"
        />
        <SectorDecisionTable data={visibleWithDays} onSelect={onSelect} leadingRRGCount={leadingRRGCount} />
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

        {/* Event Playbook */}
        {playbook.length > 0 && (
          <div className="mb-10 -mx-6">
            <SectorEventPlaybook
              entries={playbook}
              currentOverweightSectors={overweightSectors}
            />
          </div>
        )}

        {/* Sector State Heatmap */}
        <div>
          <div className="flex items-center justify-between mb-4">
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
          <div className="grid grid-cols-1 xl:grid-cols-[1fr_260px] gap-6 items-start">
            {/* Heatmap */}
            <SectorHeatmap
              history={filteredHistory}
              sectors={visible.map(s => s.sector_name)}
            />

            {/* Commentary panel */}
            <div className="font-sans text-[11px] text-ink-secondary space-y-4 pt-1">
              <div className="space-y-2">
                <div className="font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">Color key</div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-3 h-3 rounded-sm flex-shrink-0" style={{ background: '#22c55e' }} />
                  <span><span className="font-medium" style={{ color: '#22c55e' }}>Overweight</span> — sector meets RS + breadth thresholds. Active position.</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-3 h-3 rounded-sm flex-shrink-0" style={{ background: '#f59e0b' }} />
                  <span><span className="font-medium" style={{ color: '#f59e0b' }}>Neutral</span> — mixed signals. Hold existing positions; no new adds.</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-3 h-3 rounded-sm flex-shrink-0" style={{ background: '#ef4444' }} />
                  <span><span className="font-medium" style={{ color: '#ef4444' }}>Underweight</span> — RS or breadth deteriorating. Reduce / exit.</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block w-3 h-3 rounded-sm flex-shrink-0" style={{ background: '#7c2d12' }} />
                  <span><span className="font-medium" style={{ color: '#9a3412' }}>Avoid</span> — broad breakdown. No exposure; capital preservation only.</span>
                </div>
              </div>

              <div className="space-y-2 border-t border-paper-rule pt-3">
                <div className="font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">What to look for</div>
                <div className="leading-relaxed">
                  <span className="font-medium text-ink-primary">Sustained runs</span> signal conviction — a sector that has been Overweight for 60+ days is a core position, not a trade.
                </div>
                <div className="leading-relaxed">
                  <span className="font-medium text-ink-primary">Fresh flips to green</span> in the last 1–5 cells are new entry candidates. Cross-check in the bubble chart and RRG before sizing.
                </div>
                <div className="leading-relaxed">
                  <span className="font-medium text-ink-primary">Red runs after green</span> are exits, not dips. The model has seen the breadth data; follow it.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
