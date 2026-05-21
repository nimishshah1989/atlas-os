'use client'
import { useState } from 'react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import type { ConvictionMapRow } from '@/lib/queries/conviction'
import type { RSLeaderRow, BreakoutCandidateRow } from '@/lib/queries/leaders'
import { StockBreadthPanel } from './StockBreadthPanel'
import { StockBubbleChart } from './StockBubbleChart'
import { StockIntelligencePanel } from './StockIntelligencePanel'
import { StockScreener } from './StockScreener'
import { IntradayRSLeaders } from './IntradayRSLeaders'
import { RSLeadersPanel } from './RSLeadersPanel'
import { CTSGradeSummaryCards } from './CTSGradeSummaryCards'
import { CTSIndexTimingPanel } from './CTSIndexTimingPanel'
import { CTSSectorPanel } from './CTSSectorPanel'

type MaFilter = 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null
type ActiveView = 'overview' | 'leaders'

export function StocksClientShell({
  stocks,
  regimeState,
  deploymentMultiplier,
  convictionMap,
  leaders,
  breakouts,
  deterioration,
}: {
  stocks: StockRowWithSector[]
  regimeState: string
  deploymentMultiplier: number
  convictionMap?: Record<string, ConvictionMapRow>
  leaders: RSLeaderRow[]
  breakouts: BreakoutCandidateRow[]
  deterioration: BreakoutCandidateRow[]
}) {
  const [maFilter, setMaFilter] = useState<MaFilter>(null)
  const [activeView, setActiveView] = useState<ActiveView>('overview')
  const [showIntraday, setShowIntraday] = useState(false)

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
          <div className="border border-paper-rule rounded-sm bg-paper">
            <button
              type="button"
              onClick={() => setShowIntraday(v => !v)}
              className="w-full flex items-center justify-between px-5 py-2.5 font-sans text-xs font-medium text-ink-secondary hover:bg-paper-rule/10 transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-signal-pos" />
                Live RS Leaders (intraday)
              </span>
              <span className="text-ink-tertiary">{showIntraday ? '▲ Hide' : '▼ Show'}</span>
            </button>
            {showIntraday && (
              <div className="border-t border-paper-rule p-4">
                <IntradayRSLeaders />
              </div>
            )}
          </div>
          <StockBreadthPanel
            stocks={stocks}
            activeMaFilter={maFilter}
            onMaFilter={setMaFilter}
          />
          <StockBubbleChart stocks={stocks} />
          <StockIntelligencePanel
            stocks={stocks}
            regimeState={regimeState}
            deploymentMultiplier={deploymentMultiplier}
          />
          <CTSGradeSummaryCards />
          <CTSIndexTimingPanel />
          <CTSSectorPanel />
          <StockScreener
            stocks={stocks}
            maFilter={maFilter}
            convictionMap={convictionMap}
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
