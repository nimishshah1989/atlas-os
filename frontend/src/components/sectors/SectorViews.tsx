'use client'
import { useState } from 'react'
import type { SectorDecision } from '@/lib/sectors-decision'
import type { SectorStateRow, SectorSnapshot } from '@/lib/queries/sectors'
import { SectorBubbleChart } from './SectorBubbleChart'
import { SectorDecisionTable } from './SectorDecisionTable'
import { SectorHeatmap } from './SectorHeatmap'
import { SectorDrawer } from './SectorDrawer'

type SectorWithDecision = SectorSnapshot & { decision: SectorDecision }

type Props = {
  sectors: SectorWithDecision[]
  stateHistory: SectorStateRow[]
  range: string
}

export function SectorViews({ sectors, stateHistory, range }: Props) {
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <>
      {/* View 1: Bubble Matrix */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector Positioning Matrix — RS vs Breadth
        </h2>
        <SectorBubbleChart data={sectors} range={range} onSelect={setSelected} />
      </div>

      {/* View 2: Decision Table */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector Decision Table
        </h2>
        <SectorDecisionTable data={sectors} onSelect={setSelected} />
      </div>

      {/* View 3: State History Heatmap */}
      <div className="px-6 py-6">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-4">
          Sector State History — {range}
        </h2>
        <SectorHeatmap
          history={stateHistory}
          sectors={sectors.map(s => s.sector_name)}
        />
      </div>

      {/* Drawer (shared) */}
      {selected && (
        <SectorDrawer
          sectorName={selected}
          range={range}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  )
}
