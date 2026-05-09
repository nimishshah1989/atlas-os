// frontend/src/components/sectors/SectorViews.tsx
'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Info, ChevronDown, ChevronUp } from 'lucide-react'
import type { SectorDecision } from '@/lib/sectors-decision'
import type { SectorStateRow, SectorSnapshot } from '@/lib/queries/sectors'
import { SectorBubbleChart } from './SectorBubbleChart'
import { SectorDecisionTable } from './SectorDecisionTable'
import { SectorHeatmap } from './SectorHeatmap'

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
  range: string
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

export function SectorViews({ actionable, excluded, allSectors, stateHistory, range }: Props) {
  const router = useRouter()
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? allSectors : actionable

  const onSelect = (name: string) => {
    router.push(`/sectors/${encodeURIComponent(name)}?range=${range}`)
  }

  return (
    <>
      {/* View 1: Bubble Matrix */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <div className="flex items-baseline gap-3 mb-3">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
            Sector Positioning Matrix — RS vs Breadth
          </h2>
          <span className="font-sans text-xs text-ink-tertiary">Current snapshot — click any bubble for the deep dive</span>
        </div>
        <HowToReadPanel />
        <SectorBubbleChart data={visible} range={range} onSelect={onSelect} />
        <ExcludedNote
          excluded={excluded}
          showAll={showAll}
          onToggle={() => setShowAll(s => !s)}
        />
      </div>

      {/* View 2: Decision Table */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <div className="flex items-baseline gap-3 mb-4">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
            Sector Decision Table
            <span title="Bottom-up rollup of every sector's signals. Decision is derived from sector state + RS + momentum. Click any row for the deep dive.">
              <Info className="w-3 h-3 opacity-60 cursor-help" />
            </span>
          </h2>
        </div>
        <SectorDecisionTable data={visible} onSelect={onSelect} />
      </div>

      {/* View 3: State History Heatmap */}
      <div className="px-6 py-6">
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
    </>
  )
}
