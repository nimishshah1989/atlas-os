'use client'
import { useState } from 'react'
import type { ETFRow, ETFMetricHistoryRow, ETFStateHistoryRow, ETFHoldingRow } from '@/lib/queries/etfs'
import type { TimeRange } from '@/lib/time-range'
import { ETFOverviewTab } from './ETFOverviewTab'
import { ETFHistoryTab } from './ETFHistoryTab'
import { ETFHoldingsTab } from './ETFHoldingsTab'

type Tab = 'overview' | 'history' | 'holdings'

const TAB_LABELS: Record<Tab, string> = {
  overview: 'Overview',
  history: 'State History',
  holdings: 'Holdings',
}

export function ETFDeepDiveTabs({
  etf,
  metricHistory,
  stateHistory,
  holdings,
  range,
  initialTab = 'overview',
}: {
  etf: ETFRow
  metricHistory: ETFMetricHistoryRow[]
  stateHistory: ETFStateHistoryRow[]
  holdings: ETFHoldingRow[]
  range: TimeRange
  initialTab?: string
}) {
  const validTab = (['overview', 'history', 'holdings'] as Tab[]).includes(initialTab as Tab)
    ? (initialTab as Tab)
    : 'overview'
  const [tab, setTab] = useState<Tab>(validTab)

  return (
    <div>
      {/* Tab bar */}
      <div className="px-6 border-b border-paper-rule">
        <div className="flex items-center gap-0">
          {(['overview', 'history', 'holdings'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 font-sans text-sm capitalize transition-colors border-b-2 -mb-px ${
                tab === t
                  ? 'border-teal text-ink-primary font-medium'
                  : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
              }`}
            >
              {TAB_LABELS[t]}
              {t === 'holdings' && holdings.length > 0 && (
                <span className="ml-1.5 font-sans text-[10px] bg-paper-rule/40 px-1 py-0.5 rounded">
                  {holdings.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <ETFOverviewTab etf={etf} metricHistory={metricHistory} range={range} />
      )}
      {tab === 'history' && (
        <ETFHistoryTab etf={etf} stateHistory={stateHistory} metricHistory={metricHistory} />
      )}
      {tab === 'holdings' && (
        <ETFHoldingsTab holdings={holdings} />
      )}
    </div>
  )
}
