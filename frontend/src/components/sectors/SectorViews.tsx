// frontend/src/components/sectors/SectorViews.tsx
'use client'
import { useState } from 'react'
import { useRouter, useSearchParams, usePathname } from 'next/navigation'
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

// RRGChart uses D3 and must not run on the server.
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

const VALID_TABS = ['rotation', 'rrg', 'decision', 'history'] as const
type Tab = (typeof VALID_TABS)[number]

const TAB_LABEL: Record<Tab, string> = {
  rotation: 'Rotation Matrix',
  rrg:      'RRG',
  decision: 'Decision Table',
  history:  'State History',
}

function HowToReadPanel() {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-3">
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
        <div className="mt-2 px-3.5 py-2.5 bg-paper-rule/15 border border-paper-rule rounded-sm grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 font-sans text-[11px] text-ink-secondary leading-relaxed">
          <div><span className="font-semibold text-ink-primary">X-axis:</span> 3-month relative strength vs Nifty 500. Right of zero = leading; left = lagging.</div>
          <div><span className="font-semibold text-ink-primary">Y-axis:</span> % of stocks above their 50-day EMA. Up = broader strength; down = participation thinning.</div>
          <div><span className="font-semibold text-ink-primary">Bubble size:</span> number of stocks in the sector.</div>
          <div><span className="font-semibold text-ink-primary">Color:</span> current state — green (Overweight), amber (Neutral), red (Underweight / Avoid).</div>
          <div className="sm:col-span-2"><span className="font-semibold text-ink-primary">Where to look:</span> top-right (LEADERS) is what you want to be long. Bottom-left (LAGGARDS) — capital preservation. Click any bubble for full history + stocks.</div>
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
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? allSectors : actionable

  const rawTab = searchParams.get('tab') ?? 'rotation'
  const activeTab: Tab = (VALID_TABS as readonly string[]).includes(rawTab)
    ? (rawTab as Tab)
    : 'rotation'

  function setTab(tab: Tab) {
    const params = new URLSearchParams(searchParams.toString())
    params.set('tab', tab)
    router.replace(`${pathname}?${params.toString()}`)
  }

  const onSelect = (name: string) => {
    router.push(`/sectors/${encodeURIComponent(name)}?range=${range}`)
  }

  const daysMap = new Map(daysInState.map(d => [d.sector_name, d.days_in_state]))
  const visibleWithDays = visible.map(s => ({
    ...s,
    days_in_state: daysMap.get(s.sector_name),
  }))

  return (
    <>
      {/* Always-visible state transitions card */}
      <div className="px-6 pt-6 pb-4">
        <StateTransitionCard sectors={allSectors} daysInState={daysInState} />
      </div>

      {/* Tab bar */}
      <div className="px-6 border-b border-paper-rule" role="tablist" aria-label="Sector views">
        <div className="flex gap-6">
          {VALID_TABS.map(tab => {
            const isActive = tab === activeTab
            return (
              <button
                key={tab}
                role="tab"
                aria-selected={isActive}
                aria-controls={`sector-tab-panel-${tab}`}
                id={`sector-tab-${tab}`}
                onClick={() => setTab(tab)}
                className={
                  'relative pb-3 pt-2 font-sans text-xs uppercase tracking-wider transition-colors ' +
                  (isActive
                    ? 'text-ink-primary font-medium'
                    : 'text-ink-tertiary hover:text-ink-secondary')
                }
              >
                {TAB_LABEL[tab]}
                {isActive && (
                  <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-ink-primary" />
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Tab panels */}
      {activeTab === 'rotation' && (
        <div
          role="tabpanel"
          id="sector-tab-panel-rotation"
          aria-labelledby="sector-tab-rotation"
          className="px-6 py-6"
        >
          <div className="flex items-baseline gap-3 mb-3">
            <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
              Sector Positioning Matrix — RS vs Breadth
            </h2>
            <span className="font-sans text-xs text-ink-tertiary">
              Current snapshot — click any bubble for the deep dive
            </span>
          </div>
          <HowToReadPanel />
          <SectorBubbleChart data={visible} range={range} onSelect={onSelect} />
          <ExcludedNote
            excluded={excluded}
            showAll={showAll}
            onToggle={() => setShowAll(s => !s)}
          />
        </div>
      )}

      {activeTab === 'rrg' && (
        <div
          role="tabpanel"
          id="sector-tab-panel-rrg"
          aria-labelledby="sector-tab-rrg"
          className="px-6 py-6"
        >
          <div className="flex items-baseline gap-3 mb-3">
            <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
              Relative Rotation Graph
              <span title="Quadrant momentum view: leading, weakening, lagging, improving. Trails show the last 5 trading days; today is the solid bubble.">
                <Info className="w-3 h-3 opacity-60 cursor-help" />
              </span>
            </h2>
          </div>
          <RRGChart current={visible} history={rrgHistory} onSelect={onSelect} />
        </div>
      )}

      {activeTab === 'decision' && (
        <div
          role="tabpanel"
          id="sector-tab-panel-decision"
          aria-labelledby="sector-tab-decision"
          className="px-6 py-6"
        >
          <div className="flex items-baseline gap-3 mb-4">
            <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
              Sector Decision Table
              <span title="Bottom-up rollup of every sector's signals. Decision is derived from sector state + RS + momentum. Click any row for the deep dive.">
                <Info className="w-3 h-3 opacity-60 cursor-help" />
              </span>
            </h2>
          </div>
          <SectorDecisionTable data={visibleWithDays} onSelect={onSelect} />
        </div>
      )}

      {activeTab === 'history' && (
        <div
          role="tabpanel"
          id="sector-tab-panel-history"
          aria-labelledby="sector-tab-history"
          className="px-6 py-6 space-y-8"
        >
          <div>
            <div className="flex items-baseline gap-3 mb-4">
              <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
                Breadth Waterfall
                <span title="Share of stocks classified as Leader vs Strong by relative strength, plotted across the available history.">
                  <Info className="w-3 h-3 opacity-60 cursor-help" />
                </span>
              </h2>
            </div>
            <BreadthWaterfall data={breadthData} />
          </div>

          <div>
            <div className="flex items-baseline gap-3 mb-4">
              <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
                Sector State History — {range}
                <span title="Daily classification per sector across the selected range. Green = Overweight, Amber = Neutral, Red = Underweight/Avoid. Look for sectors that flipped recently.">
                  <Info className="w-3 h-3 opacity-60 cursor-help" />
                </span>
              </h2>
            </div>
            <SectorHeatmap
              history={stateHistory}
              sectors={visible.map(s => s.sector_name)}
            />
          </div>
        </div>
      )}
    </>
  )
}
