'use client'
import { useState } from 'react'
import type { ETFRow, ETFMetricHistoryRow, ETFStateHistoryRow } from '@/lib/queries/etfs'
import { ETFOverviewTab } from './ETFOverviewTab'
import { ETFHistoryTab } from './ETFHistoryTab'

type Tab = 'overview' | 'history'

export function ETFDeepDiveTabs({
  etf,
  metricHistory,
  stateHistory,
}: {
  etf: ETFRow
  metricHistory: ETFMetricHistoryRow[]
  stateHistory: ETFStateHistoryRow[]
}) {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div>
      {/* Tab bar */}
      <div className="px-6 border-b border-paper-rule">
        <div className="flex items-center gap-0">
          {(['overview', 'history'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 font-sans text-sm capitalize transition-colors border-b-2 -mb-px ${
                tab === t
                  ? 'border-teal text-ink-primary font-medium'
                  : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
              }`}
            >
              {t === 'overview' ? 'Overview' : 'State History'}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <ETFOverviewTab etf={etf} metricHistory={metricHistory} />
      )}
      {tab === 'history' && (
        <ETFHistoryTab etf={etf} stateHistory={stateHistory} metricHistory={metricHistory} />
      )}
    </div>
  )
}
