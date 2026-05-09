'use client'
import { useState } from 'react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import type { MetricHistoryRow, StateHistoryRow } from '@/lib/queries/stocks'
import { StockOverviewTab } from './StockOverviewTab'
import { StockHistoryTab } from './StockHistoryTab'

type Tab = 'overview' | 'history'

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'history',  label: 'History' },
]

export function StockTabs({
  stock,
  metricHistory,
  stateHistory,
}: {
  stock: StockRowWithSector
  metricHistory: MetricHistoryRow[]
  stateHistory: StateHistoryRow[]
}) {
  const [active, setActive] = useState<Tab>('overview')

  return (
    <div>
      {/* Tab bar */}
      <div className="px-6 border-b border-paper-rule flex gap-0">
        {TABS.map(t => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActive(t.key)}
            className={`px-4 py-3 font-sans text-sm font-medium border-b-2 transition-colors ${
              active === t.key
                ? 'border-teal text-teal'
                : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {active === 'overview' && (
        <StockOverviewTab
          stock={stock}
          metricHistory={metricHistory}
          stateHistory={stateHistory}
        />
      )}
      {active === 'history' && (
        <StockHistoryTab
          stock={stock}
          stateHistory={stateHistory}
          metricHistory={metricHistory}
        />
      )}
    </div>
  )
}
