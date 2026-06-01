'use client'
import { useState } from 'react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import type { ComponentValidation } from '@/lib/queries/component_validation'
import type { RSLeaderRow, BreakoutCandidateRow } from '@/lib/queries/leaders'
import type { PolicyEntryParams } from '@/lib/policy-entry-filter'
import { StockBreadthPanel } from './StockBreadthPanel'
import { StockIntelligencePanel } from './StockIntelligencePanel'
import { StockScreener } from './StockScreener'
import { IntradayRSLeaders } from './IntradayRSLeaders'
import { RSLeadersPanel } from './RSLeadersPanel'

type MaFilter = 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null
type ActiveView = 'overview' | 'leaders'

export function StocksClientShell({
  stocks,
  regimeState,
  deploymentMultiplier,
  validations = [],
  leaders,
  breakouts,
  deterioration,
  initialSectorFilter,
  initialIndexFilter,
  policyEntryParams,
}: {
  stocks: StockRowWithSector[]
  regimeState: string
  deploymentMultiplier: number
  validations?: ComponentValidation[]
  leaders: RSLeaderRow[]
  breakouts: BreakoutCandidateRow[]
  deterioration: BreakoutCandidateRow[]
  initialSectorFilter?: string
  initialIndexFilter?: string
  /** Policy entry-rule params for flow mode (active portfolio + sector filter). */
  policyEntryParams?: PolicyEntryParams
}) {
  const [maFilter, setMaFilter] = useState<MaFilter>(null)
  const [activeView, setActiveView] = useState<ActiveView>('overview')

  return (
    <div className="flex flex-col gap-6">
      {/* Tab toggle */}
      <div className="flex items-center gap-1 border-b border-paper-rule pb-0">
        <button
          className={`px-4 py-2 font-sans text-xs font-medium border-b-2 transition-colors ${
            activeView === 'overview'
              ? 'border-teal text-ink-primary'
              : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
          }`}
          onClick={() => setActiveView('overview')}
        >
          Overview
        </button>
        <button
          className={`px-4 py-2 font-sans text-xs font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
            activeView === 'leaders'
              ? 'border-teal text-ink-primary'
              : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
          }`}
          onClick={() => setActiveView('leaders')}
        >
          RS Leaders
          {leaders.length > 0 && (
            <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-teal/15 font-sans text-[9px] font-semibold text-teal">
              {leaders.length}
            </span>
          )}
        </button>
      </div>

      {activeView === 'overview' ? (
        <>
          <IntradayRSLeaders />
          <StockBreadthPanel
            stocks={stocks}
            activeMaFilter={maFilter}
            onMaFilter={setMaFilter}
          />
          <StockIntelligencePanel
            stocks={stocks}
            regimeState={regimeState}
            deploymentMultiplier={deploymentMultiplier}
          />
          <StockScreener
            stocks={stocks}
            maFilter={maFilter}
            validations={validations}
            initialSectorFilter={initialSectorFilter}
            initialIndexFilter={initialIndexFilter}
            policyEntryParams={policyEntryParams}
          />
        </>
      ) : (
        <RSLeadersPanel
          leaders={leaders}
          breakouts={breakouts}
          deterioration={deterioration}
        />
      )}
    </div>
  )
}
